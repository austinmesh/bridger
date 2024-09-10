import base64
from unittest.mock import MagicMock, patch

import pytest
from influxdb_client import InfluxDBClient
from influxdb_client.rest import ApiException
from meshtastic.protobuf.mesh_pb2 import Position
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.db import PositionPoint
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
node_info_encrypted = base64.b64decode(b"CjAN8w/QhBVk2BYMIjsIBBIyCgkhODRkMDBmZjMSE+KYgO+4j1NPTDMgUmVsYXkgVjIaBFNPTDMiBsPThNAP8ygJOAM125PbNjUC6MYyRQAAkEBIAmDX//////////8BeAISCExvbmdGYXN0GgkhMGMxNmQ4NjQ=")  # noqa: E501
power_packet_encrypted1 = base64.b64decode(b"CjMN9KoYDBX/////GAgqFY3Y05LhKIBqMwjwGuGN5o6s3xa8wjXB1YJfPcDN32ZIA1gKeAMSCExvbmdGYXN0GgkhMGMxOGFhZjQ=")  # noqa: E501
# fmt: on


@pytest.fixture
def influx_client():
    return MagicMock(spec=InfluxDBClient)


@pytest.fixture
def service_envelope():
    envelope = ServiceEnvelope.FromString(position1)
    return envelope


@pytest.fixture
def neighbor_envelope():
    envelope = ServiceEnvelope.FromString(neighbor1)
    return envelope


class TestPBPacketProcessor:
    def test_init_success(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        with patch.object(Position, "FromString", return_value=MagicMock()):
            processor = PBPacketProcessor(influx_client, service_envelope)
            assert processor.portnum == PortNum.POSITION_APP

    def test_init_failure(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        # Modify the envelope to use an unsupported portnum
        modified_envelope = ServiceEnvelope.FromString(node_info2)
        modified_envelope.packet.decoded.portnum = 6  # Admin portnum that we don't use
        with pytest.raises(PacketProcessorError):
            processor = PBPacketProcessor(influx_client, modified_envelope)
            processor.payload

    def test_payload_as_dict(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        with patch.object(Position, "FromString", return_value=MagicMock()):
            processor = PBPacketProcessor(influx_client, service_envelope)
            assert isinstance(processor.payload_as_dict, dict)

    def test_data(self, influx_client: MagicMock, service_envelope: ServiceEnvelope):
        payload_dict = {
            "latitude_i": 123456,
            "longitude_i": 654321,
            "altitude": 100,
            "precision_bits": 10,
            "speed": 50,
            "time": 1609459200,
        }
        with patch.object(Position, "FromString", return_value=MagicMock()), patch.object(
            PBPacketProcessor, "payload_as_dict", new_callable=MagicMock(return_value=payload_dict)
        ):
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
        with patch.object(Position, "FromString", return_value=MagicMock()), patch.object(
            PBPacketProcessor, "payload_as_dict", new_callable=MagicMock(return_value=payload_dict)
        ), patch.object(influx_client, "write_api", return_value=MagicMock()) as mock_write_api:
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
            PBPacketProcessor, "payload_as_dict", new_callable=MagicMock(return_value=payload_dict)
        ), patch.object(
            influx_client, "write_api", return_value=MagicMock(side_effect=ApiException(status=401))
        ) as mock_write_api:
            processor = PBPacketProcessor(influx_client, service_envelope)
            telemetry_data = processor.data
            processor.write_point(telemetry_data)
            assert mock_write_api().write.called
