"""
Tests for virtual node functionality
"""

import pytest
from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.virtual_node.config import VIRTUAL_NODE_ID, VIRTUAL_NODE_LONG_NAME, VIRTUAL_NODE_SHORT_NAME
from bridger.virtual_node.packet_builder import NodeInfoPacketBuilder, TextMessagePacketBuilder


class TestNodeInfoPacketBuilder:
    """Test NodeInfo packet builder"""

    def test_portnum(self):
        """Test that NodeInfo packet builder has correct port number"""
        builder = NodeInfoPacketBuilder()
        assert builder.portnum == PortNum.NODEINFO_APP

    def test_build_payload(self):
        """Test NodeInfo payload building"""
        builder = NodeInfoPacketBuilder()
        payload = builder.build_payload()
        assert isinstance(payload, bytes)
        assert len(payload) > 0

    def test_build_service_envelope(self):
        """Test building complete ServiceEnvelope"""
        builder = NodeInfoPacketBuilder()
        envelope = builder.build_service_envelope()

        # Check envelope structure
        assert envelope.packet.decoded.portnum == PortNum.NODEINFO_APP
        assert getattr(envelope.packet, "from") == VIRTUAL_NODE_ID
        assert envelope.packet.to == 0xFFFFFFFF  # Broadcast
        assert envelope.channel_id == "LongFast"
        assert envelope.gateway_id == f"!{VIRTUAL_NODE_ID:08x}"

    def test_custom_gateway_id(self):
        """Test building envelope with custom gateway ID"""
        builder = NodeInfoPacketBuilder()
        custom_gateway = "!12345678"
        envelope = builder.build_service_envelope(gateway_id=custom_gateway)

        assert envelope.gateway_id == custom_gateway


class TestTextMessagePacketBuilder:
    """Test Text Message packet builder"""

    def test_portnum(self):
        """Test that Text Message packet builder has correct port number"""
        builder = TextMessagePacketBuilder("test message")
        assert builder.portnum == PortNum.TEXT_MESSAGE_APP

    def test_build_payload(self):
        """Test text message payload building"""
        message = "Hello from virtual node!"
        builder = TextMessagePacketBuilder(message)
        payload = builder.build_payload()

        assert isinstance(payload, bytes)
        assert payload.decode("utf-8") == message

    def test_build_service_envelope(self):
        """Test building complete ServiceEnvelope for text message"""
        message = "Test message"
        builder = TextMessagePacketBuilder(message)
        envelope = builder.build_service_envelope()

        # Check envelope structure
        assert envelope.packet.decoded.portnum == PortNum.TEXT_MESSAGE_APP
        assert getattr(envelope.packet, "from") == VIRTUAL_NODE_ID
        assert envelope.packet.to == 0xFFFFFFFF  # Broadcast by default

    def test_directed_message(self):
        """Test building directed text message"""
        message = "Direct message"
        target_node = 0x12345678
        builder = TextMessagePacketBuilder(message, to_node=target_node)
        envelope = builder.build_service_envelope()

        assert envelope.packet.to == target_node


class TestVirtualNodeConfig:
    """Test virtual node configuration"""

    def test_virtual_node_constants(self):
        """Test that virtual node constants are properly defined"""
        assert VIRTUAL_NODE_ID == 0x42524447  # "BRDG" in hex
        assert VIRTUAL_NODE_SHORT_NAME == "BRDG"
        assert VIRTUAL_NODE_LONG_NAME == "Bridger"

    def test_hex_id_format(self):
        """Test that virtual node ID formats correctly as hex"""
        hex_id = f"!{VIRTUAL_NODE_ID:08x}"
        assert hex_id == "!42524447"
