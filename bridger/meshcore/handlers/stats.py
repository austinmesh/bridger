"""Handler for MeshCore status messages (observer/gateway health)."""

from bridger.dataclasses import MeshCoreStatsCorePoint, MeshCoreStatsRadioPoint, MeshCoreStatusPoint
from bridger.meshcore.base import MeshCoreHandler
from bridger.meshcore.handler_registry import meshcore_handler


@meshcore_handler("status")
class StatusHandler(MeshCoreHandler):
    """Handler for observer/gateway status messages.

    Status messages contain:
        - Online/offline status
        - Device info (firmware, model, radio config)
        - Stats: battery, uptime, noise floor, air time, etc.

    Produces multiple data points per message to maintain
    separate InfluxDB measurements for core and radio stats.
    """

    def handle(self):
        if not isinstance(self.payload, dict):
            return None

        stats = self.payload.get("stats", {})
        points = []

        # Observer core stats
        core_point = MeshCoreStatsCorePoint(
            public_key=self.public_key,
            iata=self.iata,
            origin=self.origin,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            battery_mv=stats.get("battery_mv"),
            uptime_secs=stats.get("uptime_secs"),
            queue_len=stats.get("queue_len"),
            debug_flags=stats.get("debug_flags"),
            recv_errors=stats.get("recv_errors"),
        )
        points.append(core_point)

        # Observer radio stats
        radio_point = MeshCoreStatsRadioPoint(
            public_key=self.public_key,
            iata=self.iata,
            origin=self.origin,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            noise_floor=stats.get("noise_floor"),
            tx_air_secs=stats.get("tx_air_secs"),
            rx_air_secs=stats.get("rx_air_secs"),
        )
        points.append(radio_point)

        # Observer online/offline status
        status_point = MeshCoreStatusPoint(
            public_key=self.public_key,
            iata=self.iata,
            origin=self.origin,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            status=self.payload.get("status"),
            source=self.payload.get("source"),
            client_version=self.payload.get("client_version"),
            radio=self.payload.get("radio"),
        )
        points.append(status_point)

        return points
