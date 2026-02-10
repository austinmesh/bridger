"""MeshCore message handlers."""

# Import all handlers to register them with the registry
from bridger.meshcore.handlers.info import InfoHandler  # noqa: F401
from bridger.meshcore.handlers.packets import PacketsHandler  # noqa: F401
from bridger.meshcore.handlers.stats import StatsCoreHandler, StatsPacketsHandler, StatsRadioHandler  # noqa: F401
