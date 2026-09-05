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
        mqtt_client.subscribe.assert_called_once_with("fake/2/e/#")

    def test_on_connect_failure(self, mqtt_client):
        mqtt_client.subscribe = MagicMock()
        mqtt_client.on_connect(mqtt_client, None, None, 1, None)
        mqtt_client.subscribe.assert_not_called()

    def test_on_disconnect(self, mqtt_client):
        mqtt_client.on_disconnect(mqtt_client, None, None, 0, None)

    def test_on_message(self, mqtt_client, mqtt_message):
        mqtt_client._handle_decode_error = MagicMock()
        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1, _from="test_user"))):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            assert len(mqtt_client.deduplicator.message_queue) == 1

    def test_on_message_decode_error(self, mqtt_client, mqtt_message):
        mqtt_client._handle_decode_error = MagicMock()
        with patch.object(ServiceEnvelope, "FromString", side_effect=DecodeError):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            mqtt_client._handle_decode_error.assert_called_once()

    def test_on_message_type_error(self, mqtt_client, mqtt_message):
        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1))):
            with patch.object(PBPacketProcessor, "__init__", side_effect=TypeError):
                mqtt_client.on_message(mqtt_client, None, mqtt_message)

    def test_handle_decode_error(self, mqtt_client):
        payload = b"invalid_payload"
        mqtt_client._handle_decode_error(DecodeError(), {}, payload)

    def test_second_packet_skipped(self, mqtt_client, mqtt_message):
        mqtt_client._handle_decode_error = MagicMock()
        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1, _from="test_user"))):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            assert len(mqtt_client.deduplicator.message_queue) == 1
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            assert (
                len(mqtt_client.deduplicator.message_queue) == 1
            )  # The second packet should be skipped, queue length should remain 1


class TestWriterLifecycle:
    def test_one_writer_for_the_process(self, influx_client, mqtt_message):
        # A WriteApi per message rebuilt the batching pipeline every time, which defeats it.
        client = BridgerMQTT(influx_client, CallbackAPIVersion.VERSION2)
        client._handle_decode_error = MagicMock()

        with patch.object(ServiceEnvelope, "FromString", return_value=MagicMock(packet=MagicMock(id=1))):
            client.on_message(client, None, mqtt_message)
            client.on_message(client, None, mqtt_message)

        assert influx_client.write_api.call_count == 1

    def test_close_flushes_pending_writes(self, influx_client):
        client = BridgerMQTT(influx_client, CallbackAPIVersion.VERSION2)

        client.close()

        influx_client.write_api.return_value.close.assert_called_once()


class TestGatewayScopedDeduplication:
    def test_the_same_packet_from_two_gateways_is_kept(self, mqtt_client, mqtt_message):
        # rx_snr/rx_rssi are per-gateway, and gateway_id is a tag, so each gateway's reception
        # has to be written rather than only the first to arrive.
        mqtt_client._handle_decode_error = MagicMock()

        first = MagicMock(packet=MagicMock(id=1), gateway_id="!gw1")
        second = MagicMock(packet=MagicMock(id=1), gateway_id="!gw2")

        with patch.object(ServiceEnvelope, "FromString", side_effect=[first, second]):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            mqtt_client.on_message(mqtt_client, None, mqtt_message)

        assert len(mqtt_client.deduplicator.message_queue) == 2

    def test_the_same_packet_from_one_gateway_is_dropped(self, mqtt_client, mqtt_message):
        mqtt_client._handle_decode_error = MagicMock()

        envelope = MagicMock(packet=MagicMock(id=1), gateway_id="!gw1")

        with patch.object(ServiceEnvelope, "FromString", return_value=envelope):
            mqtt_client.on_message(mqtt_client, None, mqtt_message)
            mqtt_client.on_message(mqtt_client, None, mqtt_message)

        assert len(mqtt_client.deduplicator.message_queue) == 1


class TestSubscribeReporting:
    def test_a_refused_suback_is_logged_as_an_error(self, mqtt_client):
        # paho's local return code is success even when the broker denies the subscription,
        # so without this the bridge reports healthy and silently receives nothing.
        denied = MagicMock(is_failure=True)
        denied.__str__ = lambda self: "Not authorized"

        with patch("bridger.mqtt.logger") as log:
            mqtt_client.on_subscribe(mqtt_client, None, 1, [denied], None)

        assert log.error.called
        assert "No packets will arrive" in log.error.call_args[0][0]

    def test_a_granted_suback_is_logged_as_info(self, mqtt_client):
        granted = MagicMock(is_failure=False, value=0)

        with patch("bridger.mqtt.logger") as log:
            mqtt_client.on_subscribe(mqtt_client, None, 1, [granted], None)

        assert not log.error.called
        assert log.info.called
