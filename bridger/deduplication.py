from collections import deque
from typing import Hashable

from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope

from bridger.log import logger


class _BaseDeduplicator:
    """Shared bounded-FIFO duplicate detector.

    Subclasses build the key from mesh-specific fields and layer their own
    public API on top of the key-level helpers below.
    """

    def __init__(self, maxlen: int = 100):
        self.message_queue: deque = deque(maxlen=maxlen)

    def _is_duplicate_key(self, key: Hashable) -> bool:
        return key in self.message_queue

    def _mark_key(self, key: Hashable) -> None:
        self.message_queue.append(key)

    def _check_and_mark(self, key: Hashable) -> bool:
        """Return True if the key was new (and has now been marked)."""
        if key in self.message_queue:
            return False
        self.message_queue.append(key)
        return True


class MeshCoreDeduplicator(_BaseDeduplicator):
    """Deduplicate MeshCore packets keyed by (gateway_key, message_hash).

    Keying on the gateway/observer means the same packet seen by two
    observers is kept as two records -- different SNR/RSSI perspectives --
    while a single observer republishing the same hash is skipped.
    """

    def should_process(self, message_hash: str, gateway_key: str) -> bool:
        key = (gateway_key, message_hash)
        if not self._check_and_mark(key):
            logger.bind(message_hash=message_hash).opt(colors=True).debug(
                f"MeshCore packet <yellow>{message_hash}</yellow> from <green>{gateway_key[:8]}</green> already in queue"
            )
            return False
        return True


class PacketDeduplicator(_BaseDeduplicator):
    """Deduplicate Meshtastic packets keyed by packet_id (optionally per-gateway)."""

    def __init__(self, maxlen: int = 100, use_gateway_id: bool = False):
        super().__init__(maxlen=maxlen)
        self.use_gateway_id = use_gateway_id

    def _key(self, service_envelope: ServiceEnvelope):
        packet_id = service_envelope.packet.id
        if self.use_gateway_id:
            return (service_envelope.gateway_id, packet_id)
        return packet_id

    def is_duplicate(self, service_envelope: ServiceEnvelope) -> bool:
        if self._is_duplicate_key(self._key(service_envelope)):
            logger.bind(envelope_id=service_envelope.packet.id).opt(colors=True).debug(
                f"Packet <yellow>{service_envelope.packet.id}</yellow> from <green>{service_envelope.gateway_id}</green> already in queue"
            )
            return True
        return False

    def mark_processed(self, service_envelope: ServiceEnvelope) -> None:
        self._mark_key(self._key(service_envelope))

    def should_process(self, service_envelope: ServiceEnvelope) -> bool:
        if self.is_duplicate(service_envelope):
            return False
        self.mark_processed(service_envelope)
        return True
