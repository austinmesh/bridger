from dataclasses import dataclass

import pytest

from bridger.dataclasses import NodeData, NodeMixin


@dataclass
class TestNodeWithNodeId(NodeMixin):
    """Test class with node_id attribute"""

    node_id: int


@dataclass
class TestNodeWithFrom(NodeMixin):
    """Test class with _from attribute (like TelemetryPoint)"""

    _from: int


class TestNodeMixin:
    """Test the NodeMixin functionality with different attribute types"""

    def test_node_hex_id_with_bang_from_node_id(self):
        """Test hex ID conversion from node_id attribute"""
        node = TestNodeWithNodeId(node_id=439041101)  # 0x1a2b3c4d
        assert node.node_hex_id_with_bang == "!1a2b3c4d"
        assert node.node_hex_id_without_bang == "1a2b3c4d"
        assert node.color == "2b3c4d"

    def test_node_hex_id_with_bang_from_from_attribute(self):
        """Test hex ID conversion from _from attribute"""
        node = TestNodeWithFrom(_from=439041101)  # 0x1a2b3c4d
        assert node.node_hex_id_with_bang == "!1a2b3c4d"
        assert node.node_hex_id_without_bang == "1a2b3c4d"
        assert node.color == "2b3c4d"

    def test_node_hex_id_padding(self):
        """Test that hex IDs are properly zero-padded to 8 characters"""
        node = TestNodeWithNodeId(node_id=255)  # 0xff
        assert node.node_hex_id_with_bang == "!000000ff"
        assert node.node_hex_id_without_bang == "000000ff"

    def test_node_hex_id_large_numbers(self):
        """Test hex ID conversion with large numbers"""
        node = TestNodeWithNodeId(node_id=4294967295)  # 0xffffffff
        assert node.node_hex_id_with_bang == "!ffffffff"
        assert node.node_hex_id_without_bang == "ffffffff"

    def test_node_hex_id_no_attributes_raises_error(self):
        """Test that missing required attributes raises AttributeError"""

        @dataclass
        class TestNodeEmpty(NodeMixin):
            other_field: str

        node = TestNodeEmpty(other_field="test")

        with pytest.raises(AttributeError) as exc_info:
            _ = node.node_hex_id_with_bang

        assert "must have either '_from' or 'node_id' attribute" in str(exc_info.value)

    def test_priority_from_attribute_over_node_id(self):
        """Test that _from attribute takes priority over node_id"""

        @dataclass
        class TestNodeBoth(NodeMixin):
            _from: int
            node_id: int

        node = TestNodeBoth(_from=439041101, node_id=123456)  # Should use _from
        assert node.node_hex_id_with_bang == "!1a2b3c4d"

    def test_color_property_various_scenarios(self):
        """Test color property extraction in various scenarios"""
        # Test with short hex (should take last 6 chars after padding)
        node1 = TestNodeWithNodeId(node_id=255)  # 0x000000ff
        assert node1.color == "0000ff"

        # Test with full hex
        node2 = TestNodeWithNodeId(node_id=0xFFA2B3C4)
        assert node2.color == "a2b3c4"

        # Test with direct node_id input
        node3 = TestNodeWithNodeId(node_id=0x12345678)
        assert node3.color == "345678"


class TestNodeData:
    """Test the NodeData class functionality"""

    def test_node_data_basic_functionality(self):
        """Test basic NodeData functionality"""
        node = NodeData(node_id=439041101)
        assert node.node_id == 439041101
        assert node.node_hex_id_with_bang == "!1a2b3c4d"
        assert node.node_hex_id_without_bang == "1a2b3c4d"
        assert node.color == "2b3c4d"

    def test_node_data_zero_padding(self):
        """Test NodeData with small numbers requiring zero padding"""
        node = NodeData(node_id=1)
        assert node.node_hex_id_with_bang == "!00000001"
        assert node.node_hex_id_without_bang == "00000001"

    def test_node_data_max_value(self):
        """Test NodeData with maximum 32-bit value"""
        node = NodeData(node_id=4294967295)  # 0xffffffff
        assert node.node_hex_id_with_bang == "!ffffffff"
        assert node.node_hex_id_without_bang == "ffffffff"
