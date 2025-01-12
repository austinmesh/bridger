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
from meshtastic import KnownProtocol, protocols
from meshtastic.protobuf.mesh_pb2 import Data, NeighborInfo, Position, User
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum
from meshtastic.protobuf.telemetry_pb2 import Telemetry

from bridger.crypto import CryptoEngine
from bridger.dataclasses import (
    DeviceTelemetryPoint,
    NeighborInfoPacket,
    NodeInfoPoint,
    PositionPoint,
    PowerTelemetryPoint,
    SensorTelemetryPoint,
    TelemetryPoint,
)
from bridger.log import file_logger, logger

INFLUXDB_V2_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "meshtastic")

SUPPORTED_PACKET_TYPES = [
    "text",
    "position",
    "user",
    "telemetry",
    "neighborinfo",
    "traceroute",
    "admin",
]  # See meshtastic.protocols for the names of packet types

# DECODERS = {
#     PortNum.NODEINFO_APP: User,
#     PortNum.POSITION_APP: Position,
#     PortNum.TELEMETRY_APP: Telemetry,
#     PortNum.NEIGHBORINFO_APP: NeighborInfo,
# }


class PacketProcessorError(Exception):
    def __init__(self, message, portnum=None):
        super().__init__(message)
        self.portnum = portnum


