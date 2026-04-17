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
        # Should subscribe to meshtastic topic
        mqtt_client.subscribe.assert_any_call("fake/2/e/#")
        # Should also subscribe to meshcore topic when MESHCORE_ENABLED=true (default)
        mqtt_client.subscribe.assert_any_call("fake/meshcore/#")

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

    def _make_meshcore_message(self, public_key: str, hash_value: str) -> MQTTMessage:
        import json as _json

        msg = MQTTMessage()
        msg.topic = f"fake/meshcore/AUS/{public_key}/packets".encode()
        msg.payload = _json.dumps(
            {
                "timestamp": "2026-04-11T00:00:00",
                "origin": "test relay",
                "origin_id": public_key,
                "type": "PACKET",
                "direction": "rx",
                "len": "54",
                "packet_type": "5",
                "route": "D",
                "payload_len": "51",
                "raw": "150142592837c57407f7965593ba3e513470bc3da2ad4bd0ac5f13056259c14abe2b590adbb637a8ba4b29e2e8d52b1997c18d5d1cf0",
                "SNR": "12.5",
                "RSSI": "-32",
                "score": "1000",
                "duration": "0",
                "hash": hash_value,
            }
        ).encode()
        return msg

    def test_meshcore_duplicate_from_same_observer_skipped(self, mqtt_client):
        public_key = "A" * 64
        msg = self._make_meshcore_message(public_key, "DEADBEEF")

        mqtt_client.on_message(mqtt_client, None, msg)
        assert len(mqtt_client.meshcore_deduplicator.message_queue) == 1

        # Same observer, same hash -> skipped
        mqtt_client.on_message(mqtt_client, None, msg)
        assert len(mqtt_client.meshcore_deduplicator.message_queue) == 1

    def test_meshcore_same_hash_different_observers_kept(self, mqtt_client):
        pk1 = "A" * 64
        pk2 = "B" * 64
        msg1 = self._make_meshcore_message(pk1, "DEADBEEF")
        msg2 = self._make_meshcore_message(pk2, "DEADBEEF")

        mqtt_client.on_message(mqtt_client, None, msg1)
        mqtt_client.on_message(mqtt_client, None, msg2)

        # Different observers reporting the same packet hash -> both kept
        assert len(mqtt_client.meshcore_deduplicator.message_queue) == 2
