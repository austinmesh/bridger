import os

import sentry_sdk
from dotenv import load_dotenv
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

load_dotenv()

denylist = DEFAULT_DENYLIST + [
    "DISCORD_BOT_TOKEN",
    "EMQX_API_KEY",
    "EMQX_SECRET_KEY",
    "MQTT_PASS",
    "INFLUXDB_V2_TOKEN",
    "BRIDGER_PKI_PRIVATE_KEY",
    "BRIDGER_PKI_PUBLIC_KEY",
    "EMQX_NODE__COOKIE",
]

sentry_sdk.init(
    send_default_pii=False,
    traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0.1)),
    profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", 0.1)),
    event_scrubber=EventScrubber(denylist=denylist, recursive=True),
)
