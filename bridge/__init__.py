import sentry_sdk
from dotenv import load_dotenv

__VERSION__ = "0.1.13"
__APP_NAME__ = "bridger"

load_dotenv()

sentry_sdk.init(
    enable_tracing=True,
    send_default_pii=True,
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    release=f"{__APP_NAME__}@{__VERSION__}",
)
