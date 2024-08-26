from collections import deque
from unittest.mock import MagicMock, patch

import pytest
from google.protobuf.message import DecodeError
from influxdb_client import InfluxDBClient
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from paho.mqtt.client import CallbackAPIVersion, MQTTMessage

from bridger.mesh import PBPacketProcessor
from bridger.mqtt import BridgerMQTT


@pytest.fixture
def influx_client():
    return MagicMock(spec=InfluxDBClient)


@pytest.fixture
def mqtt_client(influx_client):
    return BridgerMQTT(influx_client, CallbackAPIVersion.VERSION2)


@pytest.fixture
def mqtt_message():
    message = MQTTMessage()
    message.topic = b"test/topic"
    message.payload = b"test_payload"
    return message


class TestBridgerMQTT:
    def test_on_connect_success(self, mqtt_client):
        mqtt_client.subscribe = MagicMock(return_value=(0, 1))
        mqtt_client.on_connect(mqtt_client, None, None, 0, None)
        mqtt_client.subscribe.assert_called_once_with("egr/home/2/e/#")

    def test_on_connect_failure(self, mqtt_client):
        mqtt_client.subscribe = MagicMock()
        mqtt_client.on_connect(mqtt_client, None, None, 1, None)
        mqtt_client.subscribe.assert_not_called()

    def test_on_disconnect(self, mqtt_client):
        mqtt_client.on_disconnect(mqtt_client, None, None, 0, None)

    def test_on_message(self, mqtt_client, mqtt_message):
        mqtt_client.message_queue = deque(maxlen=100)
        mqtt_client._handle_decode_error = MagicMock()
        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1, _from="test_user"))):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            assert len(mqtt_client.message_queue) == 1

    def test_on_message_decode_error(self, mqtt_client, mqtt_message):
        mqtt_client.message_queue = deque(maxlen=100)
        mqtt_client._handle_decode_error = MagicMock()
        with patch.object(ServiceEnvelope, "FromString", side_effect=DecodeError):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            mqtt_client._handle_decode_error.assert_called_once()

    def test_on_message_type_error(self, mqtt_client, mqtt_message):
        mqtt_client.message_queue = deque(maxlen=100)
        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1))):
            with patch.object(PBPacketProcessor, "__init__", side_effect=TypeError):
                mqtt_client.on_message(mqtt_client, None, mqtt_message)

    def test_handle_decode_error(self, mqtt_client):
        payload = b"invalid_payload"
        mqtt_client._handle_decode_error(DecodeError(), {}, payload)

    def test_second_packet_skipped(self, mqtt_client, mqtt_message):
        mqtt_client.message_queue = deque(maxlen=100)
        mqtt_client._handle_decode_error = MagicMock()
        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1, _from="test_user"))):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            assert len(mqtt_client.message_queue) == 1
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            assert len(mqtt_client.message_queue) == 1  # The second packet should be skipped, queue length should remain 1
