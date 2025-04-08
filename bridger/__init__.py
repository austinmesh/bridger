import os

import sentry_sdk
from dotenv import load_dotenv

load_dotenv()

sentry_sdk.init(
    send_default_pii=True,
    traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0.1)),
    profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", 0.1)),
)
