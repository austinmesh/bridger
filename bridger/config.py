import hashlib
import os

from meshcoredecoder.crypto import ChannelCrypto

MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.110")
MQTT_USER = os.getenv("MQTT_USER", "station")
MQTT_PASS = os.getenv("MQTT_PASS")
MQTT_PORT = os.getenv("MQTT_PORT", 1883)
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "egr/home/2/e/#")
INFLUXDB_V2_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "meshtastic")
INFLUXDB_V2_WRITE_PRECISION = os.getenv("INFLUXDB_V2_WRITE_PRECISION", "s")  # s, ms, us, or ns
MESHTASTIC_API_ENDPOINT = "https://api.meshtastic.org"
MESHTASTIC_API_CACHE_TTL = int(os.getenv("MESHTASTIC_API_CACHE_TTL", 3600 * 6))  # Default to 6 hours if not set

# MeshCore configuration
MESHCORE_IATA = os.getenv("MESHCORE_IATA", "AUS")
MESHCORE_MQTT_TOPIC = os.getenv("MESHCORE_MQTT_TOPIC", "meshcore/#")
MESHCORE_INFLUXDB_BUCKET = os.getenv("MESHCORE_INFLUXDB_BUCKET", "meshcore")
MESHCORE_ENABLED = os.getenv("MESHCORE_ENABLED", "true").lower() == "true"

# MeshCore test message configuration
MESHCORE_TEST_CHANNEL_NAME = os.getenv(
    "MESHCORE_TEST_CHANNEL_NAME", "testing"
)  # e.g. "testing" (# prefix added automatically)
MESHCORE_TEST_CHANNEL_KEY = None
MESHCORE_TEST_CHANNEL_HASH = None

if MESHCORE_TEST_CHANNEL_NAME:
    MESHCORE_TEST_CHANNEL_KEY = hashlib.sha256(f"#{MESHCORE_TEST_CHANNEL_NAME}".encode()).hexdigest()[:32]
    MESHCORE_TEST_CHANNEL_HASH = ChannelCrypto.calculate_channel_hash(MESHCORE_TEST_CHANNEL_KEY)
