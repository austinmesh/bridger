"""Handler registry for MeshCore data types."""

from collections import defaultdict
from typing import Type

MESHCORE_HANDLER_MAP = defaultdict(list)


def meshcore_handler(data_type: str):
    """Decorator to register a MeshCore handler for a data type.

    Usage:
        @meshcore_handler("stats/core")
        class StatsCoreHandler(MeshCoreHandler):
            def handle(self):
                ...
    """

    def decorator(cls: Type) -> Type:
        MESHCORE_HANDLER_MAP[data_type].append(cls)
        return cls

    return decorator
