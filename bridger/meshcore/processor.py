"""MeshCore packet processor for handling MQTT messages."""

import json
from dataclasses import dataclass
from typing import Any, Optional, Union

from meshcoredecoder.types.crypto import DecryptionOptions

from bridger.config import MESHCORE_MQTT_TOPIC
from bridger.log import logger
from bridger.meshcore.handler_registry import MESHCORE_HANDLER_MAP


class MeshCoreProcessorError(Exception):
    """Exception raised when processing MeshCore messages fails."""

    def __init__(self, message: str, data_type: str = None):
        super().__init__(message)
        self.data_type = data_type


@dataclass
class MeshCoreMetadata:
    """Common metadata from MeshCore messages."""

    public_key: str
    iata: str
    origin: Optional[str] = None
    name: Optional[str] = None
    ver: Optional[str] = None
    board: Optional[str] = None


class MCPacketProcessor:
    """Processor for MeshCore MQTT messages.

    Topic format: meshcore/{IATA}/{PUBLIC_KEY}/{packets|status}

    Message types:
        - packets: Raw mesh packet data with envelope metadata (SNR, RSSI, etc.)
        - status: Observer/gateway health status with device stats
    """

    # Extract the base prefix from config (remove the wildcard)
    TOPIC_PREFIX = MESHCORE_MQTT_TOPIC.rstrip("#")

    def __init__(self, topic: str, payload: bytes, decryption_options: Optional[DecryptionOptions] = None):
        self.topic = topic
        self.raw_payload = payload
        self.decryption_options = decryption_options
        self._parsed_json: Optional[dict] = None
        self._metadata: Optional[MeshCoreMetadata] = None
        self._data_type: Optional[str] = None
        self._iata: Optional[str] = None
        self._public_key: Optional[str] = None
        self._parse_topic()
        self._parse_payload()

    def _parse_topic(self):
        """Parse topic to extract iata, public_key, data_type.

        Topic format: {prefix}{IATA}/{PUBLIC_KEY}/{packets|status}
        """
        relative = self.topic[len(self.TOPIC_PREFIX) :]
        parts = relative.split("/")

        if len(parts) != 3:
            raise MeshCoreProcessorError(f"Invalid topic structure: {self.topic}")

        self._iata = parts[0]
        self._public_key = parts[1]
        self._data_type = parts[2]

        if self._data_type not in ("packets", "status"):
            raise MeshCoreProcessorError(f"Unknown data type from topic: {self._data_type}")

    def _parse_payload(self):
        """Parse the JSON payload and extract metadata."""
        try:
            self._parsed_json = json.loads(self.raw_payload.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise MeshCoreProcessorError(f"Failed to parse JSON payload: {e}")

        if not isinstance(self._parsed_json, dict):
            raise MeshCoreProcessorError("Payload must be a JSON object")

        # Build metadata from topic path + JSON fields
        self._metadata = MeshCoreMetadata(
            public_key=self._public_key,
            iata=self._iata,
            origin=self._parsed_json.get("origin"),
        )

        # Status messages include device info
        if self._data_type == "status":
            self._metadata.ver = self._parsed_json.get("firmware_version")
            self._metadata.board = self._parsed_json.get("model")

    def _is_heartbeat_packet(self) -> bool:
        """Check if this is a keepalive packet with no real data."""
        if self._data_type != "packets":
            return False
        raw = self._parsed_json.get("raw", "")
        pkt_len = self._parsed_json.get("len", "0")
        return not raw.strip() or pkt_len == "0"

    @staticmethod
    def _safe_float(value: str) -> Optional[float]:
        """Parse a string to float, returning None on failure."""
        if not value:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value: str) -> Optional[int]:
        """Parse a string to int, returning None on failure."""
        if not value:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    @property
    def public_key(self) -> str:
        return self._public_key

    @property
    def metadata(self) -> MeshCoreMetadata:
        return self._metadata

    @property
    def data_type(self) -> Optional[str]:
        return self._data_type

    @property
    def message_hash(self) -> Optional[str]:
        """The observer's packet hash from the packets-topic JSON envelope.

        Used for deduplication before decoding. Returns None for status
        messages and for heartbeat packets (empty hash string).
        """
        if self._data_type != "packets":
            return None
        raw_hash = self._parsed_json.get("hash")
        return raw_hash or None

    @property
    def payload(self) -> Union[str, dict]:
        """Return the processed payload for handlers.

        Returns:
            - For "packets": decoded dict from meshcoredecoder with envelope metadata
            - For "status": the full parsed JSON dict
        """
        if self._data_type == "packets":
            hex_str = self._parsed_json.get("raw", "")
            if not hex_str.strip():
                return {"error": "Empty raw packet data"}

            # Build envelope metadata from the relay's JSON fields
            envelope = {
                "SNR": self._safe_float(self._parsed_json.get("SNR", "")),
                "RSSI": self._safe_int(self._parsed_json.get("RSSI", "")),
                "direction": self._parsed_json.get("direction"),
                "route": self._parsed_json.get("route"),
                "score": self._safe_int(self._parsed_json.get("score", "")),
                "duration": self._safe_int(self._parsed_json.get("duration", "")),
                "hash": self._parsed_json.get("hash"),
                "path": self._parsed_json.get("path"),
            }

            try:
                from meshcoredecoder import MeshCoreDecoder

                decoded = MeshCoreDecoder.decode(hex_str, self.decryption_options)
                decoded_dict = decoded.to_dict() if hasattr(decoded, "to_dict") else vars(decoded)
                decoded_dict["envelope"] = envelope
                logger.debug(f"Decoded MeshCore packet: {decoded_dict}")
                return decoded_dict
            except ImportError:
                logger.warning("meshcoredecoder not installed, returning raw hex string")
                return {"raw": hex_str, "envelope": envelope}
            except Exception as e:
                logger.warning(f"Failed to decode MeshCore packet: {e}")
                return {"error": str(e), "raw": hex_str, "envelope": envelope}

        elif self._data_type == "status":
            return self._parsed_json

        return {}

    @property
    def data(self) -> Union[None, Any, list[Any]]:
        """Process and return data point(s) for InfluxDB."""
        # Skip heartbeat/keepalive packets
        if self._is_heartbeat_packet():
            logger.debug("Skipping heartbeat/keepalive packet (empty raw data)")
            return None

        handlers = MESHCORE_HANDLER_MAP.get(self._data_type, [])

        if not handlers:
            logger.debug(f"No handler registered for meshcore data_type: {self._data_type}")
            return None

        for handler_cls in handlers:
            try:
                handler = handler_cls(self._metadata, self.payload, self._data_type)
                result = handler.handle()
                if result:
                    return result
            except Exception as e:
                logger.exception(f"Error in handler {handler_cls.__name__}: {e}")

        return None
