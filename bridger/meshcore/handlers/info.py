"""Handler for MeshCore info messages (string data)."""

from bridger.dataclasses import MeshCoreInfoPoint
from bridger.meshcore.base import MeshCoreHandler
from bridger.meshcore.handler_registry import meshcore_handler


@meshcore_handler("info")
class InfoHandler(MeshCoreHandler):
    """Handler for device info messages (version, board, public key, etc.)."""

    def handle(self):
        # payload is a string like "v1.11.0 (Build: 30 Nov 2025)" or "RAK 11200"
        if not isinstance(self.payload, str):
            return None

        return MeshCoreInfoPoint(
            public_key=self.public_key,
            info_type="info",
            value=self.payload,
        )