class PacketProcessor(ABC):
    common_fields = ["rx_time", "rx_snr", "rx_rssi", "hop_limit", "hop_start", "packet_id"]
    common_tags = ["channel_id", "gateway_id", "_from", "to"]

    def __init__(self, influx_client: InfluxDBClient, service_envelope: ServiceEnvelope):
        self.service_envelope = service_envelope
        self.write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    measurement_data = {
        NodeInfoPoint: ("node", ["long_name", "short_name", "hw_model", "role"], [], PortNum.NODEINFO_APP),
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
            ],
            PortNum.TELEMETRY_APP,
        ),
        DeviceTelemetryPoint: (
            "battery",
            [],
            ["battery_level", "voltage", "air_util_tx", "channel_utilization", "uptime_seconds"],
            PortNum.TELEMETRY_APP,
        ),
        NeighborInfoPacket: (
            "neighbor",
            ["neighbor_id", "node_id", "last_sent_by_id"],
            ["snr", "node_broadcast_interval_secs"],
            PortNum.NEIGHBORINFO_APP,
        ),
        PowerTelemetryPoint: (
            "power",
            ["channel"],
            ["voltage", "current"],
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

            if isinstance(record, list):
                logger.bind(**extra).opt(colors=True).info(
                    f"Wrote {len(record)} {measurement} packets from gateway: <green>{record[0].gateway_id}</green>"
                )
            else:
                logger.bind(**extra).opt(colors=True).info(
                    f"Wrote {measurement} packet <yellow>{record.packet_id}</yellow> from gateway: <green>{record.gateway_id}</green>"  # noqa: E501
                )
        except ApiException as e:
            if e.status == 401:
                logger.error(f"Credentials for InfluxDB are either not set or incorrect: {e}")

    def write_point(self, telemetry_data: Union[TelemetryPoint, list[TelemetryPoint]]):
        for telemetry_class, (measurement, tags, fields, port_num) in self.measurement_data.items():
            if isinstance(telemetry_data, telemetry_class):
                self.write_data(telemetry_data, measurement, fields, tags)
                break

            # The InfluxDB write API can take a list of points
            if isinstance(telemetry_data, list) and isinstance(telemetry_data[0], telemetry_class):
                self.write_data(telemetry_data, measurement, fields, tags)
                break


# TODO: Implement a JSONPacketProcessor class to process packets that come in as JSON instead of protobuf
# class JSONPacketProcessor(PacketProcessor):
#     pass


class PBPacketProcessor(PacketProcessor):
    def __init__(
        self, influx_client: InfluxDBClient, service_envelope: ServiceEnvelope, force_decode=False, auto_decrypt=True
    ):
        super().__init__(influx_client, service_envelope)

        self.force_decode = force_decode
        self.crypto_engine = CryptoEngine()

        if auto_decrypt and self.encrypted:
            self.decrypt()

    @property
    def payload_as_dict(self):
        return MessageToDict(
            self.payload,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )

    @property
    def portnum(self):
        return self.service_envelope.packet.decoded.portnum

    @property
    def portnum_protocol(self) -> Optional[KnownProtocol]:
        return protocols.get(self.portnum, None)

    @property
    def portnum_friendly_name(self) -> Optional[str]:
        return getattr(self.portnum_protocol, "name", None)

    @property
    def payload(self):
        if self.portnum_friendly_name in SUPPORTED_PACKET_TYPES:
            return self.portnum_protocol.protobufFactory.FromString(self.service_envelope.packet.decoded.payload)
        else:
            raise PacketProcessorError(
                f"We cannot yet decode: {PortNum.Name(self.portnum)}",
                portnum=self.portnum,
            )

    @property
    def encrypted(self) -> bool:
        return self.service_envelope.packet.encrypted != b""

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
        logger.bind(**point_data).debug(f"Decoded packet: {point_data}")

        try:
            if self.portnum == PortNum.NODEINFO_APP:
                return NodeInfoPoint(**point_data)
            elif self.portnum == PortNum.POSITION_APP:
                if ("latitude_i" in self.payload_as_dict and "longitude_i" in self.payload_as_dict) or self.force_decode:
                    # The GPS time field ends up being used by InfluxDB as the record time so we need to rename it
                    if point_data.get("time"):
                        point_data["gps_time"] = point_data.pop("time", None)

                    return PositionPoint(**point_data)
                else:
                    logger.bind(**self.payload_as_dict).debug("Latitude and longitude not found in payload")
                    return None
            elif self.portnum == PortNum.TELEMETRY_APP:
                if "environment_metrics" in self.payload_as_dict:
                    point_data.update(self.payload_as_dict["environment_metrics"])
                    return SensorTelemetryPoint(**point_data)
                elif "device_metrics" in self.payload_as_dict:
                    point_data.update(self.payload_as_dict["device_metrics"])
                    return DeviceTelemetryPoint(**point_data)
                elif "power_metrics" in self.payload_as_dict:
                    power_metrics = self.payload_as_dict["power_metrics"]
                    power_points = []
                    channels = set(key.split("_")[0] for key in power_metrics.keys())

                    for channel in channels:
                        power_points.append(
                            PowerTelemetryPoint(
                                **point_data,
                                channel=channel,
                                voltage=power_metrics[f"{channel}_voltage"],
                                current=power_metrics[f"{channel}_current"],
                            )
                        )
                    return power_points
            elif self.portnum == PortNum.NEIGHBORINFO_APP:
                neighbors = [
                    {"neighbor_id": neighbor.get("node_id", None), "snr": neighbor.get("snr", None)}
                    for neighbor in point_data.get("neighbors", [])
                ]

                if not neighbors:
                    logger.bind(**point_data).debug("No neighbors found in payload")
                    return None

                neighbor_points = []
                point_data.pop("neighbors")

                for neighbor in neighbors:
                    point_data["neighbor_id"] = neighbor.get("neighbor_id")

                    if neighbor.get("snr"):
                        point_data["snr"] = neighbor.get("snr")

                    neighbor_points.append(NeighborInfoPacket(**point_data))

                return neighbor_points
            elif self.portnum == PortNum.TEXT_MESSAGE_APP:
                pass
            elif self.portnum == PortNum.ADMIN_APP:
                pass
            elif self.portnum == PortNum.ROUTING_APP:
                pass
            else:
                logger.bind(portnum=self.portnum).warning(f"Unknown port number: {self.portnum}")
                logger.debug(f"Payload: {self.payload_as_dict}")
                return None
        except (AttributeError, KeyError) as e:
            logger.exception(f"{type(e).__name__}: {e}")
            return None

    def decrypt(self) -> bool:
        if not self.encrypted:
            return False

        encrypted_data = self.service_envelope.packet.encrypted
        decrypted_data = self.crypto_engine.decrypt(
            getattr(self.service_envelope.packet, "from"),
            self.service_envelope.packet.id,
            encrypted_data,
        )

        logger.debug(f"Decrypted data: {decrypted_data}")

        try:
            data = Data()
            data.ParseFromString(decrypted_data)
            self.service_envelope.packet.decoded.CopyFrom(data)
        except DecodeError as e:
            logger.exception(f"Error decrypting message: {e}")
            raise PacketProcessorError(f"Error decrypting message: {e}")

        return True


if __name__ == "__main__":
    logger.remove(file_logger)
    influx_client = InfluxDBClient.from_env_properties()
    parser = ArgumentParser()
    parser.add_argument("packet", help="Base64 encoded protobuf message")
    args = parser.parse_args()

    try:
        service_envelope = ServiceEnvelope.FromString(base64.b64decode(args.packet))
        logger.info(f"Service envelope: \n{service_envelope}")

        processor = PBPacketProcessor(influx_client, service_envelope, force_decode=True)
        logger.info(f"Decoded packet: \n{processor.payload_as_dict}")
        logger.info(f"Data: {processor.data}")

    except PacketProcessorError as e:
        logger.warning(f"Error processing packet: {e}")
    except DecodeError as e:
        logger.exception(f"Error decoding message: {e}")
    except Exception as e:
        logger.exception(f"Error processing packet: {e}")
