"""
Packet Builder Classes

Abstract base class and concrete implementations for creating Meshtastic packets
to be sent via MQTT.
"""

import time
from abc import ABC, abstractmethod
from typing import Optional

from meshtastic.protobuf.mesh_pb2 import Data, MeshPacket, User
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.log import logger

from .config import (
    VIRTUAL_NODE_CHANNEL,
    VIRTUAL_NODE_HW_MODEL,
    VIRTUAL_NODE_ID,
    VIRTUAL_NODE_LONG_NAME,
    VIRTUAL_NODE_ROLE,
    VIRTUAL_NODE_SHORT_NAME,
)


class VirtualPacketBuilder(ABC):
    """Abstract base class for building Meshtastic packets"""

    def __init__(self, from_node: int = VIRTUAL_NODE_ID, to_node: int = 0xFFFFFFFF):
        self.from_node = from_node
        self.to_node = to_node
        self.packet_id = self._generate_packet_id()

    def _generate_packet_id(self) -> int:
        """Generate a unique packet ID based on timestamp"""
        return int(time.time()) & 0xFFFFFFFF

    @property
    @abstractmethod
    def portnum(self) -> PortNum:
        """Return the port number for this packet type"""
        pass

    @abstractmethod
    def build_payload(self) -> bytes:
        """Build the protobuf payload for this packet type"""
        pass

    def build_service_envelope(self, gateway_id: Optional[str] = None) -> ServiceEnvelope:
        """Build a complete ServiceEnvelope ready for MQTT publishing"""
        # Create the Data protobuf
        data = Data()
        data.portnum = self.portnum
        data.payload = self.build_payload()

        # Create the MeshPacket
        mesh_packet = MeshPacket()
        setattr(mesh_packet, "from", self.from_node)
        mesh_packet.to = self.to_node
        mesh_packet.id = self.packet_id
        mesh_packet.rx_time = int(time.time())
        mesh_packet.decoded.CopyFrom(data)

        # Create the ServiceEnvelope
        envelope = ServiceEnvelope()
        envelope.packet.CopyFrom(mesh_packet)
        envelope.channel_id = VIRTUAL_NODE_CHANNEL
        envelope.gateway_id = gateway_id or f"!{self.from_node:08x}"

        return envelope


class NodeInfoPacketBuilder(VirtualPacketBuilder):
    """Builder for NodeInfo packets"""

    @property
    def portnum(self) -> PortNum:
        return PortNum.NODEINFO_APP

    def build_payload(self) -> bytes:
        """Build NodeInfo protobuf payload"""
        user = User()
        user.id = f"!{self.from_node:08x}"
        user.long_name = VIRTUAL_NODE_LONG_NAME
        user.short_name = VIRTUAL_NODE_SHORT_NAME
        user.hw_model = VIRTUAL_NODE_HW_MODEL
        user.role = VIRTUAL_NODE_ROLE

        logger.debug(f"Built NodeInfo payload: {user}")
        return user.SerializeToString()


class TextMessagePacketBuilder(VirtualPacketBuilder):
    """Builder for Text Message packets"""

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    @property
    def portnum(self) -> PortNum:
        return PortNum.TEXT_MESSAGE_APP

    def build_payload(self) -> bytes:
        """Build text message payload"""
        return self.message.encode("utf-8")
