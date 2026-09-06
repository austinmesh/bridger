import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Optional

from bridger.log import logger

# Deduplication is really a wall-clock concern: a broker redelivery or a mesh rebroadcast
# arrives seconds later, regardless of how busy the mesh is. A pure count window couples the
# horizon to traffic rate instead -- hours on a quiet night, seconds during an event -- so TTL
# is the primary window and maxlen is only a memory backstop.
DEFAULT_TTL_SECONDS = 600
DEFAULT_MAXLEN = 20000


class PacketDeduplicator:
    def __init__(
        self,
        maxlen: int = DEFAULT_MAXLEN,
        use_gateway_id: bool = False,
        ttl: Optional[float] = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.maxlen = maxlen
        self.use_gateway_id = use_gateway_id
        self.ttl = ttl
        self._clock = clock
        # Insertion-ordered, so eviction pops from the front; `in` and len() still work, but
        # membership is O(1) rather than the deque's linear scan.
        self.message_queue: OrderedDict[Hashable, float] = OrderedDict()
        self._warned_full = False

    def _key(self, gateway_id: str, packet_id: int) -> Hashable:
        return (gateway_id, packet_id) if self.use_gateway_id else packet_id

    @staticmethod
    def _unpack(service_envelope) -> tuple[str, int]:
        # Only these two attributes are ever read, which is what keeps this class usable for
        # a second mesh protocol later.
        return service_envelope.gateway_id, service_envelope.packet.id

    def _evict(self) -> None:
        now = self._clock()

        if self.ttl is not None:
            while self.message_queue:
                key, seen_at = next(iter(self.message_queue.items()))
                if now - seen_at < self.ttl:
                    break
                del self.message_queue[key]

        if len(self.message_queue) > self.maxlen:
            if not self._warned_full:
                # Hitting this means the window is too small for the deployment: entries are
                # being forgotten before their TTL, so genuine duplicates can slip through.
                # Latched, because a saturated window is one entry over on every subsequent
                # packet, and warning per packet would flood the log exactly when the bridge
                # is busiest.
                logger.warning(f"Deduplication window full at {self.maxlen} entries, evicting before TTL")
                self._warned_full = True

            while len(self.message_queue) > self.maxlen:
                self.message_queue.popitem(last=False)
        elif len(self.message_queue) < self.maxlen:
            # Dropped back under the cap on its own, so re-arm: a window that drains and then
            # saturates again is a new occurrence worth reporting.
            self._warned_full = False

    def is_duplicate_packet(self, gateway_id: str, packet_id: int) -> bool:
        self._evict()

        if self._key(gateway_id, packet_id) in self.message_queue:
            logger.bind(envelope_id=packet_id).opt(colors=True).debug(
                f"Packet <yellow>{packet_id}</yellow> from <green>{gateway_id}</green> already in queue"
            )
            return True

        return False

    def mark_processed_packet(self, gateway_id: str, packet_id: int) -> None:
        key = self._key(gateway_id, packet_id)
        self.message_queue[key] = self._clock()
        self.message_queue.move_to_end(key)
        self._evict()

    def should_process_packet(self, gateway_id: str, packet_id: int) -> bool:
        if self.is_duplicate_packet(gateway_id, packet_id):
            return False

        self.mark_processed_packet(gateway_id, packet_id)
        return True

    def is_duplicate(self, service_envelope) -> bool:
        return self.is_duplicate_packet(*self._unpack(service_envelope))

    def mark_processed(self, service_envelope) -> None:
        self.mark_processed_packet(*self._unpack(service_envelope))

    def should_process(self, service_envelope) -> bool:
        return self.should_process_packet(*self._unpack(service_envelope))
