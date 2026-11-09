#!/usr/bin/env python3
"""
mqtt_rabbitmq_bridge.py
=======================
Puente MQTT -> RabbitMQ.

- Escucha todos los topics bajo flota/#.
- Reenvia la telemetria GPS al exchange de la flota.
- Convierte las lecturas fuera de rango en alertas y las enruta al exchange.

Exchange y routing keys:
    exchange.fleet
        gps.routing   -> cola.gps.telemetria
        temp.alert    -> cola.alertas.temperatura
        fuel.routing  -> cola.combustible.nivel

Uso:
    python3 mqtt/mqtt_rabbitmq_bridge.py

Variables de entorno opcionales:
    MQTT_BROKER, MQTT_PUERTO
    RABBITMQ_HOST, RABBITMQ_PUERTO, RABBITMQ_USER, RABBITMQ_PASS

Compatible con paho-mqtt 1.6.x y 2.x.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time

import paho.mqtt.client as mqtt
import pika

try:  # paho-mqtt >= 2.0
    from paho.mqtt.client import CallbackAPIVersion
except ImportError:  # paho-mqtt 1.x
    CallbackAPIVersion = None

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PUERTO = int(os.getenv("MQTT_PUERTO", "1883"))
MQTT_TOPIC = "flota/#"
MQTT_QOS = 1
CLIENT_ID = "puente-mqtt-rabbitmq"

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PUERTO = int(os.getenv("RABBITMQ_PUERTO", "5672"))
RABBITMQ_USUARIO = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_CLAVE = os.getenv("RABBITMQ_PASS", "admin123")

EXCHANGE = "exchange.fleet"

COLA_GPS = "cola.gps.telemetria"
COLA_ALERTAS_TEMP = "cola.alertas.temperatura"
COLA_COMBUSTIBLE = "cola.combustible.nivel"

ROUTING_GPS = "gps.routing"
ROUTING_TEMP = "temp.alert"
ROUTING_FUEL = "fuel.routing"

COLAS = (COLA_GPS, COLA_ALERTAS_TEMP, COLA_COMBUSTIBLE)

COLA_INTERNA: queue.Queue = queue.Queue(maxsize=10000)
DETENER = threading.Event()


def crear_cliente() -> mqtt.Client:
    """Crea el cliente usando la API de callbacks nativa de la version instalada."""
    argumentos = {
        "client_id": CLIENT_ID,
        "protocol": mqtt.MQTTv311,
    }
    if CallbackAPIVersion is not None:
        return mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            **argumentos,
        )
    return mqtt.Client(**argumentos)


def conectar_rabbit():
    """Abre una conexion AMQP y declara exchange, colas durables y bindings."""
    parametros = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PUERTO,
        credentials=pika.PlainCredentials(RABBITMQ_USUARIO, RABBITMQ_CLAVE),
        heartbeat=60,
        blocked_connection_timeout=10,
    )
    conexion = pika.BlockingConnection(parametros)
    canal = conexion.channel()

    canal.exchange_declare(
        exchange=EXCHANGE,
        exchange_type="direct",
        durable=True,
    )

    for cola in COLAS:
        canal.queue_declare(queue=cola, durable=True)

    canal.queue_bind(queue=COLA_GPS, exchange=EXCHANGE, routing_key=ROUTING_GPS)
    canal.queue_bind(
        queue=COLA_ALERTAS_TEMP,
        exchange=EXCHANGE,
        routing_key=ROUTING_TEMP,
    )
    canal.queue_bind(
        queue=COLA_COMBUSTIBLE,
        exchange=EXCHANGE,
        routing_key=ROUTING_FUEL,
    )

    print(
        f"[RABBITMQ] Conectado a {RABBITMQ_HOST}:{RABBITMQ_PUERTO}; "
        f"exchange {EXCHANGE} y colas listas: {', '.join(COLAS)}"
    )
    return conexion, canal


def conectar_rabbit_con_reintento():
    """Reintenta la conexion AMQP hasta lograrlo o hasta recibir Ctrl+C."""
    while not DETENER.is_set():
        try:
            return conectar_rabbit()
        except (pika.exceptions.AMQPError, OSError) as exc:
            print(
                f"[RABBITMQ] No disponible ({exc}); reintento en 5 s...",
                file=sys.stderr,
            )
            DETENER.wait(5)
    return None, None


def cerrar_conexion(conexion) -> None:
    try:
        if conexion is not None and conexion.is_open:
            conexion.close()
    except Exception:
        pass


def enrutar(topic: str, datos: dict):
    """Devuelve (cola, routing_key, payload) o None si no se reenvia."""
    partes = topic.split("/")
    if len(partes) != 3 or partes[0] != "flota":
        return None

    sensor = partes[2]

    if sensor == "gps":
        return COLA_GPS, ROUTING_GPS, datos

    if sensor == "temperatura":
        temperature = datos.get("temperature")
        if (
            isinstance(temperature, (int, float))
            and not isinstance(temperature, bool)
            and temperature > 4
        ):
            alerta = dict(datos)
            alerta["type"] = "TEMP_ALERT"
            alerta["message"] = "Temperatura excedida"
            return COLA_ALERTAS_TEMP, ROUTING_TEMP, alerta

    if sensor == "combustible":
        fuel_level = datos.get("fuel_level")
        if (
            isinstance(fuel_level, (int, float))
            and not isinstance(fuel_level, bool)
            and fuel_level < 20
        ):
            alerta = dict(datos)
            alerta["type"] = "FUEL_LOW"
            alerta["message"] = "Combustible bajo"
            return COLA_COMBUSTIBLE, ROUTING_FUEL, alerta

    return None


def publicar_en_rabbit(canal, topic: str, payload: bytes) -> None:
    """Parsea el JSON, aplica el enrutamiento y publica de forma persistente."""
    try:
        datos = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON invalido: {exc}") from exc

    if not isinstance(datos, dict):
        raise ValueError("el payload no es un objeto JSON")

    destino = enrutar(topic, datos)
    if destino is None:
        return

    cola, routing_key, cuerpo = destino
    canal.basic_publish(
        exchange=EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        properties=pika.BasicProperties(
            delivery_mode=2,  # mensaje persistente
            content_type="application/json",
        ),
    )
    print(f"[BRIDGE] {topic} -> {EXCHANGE}/{routing_key} ({cola})")


def trabajador_rabbitmq() -> None:
    """Hilo unico propietario de la conexion Pika."""
    conexion = None
    canal = None
    pendiente = None

    while not DETENER.is_set():
        if conexion is None or conexion.is_closed or canal is None or canal.is_closed:
            conexion, canal = conectar_rabbit_con_reintento()
            if conexion is None:
                break

        if pendiente is None:
            try:
                pendiente = COLA_INTERNA.get(timeout=0.5)
            except queue.Empty:
                try:
                    # Mantiene vivas las conexiones y procesa heartbeats.
                    conexion.process_data_events(time_limit=0)
                except (pika.exceptions.AMQPError, OSError) as exc:
                    print(
                        f"[RABBITMQ] Conexion perdida ({exc}); reconectando...",
                        file=sys.stderr,
                    )
                    cerrar_conexion(conexion)
                    conexion = canal = None
                continue

        if pendiente is None:  # centinela de cierre
            break

        try:
            publicar_en_rabbit(canal, *pendiente)
            pendiente = None
        except ValueError as exc:
            print(f"[BRIDGE] Mensaje descartado: {exc}", file=sys.stderr)
            pendiente = None
        except (pika.exceptions.AMQPError, OSError) as exc:
            print(
                f"[RABBITMQ] Error al publicar ({exc}); reconectando...",
                file=sys.stderr,
            )
            cerrar_conexion(conexion)
            conexion = canal = None
            DETENER.wait(1)

    cerrar_conexion(conexion)


def main() -> int:
    cliente = crear_cliente()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[MQTT] Conexion rechazada (rc={rc})", file=sys.stderr)
            return
        client.subscribe(MQTT_TOPIC, qos=MQTT_QOS)
        print(f"[MQTT] Conectado a {MQTT_BROKER}:{MQTT_PUERTO}")
        print(f"[MQTT] Suscrito a {MQTT_TOPIC}")

    def on_message(client, userdata, msg):
        if DETENER.is_set():
            return
        try:
            COLA_INTERNA.put((msg.topic, msg.payload), timeout=1)
        except queue.Full:
            print(
                f"[BRIDGE] Cola interna llena; se descarta {msg.topic}",
                file=sys.stderr,
            )

    def on_disconnect(client, userdata, *args):
        print("[MQTT] Desconectado del broker; paho intentara reconectar...")

    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.on_disconnect = on_disconnect

    hilo_rabbitmq = threading.Thread(
        target=trabajador_rabbitmq,
        name="publicador-rabbitmq",
        daemon=True,
    )
    hilo_rabbitmq.start()

    try:
        cliente.connect(MQTT_BROKER, MQTT_PUERTO, keepalive=60)
    except OSError as exc:
        print(
            f"[MQTT] No se pudo conectar a {MQTT_BROKER}:{MQTT_PUERTO}: {exc}\n"
            "       Verifica que el contenedor este arriba: docker compose up -d",
            file=sys.stderr,
        )
        DETENER.set()
        try:
            COLA_INTERNA.put_nowait(None)
        except queue.Full:
            pass
        hilo_rabbitmq.join(timeout=5)
        return 1

    cliente.loop_start()
    print("[BRIDGE] Ctrl+C para salir\n")

    try:
        while not DETENER.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[BRIDGE] Ctrl+C recibido, cerrando...")
    finally:
        DETENER.set()
        cliente.disconnect()
        cliente.loop_stop()
        try:
            COLA_INTERNA.put_nowait(None)
        except queue.Full:
            pass
        hilo_rabbitmq.join(timeout=10)
        print("[BRIDGE] Detenido.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
