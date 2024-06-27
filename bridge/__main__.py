import os

from paho.mqtt.client import CallbackAPIVersion

from bridge.mqtt import MeshBridge

MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.110")
MQTT_USER = os.getenv("MQTT_USER", "station")
MQTT_PASS = os.getenv("MQTT_PASS")
MQTT_PORT = os.getenv("MQTT_PORT", 1883)


if __name__ == "__main__":
    try:
        client = MeshBridge(CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.reconnect_delay_set(min_delay=5, max_delay=120)
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        client.disconnect()
        client.loop_stop()
        client = None
