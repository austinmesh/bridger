"""
Virtual Node MQTT Client

MQTT client for the virtual Meshtastic node that can publish packets
and listen for incoming messages.
"""

import paho.mqtt.client as mqtt
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.config import MQTT_TOPIC
from bridger.deduplication import PacketDeduplicator
from bridger.log import logger
from bridger.mesh import PBPacketProcessor

from .config import VIRTUAL_NODE_ID, get_virtual_node_topics
from .packet_builder import NodeInfoPacketBuilder, TextMessagePacketBuilder


class VirtualNodeMQTT(mqtt.Client):
    """MQTT client for virtual Meshtastic node"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.topics = get_virtual_node_topics(MQTT_TOPIC)
        self.deduplicator = PacketDeduplicator(maxlen=100)

        # Set up MQTT callbacks
        self.on_connect = self._on_connect
        self.on_message = self._on_message
        self.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback for when MQTT client connects"""
        if rc == 0:
            logger.info("Virtual node MQTT client connected")
            # Subscribe to broadcast messages to listen for messages directed at us
            client.subscribe(self.topics["subscribe_broadcast"])
            logger.info(f"Subscribed to {self.topics['subscribe_broadcast']}")
        else:
            logger.error(f"Virtual node MQTT client failed to connect: {rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        """Callback for when MQTT client disconnects"""
        logger.info(f"Virtual node MQTT client disconnected: {rc}")

    def _on_message(self, client, userdata, message):
        """Handle incoming MQTT messages"""
        try:
            service_envelope = ServiceEnvelope.FromString(message.payload)

            # Skip if we've already processed this packet
            if not self.deduplicator.should_process(service_envelope):
                return

            # Check if this message is directed at our virtual node
            packet = service_envelope.packet
            if packet.to != VIRTUAL_NODE_ID and packet.to != 0xFFFFFFFF:
                return  # Not for us

            # Skip our own packets
            if getattr(packet, "from") == VIRTUAL_NODE_ID:
                return

            logger.info(f"Received packet for virtual node: ID={packet.id}, from={getattr(packet, 'from'):08x}")

            # Process the packet
            processor = PBPacketProcessor(service_envelope=service_envelope, strip_text=False)

            # Handle different packet types
            if processor.portnum == PortNum.TEXT_MESSAGE_APP:
                self._handle_text_message(processor, service_envelope)
            elif processor.portnum == PortNum.NODEINFO_APP:
                logger.debug("Received NodeInfo packet directed at virtual node")
            else:
                logger.debug(f"Received {processor.portnum_friendly_name} packet directed at virtual node")

        except Exception as e:
            logger.exception(f"Error processing MQTT message: {e}")

    def _handle_text_message(self, processor: PBPacketProcessor, envelope: ServiceEnvelope):
        """Handle incoming text messages directed at virtual node"""
        data = processor.data
        if not data or not hasattr(data, "text"):
            return

        from_node = getattr(envelope.packet, "from")
        text = data.text

        logger.info(f"Received text message from {from_node:08x}: {text}")

        # Send auto-response
        response_text = f"Hello from Bridger! You sent: {text}"
        self.send_text_message(response_text, to_node=from_node)

    def send_nodeinfo(self):
        """Send NodeInfo packet to announce virtual node presence"""
        try:
            builder = NodeInfoPacketBuilder()
            envelope = builder.build_service_envelope()

            payload = envelope.SerializeToString()
            topic = self.topics["publish"]

            result = self.publish(topic, payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Sent NodeInfo packet on topic: {topic}")
            else:
                logger.error(f"Failed to send NodeInfo packet: {result.rc}")

        except Exception as e:
            logger.exception(f"Error sending NodeInfo packet: {e}")

    def send_text_message(self, message: str, to_node: int = 0xFFFFFFFF):
        """Send text message packet"""
        try:
            builder = TextMessagePacketBuilder(message, to_node=to_node)
            envelope = builder.build_service_envelope()

            payload = envelope.SerializeToString()
            topic = self.topics["publish"]

            result = self.publish(topic, payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Sent text message to {to_node:08x}: {message}")
            else:
                logger.error(f"Failed to send text message: {result.rc}")

        except Exception as e:
            logger.exception(f"Error sending text message: {e}")
