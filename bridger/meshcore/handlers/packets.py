"""Handler for MeshCore packet messages (HEX-encoded data)."""

from bridger.dataclasses import (
    MeshCoreAdvertPoint,
    MeshCoreHopPoint,
    MeshCorePacketPoint,
    MeshCoreTracePoint,
)
from bridger.meshcore.base import MeshCoreHandler
from bridger.meshcore.handler_registry import meshcore_handler

# PayloadType enum values from Python meshcoredecoder
PAYLOAD_TYPE_ADVERT = 4
PAYLOAD_TYPE_TRACE = 9


@meshcore_handler("packets")
class PacketsHandler(MeshCoreHandler):
    """Handler for decoded MeshCore packets.

    The payload is already decoded by meshcoredecoder in the processor.
    We extract metadata only (no message content for privacy).
    Dispatches to specific handlers based on payload type.
    """

    def handle(self):
        if not isinstance(self.payload, dict):
            return None

        # Skip if there was an error decoding
        if "error" in self.payload:
            return None

        payload_type = self.payload.get("payloadType")

        if payload_type == PAYLOAD_TYPE_ADVERT:
            main_point = self._handle_advert()
        elif payload_type == PAYLOAD_TYPE_TRACE:
            main_point = self._handle_trace()
        else:
            main_point = self._handle_generic()

        if not main_point:
            return None

        # Generate hop points for path data
        hop_points = self._build_hop_points()

        if hop_points:
            return [main_point] + hop_points
        return main_point

    def _get_envelope(self) -> dict:
        """Extract envelope metadata from the relay."""
        return self.payload.get("envelope", {})

    def _envelope_kwargs(self) -> dict:
        """Build kwargs for MeshCorePacket base-class envelope fields."""
        envelope = self._get_envelope()
        return {
            "public_key": self.public_key,
            "iata": self.iata,
            "origin": self.origin,
            "mqtt_hash": envelope.get("hash"),
            "direction": envelope.get("direction"),
            "route": envelope.get("route"),
            "rx_snr": envelope.get("SNR"),
            "rx_rssi": envelope.get("RSSI"),
            "score": envelope.get("score"),
            "duration": envelope.get("duration"),
        }

    def _build_hop_points(self) -> list:
        """Build individual mc_hop points for each hop in the packet's path."""
        path = self.payload.get("path")
        if not path or not isinstance(path, list):
            return []

        path_length = len(path)
        base_kwargs = self._envelope_kwargs()
        points = []

        for index, hop_hash in enumerate(path):
            points.append(
                MeshCoreHopPoint(
                    **base_kwargs,
                    hop_hash=str(hop_hash),
                    hop_index=index,
                    path_length=path_length,
                )
            )

        return points

    def _handle_advert(self):
        """Handle Advert packets (PayloadType.Advert = 4)."""
        payload_decoded = self.payload.get("payload", {}).get("decoded", {})
        app_data = payload_decoded.get("appData", {})
        location = app_data.get("location", {})

        return MeshCoreAdvertPoint(
            **self._envelope_kwargs(),
            # Packet-level fields
            message_hash=self.payload.get("messageHash"),
            route_type=self.payload.get("routeType"),
            payload_type=self.payload.get("payloadType"),
            path_length=self.payload.get("pathLength"),
            total_bytes=self.payload.get("totalBytes"),
            is_valid=self.payload.get("isValid"),
            # Advert-specific fields
            sender_public_key=payload_decoded.get("publicKey"),
            timestamp=payload_decoded.get("timestamp"),
            # AppData fields
            device_name=app_data.get("name"),
            device_role=app_data.get("deviceRole"),
            flags=app_data.get("flags"),
            has_location=app_data.get("hasLocation"),
            latitude=location.get("latitude") if location else None,
            longitude=location.get("longitude") if location else None,
        )

    def _handle_trace(self):
        """Handle Trace packets (PayloadType.Trace = 9)."""
        payload_decoded = self.payload.get("payload", {}).get("decoded", {})
        path_hashes = payload_decoded.get("pathHashes", [])

        return MeshCoreTracePoint(
            **self._envelope_kwargs(),
            # Packet-level fields
            message_hash=self.payload.get("messageHash"),
            route_type=self.payload.get("routeType"),
            payload_type=self.payload.get("payloadType"),
            path_length=self.payload.get("pathLength"),
            total_bytes=self.payload.get("totalBytes"),
            is_valid=self.payload.get("isValid"),
            # Trace-specific fields
            trace_tag=payload_decoded.get("traceTag"),
            auth_code=payload_decoded.get("authCode"),
            flags=payload_decoded.get("flags"),
            path_hashes=",".join(path_hashes) if path_hashes else None,
        )

    def _handle_generic(self):
        """Handle unknown or minimal packet types (fallback)."""
        return MeshCorePacketPoint(
            **self._envelope_kwargs(),
            message_hash=self.payload.get("messageHash"),
            route_type=self.payload.get("routeType"),
            payload_type=self.payload.get("payloadType"),
            payload_version=self.payload.get("payloadVersion"),
            path_length=self.payload.get("pathLength"),
            total_bytes=self.payload.get("totalBytes"),
            is_valid=self.payload.get("isValid"),
        )
