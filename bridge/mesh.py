from abc import ABC
from argparse import ArgumentParser
import base64
from typing import Optional, Union

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from loguru import logger
from meshtastic.mesh_pb2 import Position, User
from meshtastic.mqtt_pb2 import ServiceEnvelope
from meshtastic.portnums_pb2 import PortNum
from meshtastic.telemetry_pb2 import Telemetry

from bridge.db import DeviceTelemetryPoint, NodeInfoPoint, PositionPoint, SensorTelemetryPoint

DECODERS = {
    PortNum.NODEINFO_APP: User,
    PortNum.POSITION_APP: Position,
    PortNum.TELEMETRY_APP: Telemetry,
}

DECODER_DATA_MAPPING = {
    NodeInfoPoint: PortNum.NODEINFO_APP,
    PositionPoint: PortNum.POSITION_APP,
    SensorTelemetryPoint: PortNum.TELEMETRY_APP,
    DeviceTelemetryPoint: PortNum.TELEMETRY_APP,
}


class PacketProcessor(ABC):
    @property
    def payload_as_dict(self):
        return MessageToDict(
            self.payload,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )


# TODO: Implement a JSONPacketProcessor class to process packets that come in as JSON instead of protobuf
# class JSONPacketProcessor(PacketProcessor):
#     def __init__(self, packet: str):
#         super().__init__(packet)

#     @property
#     def payload(self) -> dict:
#         payload = self.packet.payload
#         try:
#             message = decoders[PortNum.NODEINFO_APP].FromString(payload)
#             message_dict = MessageToDict(message)
#         except KeyError as e:
#             logger.exception(f"Unknown port number: {e}")
#         except DecodeError as e:
#             logger.exception(f"Error decoding message: {e}")

#         return message_dict


class PBPacketProcessor(PacketProcessor):
    def __init__(self, service_envelope: ServiceEnvelope):
        self.service_envelope = service_envelope

        try:
            self.portnum: PortNum = service_envelope.packet.decoded.portnum

            if self.portnum in DECODERS:
                self.payload = DECODERS[self.portnum].FromString(service_envelope.packet.decoded.payload)
            else:
                logger.info(f"Skipping unknown port number: {self.portnum}")
        except KeyError as e:
            logger.exception(f"Unknown port number: {e}")
        except DecodeError as e:
            logger.exception(f"Error decoding message: {e}")

    # Return payload fit for the database dataclass models depending on the packet type
    @property
    def data(self) -> Optional[Union[NodeInfoPoint, PositionPoint, SensorTelemetryPoint, DeviceTelemetryPoint]]:
        try:
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

            # Combine the envelope fields with the payload
            point_data.update(self.payload_as_dict)

            if self.portnum == PortNum.NODEINFO_APP:
                return NodeInfoPoint(**point_data)
            elif self.portnum == PortNum.POSITION_APP:
                return PositionPoint(**point_data)
            elif self.portnum == PortNum.TELEMETRY_APP:
                if "environment_metrics" in self.payload_as_dict:
                    # move environment_metrics to top level
                    point_data.update(self.payload_as_dict["environment_metrics"])
                    return SensorTelemetryPoint(**point_data)
                elif "device_metrics" in self.payload_as_dict:
                    # move device_metrics to top level
                    point_data.update(self.payload_as_dict["device_metrics"])
                    return DeviceTelemetryPoint(**point_data)
            else:
                logger.warning(f"Unknown port number: {self.portnum}")
                return None
        except AttributeError as e:
            logger.error(f"AttributeError: {e}")
            return None
        except KeyError as e:
            logger.error(f"KeyError: {e}")
            return None

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("packet", help="Base64 encoded protobuf message")
    args = parser.parse_args()

    try:
        service_envelope = ServiceEnvelope.FromString(base64.b64decode(args.packet))
        logger.info(f"Service envelope: \n{service_envelope}")

        decoded_payload = DECODERS[service_envelope.packet.decoded.portnum].FromString(service_envelope.packet.decoded.payload)
        logger.info(f"Decoded payload: \n{decoded_payload}")

        processor = PBPacketProcessor(service_envelope)
        logger.info(f"Decoded packet: \n{processor.data}")

    except DecodeError as e:
        logger.error(f"Error decoding message: {e}")
    except Exception as e:
        logger.error(f"Error processing packet: {e}")
