import sentry_sdk
from dotenv import load_dotenv

load_dotenv()

sentry_sdk.init(
    enable_tracing=True,
    send_default_pii=True,
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
)
