from collections import deque

from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope

from bridger.log import logger


class PacketDeduplicator:
    def __init__(self, maxlen: int = 100, use_gateway_id: bool = False):
        self.message_queue = deque(maxlen=maxlen)
        self.use_gateway_id = use_gateway_id

    def is_duplicate(self, service_envelope: ServiceEnvelope) -> bool:
        packet_id = service_envelope.packet.id
        gateway_id = service_envelope.gateway_id

        if self.use_gateway_id:
            key = (gateway_id, packet_id)
        else:
            key = packet_id

        if key in self.message_queue:
            logger.bind(envelope_id=packet_id).opt(colors=True).debug(
                f"Packet <yellow>{packet_id}</yellow> from <green>{gateway_id}</green> already in queue"
            )
            return True

        return False

    def mark_processed(self, service_envelope: ServiceEnvelope) -> None:
        packet_id = service_envelope.packet.id
        gateway_id = service_envelope.gateway_id

        if self.use_gateway_id:
            key = (gateway_id, packet_id)
        else:
            key = packet_id

        self.message_queue.append(key)

    def should_process(self, service_envelope: ServiceEnvelope) -> bool:
        if self.is_duplicate(service_envelope):
            return False

        self.mark_processed(service_envelope)
        return True
