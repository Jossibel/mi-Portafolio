#!/usr/bin/env python3
"""
simulador_sensores.py
=====================
Publica telemetria simulada de una flota de vehiculos cada 5 segundos.

Topics:
    flota/{vehiculo_id}/gps
    flota/{vehiculo_id}/temperatura
    flota/{vehiculo_id}/combustible

Uso:
    python3 mqtt/simulador_sensores.py

Variables de entorno opcionales:
    MQTT_BROKER, MQTT_PUERTO

Compatible con paho-mqtt 1.6.x y 2.x.
"""

from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

try:  # paho-mqtt >= 2.0
    from paho.mqtt.client import CallbackAPIVersion
except ImportError:  # paho-mqtt 1.x
    CallbackAPIVersion = None

BROKER = os.getenv("MQTT_BROKER", "localhost")
PUERTO = int(os.getenv("MQTT_PUERTO", "1883"))
VEHICULOS = ["VH-001", "VH-002", "VH-003"]
INTERVALO_SEGUNDOS = 5
QOS = 1
CLIENT_ID = "simulador-flota"

# Centro geografico aproximado de Ciudad de Panama.
LAT_BASE = -2.1709
LNG_BASE = -79.9224


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


def timestamp_utc() -> str:
    """Devuelve una marca temporal ISO-8601 en UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def publicar(cliente: mqtt.Client, topic: str, payload: dict) -> bool:
    """Publica un diccionario como JSON y devuelve True si MQTT lo acepto."""
    info = cliente.publish(
        topic,
        json.dumps(payload, ensure_ascii=False),
        qos=QOS,
    )
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        print(
            f"[MQTT] Error al publicar en {topic} (rc={info.rc})",
            file=sys.stderr,
        )
        return False
    return True


def publicar_ciclo(cliente: mqtt.Client) -> int:
    """Genera y publica una lectura de cada sensor para cada vehiculo."""
    ts = timestamp_utc()
    enviados = 0

    for vehiculo_id in VEHICULOS:
        lat = round(LAT_BASE + random.uniform(-0.0008, 0.0008), 6)
        lng = round(LNG_BASE + random.uniform(-0.0008, 0.0008), 6)
        speed = round(random.uniform(20.0, 80.0), 1)
        temperature = round(random.uniform(-5.0, 8.0), 1)
        fuel_level = round(random.uniform(10.0, 100.0), 1)

        mensajes = (
            (
                f"flota/{vehiculo_id}/gps",
                {
                    "vehicle_id": vehiculo_id,
                    "timestamp": ts,
                    "lat": lat,
                    "lng": lng,
                    "speed": speed,
                },
            ),
            (
                f"flota/{vehiculo_id}/temperatura",
                {
                    "vehicle_id": vehiculo_id,
                    "timestamp": ts,
                    "temperature": temperature,
                    "unit": "celsius",
                },
            ),
            (
                f"flota/{vehiculo_id}/combustible",
                {
                    "vehicle_id": vehiculo_id,
                    "timestamp": ts,
                    "fuel_level": fuel_level,
                    "unit": "percent",
                },
            ),
        )

        for topic, payload in mensajes:
            if publicar(cliente, topic, payload):
                enviados += 1

    print(
        f"[SIM {ts}] {enviados}/{len(VEHICULOS) * 3} mensajes publicados "
        f"bajo flota/#"
    )
    return enviados


def main() -> int:
    cliente = crear_cliente()
    conectado = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[MQTT] Conexion rechazada (rc={rc})", file=sys.stderr)
            return
        conectado.set()
        print(f"[MQTT] Conectado a {BROKER}:{PUERTO}")

    def on_disconnect(client, userdata, *args):
        conectado.clear()
        print("[MQTT] Desconectado del broker; paho intentara reconectar...")

    cliente.on_connect = on_connect
    cliente.on_disconnect = on_disconnect

    try:
        cliente.connect(BROKER, PUERTO, keepalive=60)
    except OSError as exc:
        print(
            f"[MQTT] No se pudo conectar a {BROKER}:{PUERTO}: {exc}\n"
            "       Verifica que el contenedor este arriba: docker compose up -d",
            file=sys.stderr,
        )
        return 1

    cliente.loop_start()

    try:
        if not conectado.wait(timeout=10):
            print("[MQTT] Timeout esperando la confirmacion del broker.", file=sys.stderr)
            return 1

        print(
            f"[SIM] Intervalo: {INTERVALO_SEGUNDOS}s | QoS: {QOS} | "
            "Ctrl+C para salir\n"
        )
        while True:
            if conectado.is_set():
                publicar_ciclo(cliente)
            else:
                print("[SIM] Sin conexion; esperando reconexion...")
            time.sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        print("\n[SIM] Ctrl+C recibido, cerrando...")
    finally:
        cliente.disconnect()
        cliente.loop_stop()
        print("[SIM] Cliente MQTT detenido.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
