import os

# Every configuration input lives here so there is one place to read to know what the
# application is tunable by, and so tests can monkeypatch a single module.
#
# Deliberately flat module-level constants rather than a settings object: consumers do
# `from bridger.config import X`, which makes a copy per module, and tests/conftest.py relies
# on being able to walk sys.modules and patch each of those copies.
#
# Not moved here: the SENTRY_* reads in bridger/__init__.py, which runs before this module
# and calls load_dotenv().

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.110")
MQTT_USER = os.getenv("MQTT_USER", "station")
MQTT_PASS = os.getenv("MQTT_PASS")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "egr/home/2/e/#")
# Suffixed per process at the point of use: an identical client id across the bridge and the
# bot makes the broker kick one off whenever the other connects.
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "bridger")

# InfluxDB. The URL, org and token are read by influxdb-client itself, from
# INFLUXDB_V2_URL / INFLUXDB_V2_ORG / INFLUXDB_V2_TOKEN, via from_env_properties().
INFLUXDB_V2_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "meshtastic")
INFLUXDB_V2_WRITE_PRECISION = os.getenv("INFLUXDB_V2_WRITE_PRECISION", "s")  # s, ms, us, or ns

# Meshtastic
MESHTASTIC_API_ENDPOINT = "https://api.meshtastic.org"
MESHTASTIC_API_CACHE_TTL = int(os.getenv("MESHTASTIC_API_CACHE_TTL", 3600 * 6))
MESHTASTIC_API_TIMEOUT = float(os.getenv("MESHTASTIC_API_TIMEOUT", 10))
# Base64-encoded 16-byte AES-128 key. The default is the Meshtastic default channel PSK,
# which is what the "AQ==" shorthand expands to.
MESHTASTIC_KEY = os.getenv("MESHTASTIC_KEY", "1PG7OiApB1nwvP+rz05pAQ==")

# EMQX
EMQX_API_KEY = os.getenv("EMQX_API_KEY")
EMQX_SECRET_KEY = os.getenv("EMQX_SECRET_KEY")
EMQX_URL = os.getenv("EMQX_URL")
# Without a timeout, a hung EMQX hangs the Discord bot indefinitely rather than failing one
# command. 3.05s connect is the requests convention: just over the TCP retransmit window.
EMQX_HTTP_CONNECT_TIMEOUT = float(os.getenv("EMQX_HTTP_CONNECT_TIMEOUT", 3.05))
EMQX_HTTP_READ_TIMEOUT = float(os.getenv("EMQX_HTTP_READ_TIMEOUT", 10))
EMQX_HTTP_TIMEOUT = (EMQX_HTTP_CONNECT_TIMEOUT, EMQX_HTTP_READ_TIMEOUT)

# Discord. DISCORD_BOT_TOKEN and DISCORD_BOT_OWNER_ID are deliberately read at call time in
# bridger/bot.py rather than captured here, so they stay patchable and are not held in module
# state for the life of the process.
BRIDGER_ADMIN_ROLE = os.getenv("BRIDGER_ADMIN_ROLE", "Bridger Admin")
MQTT_TEST_CHANNEL = os.getenv("MQTT_TEST_CHANNEL", "+")
MQTT_TEST_CHANNEL_ID = int(os.getenv("MQTT_TEST_CHANNEL_ID", 1253788609316913265))
TEST_MESSAGE_MATCH_ALL = os.getenv("TEST_MESSAGE_MATCH_ALL", "false").lower() == "true"

# Discord bot caches. The node list TTL is deliberately twice its refresh interval, so one
# failed background refresh never empties the cache and drops users onto the blocking path.
NODE_CACHE_TTL = int(os.getenv("BRIDGER_NODE_CACHE_TTL", 600))
NODE_CACHE_REFRESH_SECONDS = int(os.getenv("BRIDGER_NODE_CACHE_REFRESH", 300))
GATEWAY_CACHE_TTL = int(os.getenv("BRIDGER_GATEWAY_CACHE_TTL", 30))
NODE_INFO_CACHE_TTL = int(os.getenv("BRIDGER_NODE_INFO_CACHE_TTL", 300))
# Discord gives autocomplete roughly 3s; leave headroom to answer with something.
AUTOCOMPLETE_DEADLINE = float(os.getenv("BRIDGER_AUTOCOMPLETE_DEADLINE", 2.0))

# testmsg MQTT supervisor backoff
MQTT_RESTART_MIN_DELAY = float(os.getenv("BRIDGER_MQTT_RESTART_MIN_DELAY", 1))
MQTT_RESTART_MAX_DELAY = float(os.getenv("BRIDGER_MQTT_RESTART_MAX_DELAY", 300))
MQTT_HEALTHY_SECONDS = float(os.getenv("BRIDGER_MQTT_HEALTHY_SECONDS", 60))

# Logging and release. LOGURU_LEVEL is not listed here because loguru reads it itself: it
# backs the default `level` of logger.add(), so it sets the threshold for both the stderr
# handler loguru installs and the file sink added in bridger/log.py.
LOG_PATH = os.getenv("LOG_PATH", "logs/bridger.log")
VERSION = os.getenv("SENTRY_RELEASE", "development")
