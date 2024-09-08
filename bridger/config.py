import os

MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.110")
MQTT_USER = os.getenv("MQTT_USER", "station")
MQTT_PASS = os.getenv("MQTT_PASS")
MQTT_PORT = os.getenv("MQTT_PORT", 1883)
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "egr/home/2/e/#")
INFLUXDB_V2_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "meshtastic")
INFLUXDB_V2_WRITE_PRECISION = os.getenv("INFLUXDB_V2_WRITE_PRECISION", "s")  # s, ms, us, or ns
MESHTASTIC_API_ENDPOINT = "https://api.meshtastic.org"
MESHTASTIC_API_CACHE_TTL = int(os.getenv("MESHTASTIC_API_CACHE_TTL", 3600 * 6))  # Default to 6 hours if not set
