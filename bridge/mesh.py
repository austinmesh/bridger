import base64
import os
from abc import ABC, abstractmethod
from argparse import ArgumentParser
from typing import Optional, Union

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
from meshtastic.protobuf.mesh_pb2 import Position, User
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum
from meshtastic.protobuf.telemetry_pb2 import Telemetry

from bridge.db import DeviceTelemetryPoint, NodeInfoPoint, PositionPoint, SensorTelemetryPoint, TelemetryPoint
from bridge.log import file_logger, logger

INFLUXDB_V2_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "meshtastic")

DECODERS = {
    PortNum.NODEINFO_APP: User,
    PortNum.POSITION_APP: Position,
    PortNum.TELEMETRY_APP: Telemetry,
}

# DECODER_DATA_MAPPING = {
#     NodeInfoPoint: PortNum.NODEINFO_APP,
#     PositionPoint: PortNum.POSITION_APP,
#     SensorTelemetryPoint: PortNum.TELEMETRY_APP,
#     DeviceTelemetryPoint: PortNum.TELEMETRY_APP,
# }


class PacketProcessorError(Exception):
    def __init__(self, message, portnum=None):
        super().__init__(message)
        self.portnum = portnum


class PacketProcessor(ABC):
    common_fields = ["rx_time", "rx_snr", "rx_rssi", "hop_limit", "hop_start"]
    common_tags = ["channel_id", "gateway_id", "_from", "to"]

    def __init__(self, influx_client: InfluxDBClient, service_envelope: ServiceEnvelope):
        self.service_envelope = service_envelope
        self.write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    measurement_data = {
        NodeInfoPoint: ("node", ["long_name", "short_name", "hw_model"], [], PortNum.NODEINFO_APP),
        PositionPoint: (
            "position",
            [],
            ["latitude_i", "longitude_i", "altitude", "precision_bits", "speed", "time"],
            PortNum.POSITION_APP,
        ),
        SensorTelemetryPoint: (
            "sensor",
            [],
            [
                "air_util_tx",
                "channel_utilization",
                "barometric_pressure",
                "current",
                "gas_resistance",
                "relative_humidity",
                "temperature",
                "voltage",
                "uptime_seconds",
            ],
            PortNum.TELEMETRY_APP,
        ),
        DeviceTelemetryPoint: (
            "battery",
            [],
            ["battery_level", "voltage", "air_util_tx", "channel_utilization"],
            PortNum.TELEMETRY_APP,
        ),
    }

    @property
    @abstractmethod
    def payload_as_dict(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def data(self):
        raise NotImplementedError

    def write_data(self, record, measurement, fields, tags):
        try:
            extra = {
                "measurement": measurement,
                "tags": tags,
                "fields": fields,
                "common_fields": self.common_fields,
                "common_tags": self.common_tags,
                "record": record,
            }

            self.write_api.write(
                bucket=INFLUXDB_V2_BUCKET,
                record=record,
                record_measurement_name=measurement,
                record_field_keys=fields + self.common_fields,
                record_tag_keys=tags + self.common_tags,
            )
            logger.bind(**extra).opt(colors=True).info(
                f"Wrote packet ID <yellow>{record.packet_id}</yellow> from gateway: {record.gateway_id}"
            )
        except ApiException as e:
            if e.status == 401:
                logger.error(f"Credentials for InfluxDB are either not set or incorrect: {e}")

    def write_point(self, telemetry_data: TelemetryPoint):
        for telemetry_class, (measurement, tags, fields, port_num) in self.measurement_data.items():
            if isinstance(telemetry_data, telemetry_class):
                self.write_data(telemetry_data, measurement, fields, tags)
                break


# TODO: Implement a JSONPacketProcessor class to process packets that come in as JSON instead of protobuf
# class JSONPacketProcessor(PacketProcessor):
#     pass


class PBPacketProcessor(PacketProcessor):
    def __init__(self, influx_client: InfluxDBClient, service_envelope: ServiceEnvelope):
        super().__init__(influx_client, service_envelope)

        # Throw exception if service envelope is a type not in the DECODERS dict
        self.portnum: PortNum = service_envelope.packet.decoded.portnum
        if self.portnum not in DECODERS:
            raise PacketProcessorError(
                f"We cannot yet decode: {PortNum.Name(self.portnum)}",
                portnum=self.portnum,
            )

        self.payload = DECODERS[self.portnum].FromString(service_envelope.packet.decoded.payload)

    @property
    def payload_as_dict(self):
        return MessageToDict(
            self.payload,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )

    @property
    def data(self) -> Optional[Union[NodeInfoPoint, PositionPoint, SensorTelemetryPoint, DeviceTelemetryPoint]]:
        packet = self.service_envelope.packet
        point_data = {
            "_from": getattr(packet, "from"),
            "to": packet.to,
            "packet_id": packet.id,
            "rx_time": packet.rx_time,
            "rx_snr": packet.rx_snr,
            "rx_rssi": packet.rx_rssi,
            "hop_limit": packet.hop_limit,
            "hop_start": packet.hop_start,
            "channel_id": self.service_envelope.channel_id,
            "gateway_id": self.service_envelope.gateway_id,
        }

        point_data.update(self.payload_as_dict)

        try:
            if self.portnum == PortNum.NODEINFO_APP:
                return NodeInfoPoint(**point_data)
            elif self.portnum == PortNum.POSITION_APP:
                if "latitude_i" in self.payload_as_dict and "longitude_i" in self.payload_as_dict:
                    return PositionPoint(**point_data)
            elif self.portnum == PortNum.TELEMETRY_APP:
                if "environment_metrics" in self.payload_as_dict:
                    point_data.update(self.payload_as_dict["environment_metrics"])
                    return SensorTelemetryPoint(**point_data)
                elif "device_metrics" in self.payload_as_dict:
                    point_data.update(self.payload_as_dict["device_metrics"])
                    return DeviceTelemetryPoint(**point_data)
            else:
                logger.bind(portnum=self.portnum).warning(f"Unknown port number: {self.portnum}")
                logger.debug(f"Payload: {self.payload_as_dict}")
                return None
        except (AttributeError, KeyError) as e:
            logger.exception(f"{type(e).__name__}: {e}")
            return None


if __name__ == "__main__":
    logger.remove(file_logger)
    influx_client = InfluxDBClient.from_env_properties()
    parser = ArgumentParser()
    parser.add_argument("packet", help="Base64 encoded protobuf message")
    args = parser.parse_args()

    try:
        service_envelope = ServiceEnvelope.FromString(base64.b64decode(args.packet))
        logger.info(f"Service envelope: \n{service_envelope}")

        processor = PBPacketProcessor(influx_client, service_envelope)
        logger.info(f"Decoded packet: \n{processor.data}")

    except PacketProcessorError as e:
        logger.warning(f"Error processing packet: {e}")
    except DecodeError as e:
        logger.exception(f"Error decoding message: {e}")
    except Exception as e:
        logger.exception(f"Error processing packet: {e}")
