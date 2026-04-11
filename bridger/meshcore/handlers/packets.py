"""Handler for MeshCore packet messages (HEX-encoded data)."""

from bridger.dataclasses import MeshCoreAdvertPoint, MeshCorePacketPoint, MeshCoreTracePoint
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
            return self._handle_advert()
        elif payload_type == PAYLOAD_TYPE_TRACE:
            return self._handle_trace()
        else:
            return self._handle_generic()

    def _get_envelope(self) -> dict:
        """Extract envelope metadata from the relay."""
        return self.payload.get("envelope", {})

    def _handle_advert(self):
        """Handle Advert packets (PayloadType.Advert = 4)."""
        payload_decoded = self.payload.get("payload", {}).get("decoded", {})
        app_data = payload_decoded.get("appData", {})
        location = app_data.get("location", {})
        envelope = self._get_envelope()

        return MeshCoreAdvertPoint(
            public_key=self.public_key,
            iata=self.iata,
            origin=self.origin,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
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
            # Envelope metadata
            snr=envelope.get("SNR"),
            rssi=envelope.get("RSSI"),
            direction=envelope.get("direction"),
            mqtt_hash=envelope.get("hash"),
        )

    def _handle_trace(self):
        """Handle Trace packets (PayloadType.Trace = 9)."""
        payload_decoded = self.payload.get("payload", {}).get("decoded", {})
        path_hashes = payload_decoded.get("pathHashes", [])
        envelope = self._get_envelope()

        return MeshCoreTracePoint(
            public_key=self.public_key,
            iata=self.iata,
            origin=self.origin,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
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
            # Envelope metadata
            snr=envelope.get("SNR"),
            rssi=envelope.get("RSSI"),
            direction=envelope.get("direction"),
            mqtt_hash=envelope.get("hash"),
        )

    def _handle_generic(self):
        """Handle unknown or minimal packet types (fallback)."""
        envelope = self._get_envelope()

        return MeshCorePacketPoint(
            public_key=self.public_key,
            iata=self.iata,
            origin=self.origin,
            name=self.metadata.name,
            ver=self.metadata.ver,
            board=self.metadata.board,
            message_hash=self.payload.get("messageHash"),
            route_type=self.payload.get("routeType"),
            payload_type=self.payload.get("payloadType"),
            payload_version=self.payload.get("payloadVersion"),
            path_length=self.payload.get("pathLength"),
            total_bytes=self.payload.get("totalBytes"),
            is_valid=self.payload.get("isValid"),
            # Envelope metadata
            snr=envelope.get("SNR"),
            rssi=envelope.get("RSSI"),
            direction=envelope.get("direction"),
            mqtt_hash=envelope.get("hash"),
        )
