#!/usr/bin/env python3
"""
suscriptor_almacenador.py
=========================
Se suscribe a la telemetria MQTT y almacena cada lectura en SQLite.

Topics:
    flota/+/gps
    flota/+/temperatura
    flota/+/combustible

Base de datos:
    mqtt/telemetria.db (se crea junto a este script)

Uso:
    python3 mqtt/suscriptor_almacenador.py

Variables de entorno opcionales:
    MQTT_BROKER, MQTT_PUERTO

Compatible con paho-mqtt 1.6.x y 2.x.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
from pathlib import Path

import paho.mqtt.client as mqtt

try:  # paho-mqtt >= 2.0
    from paho.mqtt.client import CallbackAPIVersion
except ImportError:  # paho-mqtt 1.x
    CallbackAPIVersion = None

BROKER = os.getenv("MQTT_BROKER", "localhost")
PUERTO = int(os.getenv("MQTT_PUERTO", "1883"))
CLIENT_ID = "suscriptor-almacenador"
QOS = 1
DB_PATH = Path(__file__).resolve().with_name("telemetria.db")

TOPICS = (
    "flota/+/gps",
    "flota/+/temperatura",
    "flota/+/combustible",
)


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


class Almacenador:
    """Encapsula la conexion SQLite y las inserciones de telemetria."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._crear_esquema()

    def _crear_esquema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gps_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    lat REAL,
                    lng REAL,
                    speed REAL,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS temp_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    temperature REAL,
                    unit TEXT,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS fuel_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id TEXT,
                    fuel_level REAL,
                    unit TEXT,
                    timestamp TEXT
                );
                """
            )
            self._conn.commit()

    @staticmethod
    def _numero(datos: dict, clave: str) -> float:
        valor = datos.get(clave)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"campo '{clave}' ausente o no numerico")
        return float(valor)

    def _insertar(self, sql: str, parametros: tuple) -> bool:
        with self._lock:
            try:
                self._conn.execute(sql, parametros)
                self._conn.commit()
                return True
            except sqlite3.Error as exc:
                self._conn.rollback()
                print(f"[DB] Error de SQLite: {exc}", file=sys.stderr)
                return False

    def procesar(self, topic: str, payload: bytes) -> None:
        """Valida, alerta e inserta un mensaje recibido desde MQTT."""
        partes = topic.split("/")
        if len(partes) != 3 or partes[0] != "flota":
            print(f"[WARN] Topic no reconocido: {topic}", file=sys.stderr)
            return

        sensor = partes[2]
        try:
            datos = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"[WARN] JSON invalido en {topic}: {exc}", file=sys.stderr)
            return

        if not isinstance(datos, dict):
            print(f"[WARN] El payload de {topic} no es un objeto JSON", file=sys.stderr)
            return

        vehicle_id = str(datos.get("vehicle_id") or partes[1])
        timestamp = str(datos.get("timestamp", ""))

        if sensor == "gps":
            self._procesar_gps(vehicle_id, timestamp, datos)
        elif sensor == "temperatura":
            self._procesar_temperatura(vehicle_id, timestamp, datos)
        elif sensor == "combustible":
            self._procesar_combustible(vehicle_id, timestamp, datos)
        else:
            print(f"[WARN] Sensor desconocido en {topic}", file=sys.stderr)

    def _procesar_gps(self, vehicle_id: str, timestamp: str, datos: dict) -> None:
        try:
            lat = self._numero(datos, "lat")
            lng = self._numero(datos, "lng")
            speed = self._numero(datos, "speed")
        except ValueError as exc:
            print(f"[WARN] GPS invalido de {vehicle_id}: {exc}", file=sys.stderr)
            return

        if self._insertar(
            "INSERT INTO gps_data (vehicle_id, lat, lng, speed, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (vehicle_id, lat, lng, speed, timestamp),
        ):
            print(f"[GPS] {vehicle_id}: lat={lat}, lng={lng}, speed={speed}")

    def _procesar_temperatura(
        self, vehicle_id: str, timestamp: str, datos: dict
    ) -> None:
        try:
            temperature = self._numero(datos, "temperature")
        except ValueError as exc:
            print(f"[WARN] Temperatura invalida de {vehicle_id}: {exc}", file=sys.stderr)
            return

        unit = str(datos.get("unit", "celsius"))
        if temperature > 4:
            print(f"ALERTA: {vehicle_id} temperatura alta")

        if self._insertar(
            "INSERT INTO temp_data (vehicle_id, temperature, unit, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (vehicle_id, temperature, unit, timestamp),
        ):
            print(f"[TEMP] {vehicle_id}: temperature={temperature} {unit}")

    def _procesar_combustible(
        self, vehicle_id: str, timestamp: str, datos: dict
    ) -> None:
        try:
            fuel_level = self._numero(datos, "fuel_level")
        except ValueError as exc:
            print(f"[WARN] Combustible invalido de {vehicle_id}: {exc}", file=sys.stderr)
            return

        unit = str(datos.get("unit", "percent"))
        if fuel_level < 20:
            print(f"ALERTA: {vehicle_id} combustible bajo")

        if self._insertar(
            "INSERT INTO fuel_data (vehicle_id, fuel_level, unit, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (vehicle_id, fuel_level, unit, timestamp),
        ):
            print(f"[FUEL] {vehicle_id}: fuel_level={fuel_level} {unit}")

    def cerrar(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except sqlite3.Error:
                pass


def main() -> int:
    almacenador = Almacenador(DB_PATH)
    cliente = crear_cliente()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[MQTT] Conexion rechazada (rc={rc})", file=sys.stderr)
            return
        client.subscribe([(topic, QOS) for topic in TOPICS])
        print(f"[MQTT] Conectado a {BROKER}:{PUERTO}")
        print("[MQTT] Suscrito a: " + ", ".join(TOPICS))

    def on_message(client, userdata, msg):
        almacenador.procesar(msg.topic, msg.payload)

    def on_disconnect(client, userdata, *args):
        print("[MQTT] Desconectado del broker; paho intentara reconectar...")

    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.on_disconnect = on_disconnect

    try:
        cliente.connect(BROKER, PUERTO, keepalive=60)
        print(f"[DB] Base de datos: {DB_PATH}")
        print("[SUB] Ctrl+C para salir\n")
        cliente.loop_forever()
    except OSError as exc:
        print(
            f"[MQTT] No se pudo conectar a {BROKER}:{PUERTO}: {exc}\n"
            "       Verifica que el contenedor este arriba: docker compose up -d",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\n[SUB] Ctrl+C recibido, cerrando...")
    finally:
        cliente.disconnect()
        almacenador.cerrar()
        print("[SUB] Base de datos cerrada.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
