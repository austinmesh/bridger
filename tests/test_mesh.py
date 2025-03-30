import base64
from unittest.mock import MagicMock, patch

import pytest
from meshtastic.protobuf.mesh_pb2 import Position
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum

import bridger.mesh.handlers  # noqa: F401 # We need to import handlers to register them in the HANDLER_MAP
from bridger.crypto import CryptoEngine
from bridger.dataclasses import PositionPoint
from bridger.mesh import PacketProcessorError, PBPacketProcessor

encrypted_key_test = "ujlQw7lG0zMZVjP7gYfs7A=="

# Example base64 encoded MQTT messages
# fmt: off
node_info1 = base64.b64decode(b"Cj4NZNgWDBX/////IicIBBIhCgkhMGMxNmQ4NjQSBEdFS08aBPCfpo4iBtzaDBbYZCgfGAE125PbNkgFWAp4BRIITG9uZ0Zhc3QaCSEwYzE2ZDg2NA==")  # noqa: E501
node_info2 = base64.b64decode(b"CmAN8w/QhBVk2BYMIjsIBBIyCgkhODRkMDBmZjMSE+KYgO+4j1NPTDMgUmVsYXkgVjIaBFNPTDMiBsPThNAP8ygJOAM125PbNjUC6MYyRQAAkEBIAmDX//////////8BeAISCExvbmdGYXN0GgkhMGMxNmQ4NjQ=")  # noqa: E501
device_telemetry1 = base64.b64decode(b"CjANZNgWDBX/////IhkIQxIVDTIAAAASDghlHU8bxEAl9dyRPCgyNdyT2zZIBVgKeAUSCExvbmdGYXN0GgkhMGMxNmQ4NjQ=")  # noqa: E501
position1 = base64.b64decode(b"CioNZNgWDBX/////IhMIAxINDQDADBIVAMDCxbgBERgBNd+T2zZIBVgKeAUSCExvbmdGYXN0GgkhMGMxNmQ4NjQ=")  # noqa: E501
position2 = base64.b64decode(b"CkAN8w/QhBVk2BYMIhsIAxISDQAADRIVAADDxSXUEYZmuAEPNd+T2zY1A+jGMkUAALhASAJg1f//////////AXgCEghMb25nRmFzdBoJITBjMTZkODY0")  # noqa: E501
neighbor1 = base64.b64decode(b"CmENuoSLahX/////IkcIRxJDCLqJrtQGELqJrtQGGIQHIgsIhome5wgVAADAQCILCN6vs+wLFQAAMMEiCwi/w4qUBxUAAIDBIgsIqIjKqgUVAAB8wTWcQz5MPW5/hWZIBHgEEghMb25nRmFzdBoJITZhOGI4NGJh")  # noqa: E501
node_info_encrypted = base64.b64decode(b"ClwN1bNHIBX/////GAgqMCjSKlNzvvW8rDUZjO5/jPMTm0NYltWLHRCbCDiPCP2nhV+/e6RjVuGMa5eBmNhm8zVpxh+dPbmG4GZFAADIQEgDYOX//////////wF4AxIITG9uZ0Zhc3QaCSEwYzE4YWFmNA==")  # noqa: E501
power_packet_encrypted1 = base64.b64decode(b"CjMN9KoYDBX/////GAgqFY3Y05LhKIBqMwjwGuGN5o6s3xa8wjXB1YJfPcDN32ZIA1gKeAMSCExvbmdGYXN0GgkhMGMxOGFhZjQ=")  # noqa: E501
text_pki_message1 = base64.b64decode(b"CkUNrblyoRX6jzHYKhb0yGmkfVrkb3IV3LoA5qiW1XZRw1gHNWPEqTA9WKroZ0UAAOBASANQAWDz//////////8BeAOIAQESA1BLSRoJITkzNGNjYzc0")  # noqa: E501
# fmt: on


@pytest.fixture
def crypto_engine():
    return MagicMock(spec=CryptoEngine)


@pytest.fixture
def service_envelope():
    envelope = ServiceEnvelope.FromString(position1)
    return envelope


@pytest.fixture
def text_pki_service_envelope():
    envelope = ServiceEnvelope.FromString(text_pki_message1)
    return envelope


@pytest.fixture
def neighbor_envelope():
    envelope = ServiceEnvelope.FromString(neighbor1)
    return envelope


@pytest.fixture
def nodeinfo_encrypted():
    envelope = ServiceEnvelope.FromString(node_info_encrypted)
    return envelope


class TestPBPacketProcessor:
    def test_init_success(self, service_envelope: ServiceEnvelope):
        with patch.object(Position, "FromString", return_value=MagicMock()):
            processor = PBPacketProcessor(service_envelope, force_decode=True)
            assert processor.portnum == PortNum.POSITION_APP
            assert processor.force_decode is True

    def test_init_failure(self, service_envelope: ServiceEnvelope):
        modified_envelope = ServiceEnvelope.FromString(node_info2)
        modified_envelope.packet.decoded.portnum = 6
        with pytest.raises(PacketProcessorError):
            processor = PBPacketProcessor(modified_envelope)
            processor.payload

    def test_payload_dict(self, service_envelope: ServiceEnvelope):
        with patch.object(Position, "FromString", return_value=MagicMock()):
            processor = PBPacketProcessor(service_envelope)
            assert isinstance(processor.payload_dict, dict)

    def test_data(self, service_envelope: ServiceEnvelope):
        mock_factory = MagicMock()
        mock_factory.FromString.return_value = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.name = "position"
        mock_protocol.protobufFactory = mock_factory

        with patch("meshtastic.protocols", new={PortNum.POSITION_APP: mock_protocol}):
            processor = PBPacketProcessor(service_envelope)
            data = processor.data
            assert isinstance(data, PositionPoint)

    def test_decrypt_node_info_encrypted(self, nodeinfo_encrypted: ServiceEnvelope):
        expected_data = {
            "_from": 541570005,
            "to": 4294967295,
            "packet_id": 2636105321,
            "rx_time": 1725990585,
            "rx_snr": 6.25,
            "rx_rssi": -27,
            "hop_limit": 3,
            "hop_start": 3,
            "channel_id": "LongFast",
            "gateway_id": "!0c18aaf4",
            "id": "!2047b3d5",
            "long_name": "egrme.sh Palm",
            "short_name": "egrp",
            "macaddr": "1kEgR7PV",
            "hw_model": 9,
            "role": 1,
        }

        with patch(
            "bridger.mesh.CryptoEngine.decrypt",
            return_value=(b'\x08\x04\x12,\n\t!2047b3d5\x12\regrme.sh Palm\x1a\x04egrp"\x06\xd6A G\xb3\xd5(\t8\x01'),
        ):
            processor = PBPacketProcessor(nodeinfo_encrypted, auto_decrypt=True)
            decrypted_data = processor.data

            for key, value in expected_data.items():
                assert getattr(decrypted_data, key) == value

    def test_pki_encrypted_text_message(self, text_pki_service_envelope: ServiceEnvelope):
        with pytest.raises(PacketProcessorError) as e:
            processor = PBPacketProcessor(text_pki_service_envelope)
            processor.payload_dict
        assert "We cannot decrypt PKI messages" in str(e.value)
