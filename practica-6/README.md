# Fleet Monitor — Spring Boot + RabbitMQ + MQTT

Práctica integrada de monitoreo de flota. Combina la aplicación Java Spring Boot
(actividades 5–8) con la capa IoT de Mosquitto, el simulador de sensores, el
suscriptor SQLite y el puente MQTT → RabbitMQ.

## Arquitectura

```text
mqtt/simulador_sensores.py
        │ MQTT (flota/#)
        ▼
mosquitto_broker :1883
        │
        ├──────────────► mqtt/suscriptor_almacenador.py ──► mqtt/telemetria.db
        │
        └──────────────► mqtt/mqtt_rabbitmq_bridge.py ──► RabbitMQ :5672
                                                              │
                                                              ▼
                                                    exchange.fleet (direct)
                                                      ├── gps.routing
                                                      ├── temp.alert
                                                      └── fuel.routing
                                                              │
                                                              ▼
                                              Spring Boot fleet-monitor :8080
                                              ├── GpsConsumer
                                              ├── AlertConsumer → cola.notificaciones
                                              └── FleetController (REST)
```

## Estructura

```text
practica_6/
├── docker-compose.yml              # Mosquitto + RabbitMQ
├── docker-compose-rabbitmq.yml     # compose anterior (legado, no usar)
├── mosquitto/
│   └── config/mosquitto.conf
├── mqtt/
│   ├── simulador_sensores.py
│   ├── suscriptor_almacenador.py
│   ├── mqtt_rabbitmq_bridge.py
│   └── requirements.txt
├── src/main/java/com/fleet/monitor/
│   ├── config/RabbitMQConfig.java
│   ├── consumer/GpsConsumer.java
│   ├── consumer/AlertConsumer.java
│   ├── controller/FleetController.java
│   ├── model/GpsMessage.java
│   └── FleetMonitorApplication.java
├── pom.xml
└── README.md
```

## Requisitos

- Docker y Docker Compose.
- Java 17 o superior (el proyecto compila con `release 17`).
- Python 3 con `venv`.
- Maven.

## 1. Levantar la infraestructura

Desde la raíz del proyecto:

```bash
docker compose up -d
docker compose ps
```

Servicios esperados:

- `mosquitto_broker`: puertos `1883` (MQTT) y `9001`.
- `rabbitmq_broker`: puertos `5672` (AMQP) y `15672` (panel web).

Credenciales de RabbitMQ:

```text
Usuario: admin
Contraseña: admin123
Panel: http://localhost:15672
```

> Si antes estaba corriendo el Mosquitto de `/home/israel/practica_mqtt`, detén
> ese proyecto para liberar el puerto `1883`:
>
> ```bash
> docker compose -f /home/israel/practica_mqtt/docker-compose.yml down
> ```

## 2. Preparar el entorno Python

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r mqtt/requirements.txt
```

Verificación:

```bash
.venv/bin/python -c "import paho.mqtt, pika; print('paho', paho.mqtt.__version__, 'pika', pika.__version__)"
```

## 3. Arrancar la aplicación Spring

En una terminal:

```bash
mvn spring-boot:run
```

Espera el mensaje:

```text
Started FleetMonitorApplication in ... seconds
```

Al conectar, la aplicación declara el exchange, las cuatro colas y los bindings.

## 4. Ejecutar la capa MQTT

En tres terminales separadas, desde la raíz del proyecto:

**Terminal 1 — almacenador SQLite:**

```bash
.venv/bin/python mqtt/suscriptor_almacenador.py
```

**Terminal 2 — puente MQTT → RabbitMQ:**

```bash
.venv/bin/python mqtt/mqtt_rabbitmq_bridge.py
```

**Terminal 3 — simulador de sensores:**

```bash
.venv/bin/python mqtt/simulador_sensores.py
```

El simulador publica 9 mensajes cada 5 segundos (GPS, temperatura y combustible
para `VH-001`, `VH-002` y `VH-003`).

Detén cada proceso con `Ctrl+C`.

## 5. Verificar el flujo completo

### Logs de Spring

Deben aparecer entradas como:

```text
GPS recibido: {...}
ALERTA TEMPERATURA: {...}
ALERTA COMBUSTIBLE: {...}
```

### Colas de RabbitMQ

```bash
docker exec rabbitmq_broker rabbitmqctl list_queues name durable messages
```

Deben existir:

- `cola.gps.telemetria`
- `cola.alertas.temperatura`
- `cola.combustible.nivel`
- `cola.notificaciones`

Las alertas de temperatura y combustible se reenvían a `cola.notificaciones`
desde `AlertConsumer`.

### SQLite

```bash
sqlite3 mqtt/telemetria.db ".tables"
sqlite3 -header -column mqtt/telemetria.db \
  "SELECT id, vehicle_id, lat, lng, speed, timestamp FROM gps_data ORDER BY id DESC LIMIT 9;"
