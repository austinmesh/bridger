from influxdb_client import InfluxDBClient
from paho.mqtt.client import CallbackAPIVersion

from bridger.config import MQTT_BROKER, MQTT_PASS, MQTT_PORT, MQTT_USER
from bridger.log import logger
from bridger.mqtt import BridgerMQTT

if __name__ == "__main__":
    try:
        influx_client: InfluxDBClient = InfluxDBClient.from_env_properties()
        ready = influx_client.ping()
        influx_url = influx_client.url

        if not ready:
            raise ConnectionError(f"Cannot ping InfluxDB at {influx_url}. Is it running?")

        client = BridgerMQTT(influx_client, CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.reconnect_delay_set(min_delay=5, max_delay=120)
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        client.disconnect()
        client.loop_stop()
        client = None
    except ConnectionError as e:
        logger.error(e)
