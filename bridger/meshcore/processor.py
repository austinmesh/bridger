"""MeshCore packet processor for handling MQTT messages."""

import json
from dataclasses import dataclass
from typing import Any, Optional, Union

from bridger.config import MESHCORE_MQTT_TOPIC
from bridger.log import logger
from bridger.meshcore.handler_registry import MESHCORE_HANDLER_MAP


class MeshCoreProcessorError(Exception):
    """Exception raised when processing MeshCore messages fails."""

    def __init__(self, message: str, data_type: str = None):
        super().__init__(message)
        self.data_type = data_type


# Data type keys that can appear in the JSON payload
DATA_TYPE_KEYS = ["stats_radio", "stats_packet", "stats_core", "raw"]

# Mapping from JSON keys to handler data_type identifiers
DATA_TYPE_MAP = {
    "stats_radio": "stats/radio",
    "stats_packet": "stats/packets",
    "stats_core": "stats/core",
    "raw": "packets",
}


@dataclass
class MeshCoreMetadata:
    """Common metadata from MeshCore JSON messages."""

    public_key: str
    name: Optional[str] = None
    ver: Optional[str] = None
    board: Optional[str] = None


class MCPacketProcessor:
    """Processor for MeshCore MQTT messages.

    All messages are JSON with common metadata fields:
        - name: Device name
        - public_key: Device public key
        - ver: Firmware version
        - board: Hardware board type

    And one data-specific field:
        - stats_radio: Radio statistics
        - stats_packets: Packet statistics
        - stats_core: Core statistics
        - raw: Raw packet data (hex string)
    """

    # Extract the base prefix from config (remove the wildcard)
    TOPIC_PREFIX = MESHCORE_MQTT_TOPIC.rstrip("#")

    def __init__(self, topic: str, payload: bytes):
        self.topic = topic
        self.raw_payload = payload
        self._parsed_json: Optional[dict] = None
        self._metadata: Optional[MeshCoreMetadata] = None
        self._data_type: Optional[str] = None
        self._parse_payload()

    def _parse_payload(self):
        """Parse the JSON payload and extract metadata and data type."""
        try:
            self._parsed_json = json.loads(self.raw_payload.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise MeshCoreProcessorError(f"Failed to parse JSON payload: {e}")

        if not isinstance(self._parsed_json, dict):
            raise MeshCoreProcessorError("Payload must be a JSON object")

        # Extract common metadata
        public_key = self._parsed_json.get("public_key")
        if not public_key:
            raise MeshCoreProcessorError("Missing required field: public_key")

        self._metadata = MeshCoreMetadata(
            public_key=public_key,
            name=self._parsed_json.get("name"),
            ver=self._parsed_json.get("ver"),
            board=self._parsed_json.get("board"),
        )

        # Detect data type from present keys (optional - info messages won't have one)
        for key in DATA_TYPE_KEYS:
            if key in self._parsed_json:
                self._data_type = DATA_TYPE_MAP[key]
                break

    @property
    def public_key(self) -> str:
        """Return the device public key."""
        return self._metadata.public_key

    @property
    def metadata(self) -> MeshCoreMetadata:
        """Return the common metadata."""
        return self._metadata

    @property
    def data_type(self) -> Optional[str]:
        """Return the detected data type, or None for info-only messages."""
        return self._data_type

    @property
    def payload(self) -> Union[str, dict]:
        """Return the data-specific payload.

        Returns:
            - For "packets" (raw): Decoded dict from meshcoredecoder
            - For "stats/*": Parsed dict from JSON
        """
        if self._data_type == "packets":
            # Get the raw hex string and decode it
            hex_str = self._parsed_json.get("raw", "")
            if not hex_str:
                return {"error": "Empty raw packet data"}

            try:
                from meshcoredecoder import MeshCoreDecoder

                decoded = MeshCoreDecoder.decode(hex_str)
                # Convert DecodedPacket to dict for handler processing
                decoded_dict = decoded.to_dict() if hasattr(decoded, "to_dict") else vars(decoded)
                logger.debug(f"Decoded MeshCore packet: {decoded_dict}")
                return decoded_dict
            except ImportError:
                logger.warning("meshcoredecoder not installed, returning raw hex string")
                return {"raw": hex_str}
            except Exception as e:
                logger.warning(f"Failed to decode MeshCore packet: {e}")
                return {"error": str(e), "raw": hex_str}

        elif self._data_type == "stats/radio":
            return self._parsed_json.get("stats_radio", {})
        elif self._data_type == "stats/packets":
            return self._parsed_json.get("stats_packet", {})
        elif self._data_type == "stats/core":
            return self._parsed_json.get("stats_core", {})

        return {}

    @property
    def data(self) -> Union[None, Any, list[Any]]:
        """Process and return data point(s) for InfluxDB."""
        # Info-only messages don't have a data type key
        if not self._data_type:
            logger.debug("Info-only message, no data to process")
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