```

### API REST

```bash
curl http://localhost:8080/api/fleet/status
curl http://localhost:8080/api/fleet/vehicle/VH-001/telemetria
```

## 6. Probar alertas manualmente

Con el suscriptor, el puente y Spring en ejecución:

```bash
docker exec mosquitto_broker mosquitto_pub -h localhost \
  -t 'flota/VH-001/temperatura' \
  -m '{"vehicle_id":"VH-001","timestamp":"2026-11-06T12:00:00Z","temperature":7.5,"unit":"celsius"}'

docker exec mosquitto_broker mosquitto_pub -h localhost \
  -t 'flota/VH-001/combustible' \
  -m '{"vehicle_id":"VH-001","timestamp":"2026-11-06T12:00:00Z","fuel_level":10.0,"unit":"percent"}'

docker exec mosquitto_broker mosquitto_pub -h localhost \
  -t 'flota/VH-001/gps' \
  -m '{"vehicle_id":"VH-001","timestamp":"2026-11-06T12:00:00Z","lat":-2.1709,"lng":-79.9224,"speed":45.5}'
```

## 7. Ejecutar en máquinas separadas

Las variables de entorno permiten apuntar a brokers remotos:

```bash
# Spring apuntando a un RabbitMQ remoto
SPRING_RABBITMQ_HOST=192.168.1.50 mvn spring-boot:run

# Scripts apuntando a Mosquitto remoto
MQTT_BROKER=192.168.1.50 .venv/bin/python mqtt/simulador_sensores.py

# Puente apuntando a ambos brokers
MQTT_BROKER=192.168.1.50 RABBITMQ_HOST=192.168.1.50 \
  .venv/bin/python mqtt/mqtt_rabbitmq_bridge.py
```

Los puertos que deben estar accesibles en la máquina del broker son:

- `1883` MQTT
- `5672` AMQP
- `15672` panel de RabbitMQ

## 8. Detener y limpiar

Detén los scripts Python con `Ctrl+C` y la aplicación Spring con `Ctrl+C`.

```bash
docker compose stop
```

Para eliminar contenedores:

```bash
docker compose down
```

Para eliminar también los volúmenes (colas y datos de Mosquitto):

```bash
docker compose down -v
```

Para reiniciar la base SQLite:

```bash
rm -f mqtt/telemetria.db mqtt/telemetria.db-wal mqtt/telemetria.db-shm
```

## Solución de problemas

### `ModuleNotFoundError: No module named 'pika'`

Instala las dependencias dentro del entorno virtual:

```bash
.venv/bin/pip install -r mqtt/requirements.txt
```

### `ACCESS_REFUSED` en RabbitMQ

Verifica que RabbitMQ se haya recreado con las credenciales de este proyecto:

```bash
docker compose down
docker compose up -d
```

### `PRECONDITION_FAILED` al declarar una cola

Existe una cola con parámetros distintos. Elimina el volumen y recrea:

```bash
docker compose down -v
docker compose up -d
```

### Puerto `1883` ocupado

Detén el Mosquitto anterior:

```bash
docker compose -f /home/israel/practica_mqtt/docker-compose.yml down
```

### `database is locked` en SQLite

Ejecuta un solo `suscriptor_almacenador.py` a la vez. SQLite solo admite un
escritor simultáneo.
