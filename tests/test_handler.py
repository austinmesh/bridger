from unittest.mock import MagicMock

import pytest
from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import NeighborInfoPacket
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import HANDLER_MAP, handler
from bridger.mesh.handlers.neighborinfo import NeighborInfoHandler


def test_handler_decorator_registers_class():
    class DummyHandler:
        portnum = PortNum.TEXT_MESSAGE_APP

    handler(DummyHandler)
    assert DummyHandler in HANDLER_MAP[PortNum.TEXT_MESSAGE_APP]


def test_handler_decorator_raises_if_missing_portnum():
    class InvalidHandler:
        pass

    with pytest.raises(ValueError, match="missing a `portnum` class attribute"):
        handler(InvalidHandler)


def test_packet_handler_abstract_instantiation():
    with pytest.raises(TypeError):
        PacketHandler(packet=None, payload_dict={}, base_data={})


def test_concrete_packet_handler_usage():
    class ConcreteHandler(PacketHandler):
        def handle(self):
            return {"status": "ok"}

    handler = ConcreteHandler(packet=MagicMock(), payload_dict={}, base_data={})
    assert handler.handle() == {"status": "ok"}


def test_neighbor_info_handler_generates_points():
    base_data = {
        "_from": 123,
        "to": 456,
        "packet_id": 789,
        "rx_time": 1600000000,
        "rx_snr": 12.5,
        "rx_rssi": -30,
        "hop_limit": 3,
        "hop_start": 0,
        "channel_id": "test",
        "gateway_id": "!abc123",
        "node_id": 123,
        "last_sent_by_id": 999,
        "neighbors": [
            {"node_id": 111, "snr": 10.1},
            {"node_id": 222, "snr": 7.5},
        ],
    }

    handler = NeighborInfoHandler(packet=MagicMock(), payload_dict={}, base_data=base_data.copy())
    result = handler.handle()

    assert isinstance(result, list)
    assert all(isinstance(p, NeighborInfoPacket) for p in result)
    assert len(result) == 2
    assert result[0].neighbor_id == 111
    assert result[1].neighbor_id == 222
