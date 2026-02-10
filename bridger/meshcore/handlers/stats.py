"""Handlers for MeshCore stats messages (JSON data)."""

from bridger.dataclasses import MeshCoreStatsCorePoint, MeshCoreStatsPacketsPoint, MeshCoreStatsRadioPoint
from bridger.meshcore.base import MeshCoreHandler
from bridger.meshcore.handler_registry import meshcore_handler


@meshcore_handler("stats/core")
class StatsCoreHandler(MeshCoreHandler):
    """Handler for core stats (battery, uptime, errors, queue_len)."""

    def handle(self):
        if not isinstance(self.payload, dict):
            return None

        return MeshCoreStatsCorePoint(
            public_key=self.public_key,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            battery_mv=self.payload.get("battery_mv"),
            uptime_secs=self.payload.get("uptime_secs"),
            errors=self.payload.get("errors"),
            queue_len=self.payload.get("queue_len"),
        )


@meshcore_handler("stats/radio")
class StatsRadioHandler(MeshCoreHandler):
    """Handler for radio stats (noise_floor, rssi, snr, air time)."""

    def handle(self):
        if not isinstance(self.payload, dict):
            return None

        return MeshCoreStatsRadioPoint(
            public_key=self.public_key,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            noise_floor=self.payload.get("noise_floor"),
            last_rssi=self.payload.get("last_rssi"),
            last_snr=self.payload.get("last_snr"),
            tx_air_secs=self.payload.get("tx_air_secs"),
            rx_air_secs=self.payload.get("rx_air_secs"),
        )


@meshcore_handler("stats/packets")
class StatsPacketsHandler(MeshCoreHandler):
    """Handler for packet stats (recv, sent, flood/direct counts)."""

    def handle(self):
        if not isinstance(self.payload, dict):
            return None

        return MeshCoreStatsPacketsPoint(
            public_key=self.public_key,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            recv=self.payload.get("recv"),
            sent=self.payload.get("sent"),
            flood_tx=self.payload.get("flood_tx"),
            direct_tx=self.payload.get("direct_tx"),
            flood_rx=self.payload.get("flood_rx"),
            direct_rx=self.payload.get("direct_rx"),
        )
