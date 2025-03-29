import base64
from unittest.mock import MagicMock, patch

import pytest
from influxdb_client import InfluxDBClient
from influxdb_client.rest import ApiException
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
# fmt: on


@pytest.fixture
def influx_client():
    write_api_mock = MagicMock()
    client = MagicMock(spec=InfluxDBClient)
    client.write_api.return_value = write_api_mock
    return client


@pytest.fixture
def crypto_engine():
    # return CryptoEngine(key_base64=encrypted_key_test)
    return MagicMock(spec=CryptoEngine)


@pytest.fixture
def service_envelope():
    envelope = ServiceEnvelope.FromString(position1)
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
    def test_init_success(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        with patch.object(Position, "FromString", return_value=MagicMock()):
            processor = PBPacketProcessor(influx_client, service_envelope, force_decode=True)
            assert processor.portnum == PortNum.POSITION_APP
            assert processor.force_decode is True

    def test_init_failure(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        # Modify the envelope to use an unsupported portnum
        modified_envelope = ServiceEnvelope.FromString(node_info2)
        modified_envelope.packet.decoded.portnum = 6  # Admin portnum that we don't use
        with pytest.raises(PacketProcessorError):
            processor = PBPacketProcessor(influx_client, modified_envelope)
            processor.payload

    def test_payload_dict(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        with patch.object(Position, "FromString", return_value=MagicMock()):
            processor = PBPacketProcessor(influx_client, service_envelope)
            assert isinstance(processor.payload_dict, dict)

    def test_data(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        mock_factory = MagicMock()
        mock_factory.FromString.return_value = MagicMock()
        mock_protocol = MagicMock()
        mock_protocol.name = "position"
        mock_protocol.protobufFactory = mock_factory

        with patch("meshtastic.protocols", new={PortNum.POSITION_APP: mock_protocol}):
            processor = PBPacketProcessor(influx_client, service_envelope)
            data = processor.data
            assert isinstance(data, PositionPoint)

    def test_write_point(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        payload_dict = {
            "latitude_i": 123456,
            "longitude_i": 654321,
            "altitude": 100,
            "precision_bits": 10,
            "speed": 50,
            "time": 1609459200,
        }

        mock_write_api = MagicMock()
        mock_write_api.write.side_effect = ApiException(status=401)

        with patch.object(Position, "FromString", return_value=MagicMock()), patch.object(
            PBPacketProcessor, "payload_dict", new_callable=MagicMock(return_value=payload_dict)
        ), patch.object(influx_client, "write_api", return_value=mock_write_api) as mock_write_api:

            processor = PBPacketProcessor(influx_client, service_envelope)
            telemetry_data = processor.data
            processor.write_point(telemetry_data)
            assert mock_write_api().write.called

    def test_write_nieghbor_point(self, influx_client: MagicMock, neighbor_envelope: ServiceEnvelope):
        with patch.object(influx_client, "write_api", return_value=MagicMock()) as mock_write_api:
            processor = PBPacketProcessor(influx_client, neighbor_envelope)
            telemetry_data = processor.data
            processor.write_point(telemetry_data)
            assert mock_write_api().write

    def test_write_point_api_exception(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        payload_dict = {
            "latitude_i": 123456,
            "longitude_i": 654321,
            "altitude": 100,
            "precision_bits": 10,
            "speed": 50,
            "time": 1609459200,
        }
        with patch.object(Position, "FromString", return_value=MagicMock()), patch.object(
            PBPacketProcessor, "payload_dict", new_callable=MagicMock(return_value=payload_dict)
        ), patch.object(
            influx_client, "write_api", return_value=MagicMock(side_effect=ApiException(status=401))
        ) as mock_write_api:
            processor = PBPacketProcessor(influx_client, service_envelope)
            telemetry_data = processor.data
            processor.write_point(telemetry_data)
            assert mock_write_api().write.called

    @patch("bridger.mesh.CryptoEngine.decrypt", MagicMock())
    def test_decrypt_node_info_encrypted(self, nodeinfo_encrypted: ServiceEnvelope, influx_client: MagicMock):
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

        CryptoEngine.decrypt.return_value = (
            b'\x08\x04\x12,\n\t!2047b3d5\x12\regrme.sh Palm\x1a\x04egrp"\x06\xd6A G\xb3\xd5(\t8\x01'  # noqa: E501
        )

        processor = PBPacketProcessor(influx_client, nodeinfo_encrypted, auto_decrypt=True)

        decrypted_data = processor.data

        assert decrypted_data._from == expected_data["_from"]
        assert decrypted_data.to == expected_data["to"]
        assert decrypted_data.packet_id == expected_data["packet_id"]
        assert decrypted_data.rx_time == expected_data["rx_time"]
        assert decrypted_data.rx_snr == expected_data["rx_snr"]
        assert decrypted_data.rx_rssi == expected_data["rx_rssi"]
        assert decrypted_data.hop_limit == expected_data["hop_limit"]
        assert decrypted_data.hop_start == expected_data["hop_start"]
        assert decrypted_data.channel_id == expected_data["channel_id"]
        assert decrypted_data.gateway_id == expected_data["gateway_id"]
        assert decrypted_data.id == expected_data["id"]
        assert decrypted_data.long_name == expected_data["long_name"]
        assert decrypted_data.short_name == expected_data["short_name"]
        assert decrypted_data.macaddr == expected_data["macaddr"]
        assert decrypted_data.hw_model == expected_data["hw_model"]
        assert decrypted_data.role == expected_data["role"]
