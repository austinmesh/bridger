import base64
from abc import ABC, abstractmethod
from typing import Optional, Union

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError, Message
from meshtastic import KnownProtocol, protocols
from meshtastic.protobuf.mesh_pb2 import Data
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import PortNum

import bridger.mesh.handlers  # noqa: F401 # We need to import handlers to register them in the HANDLER_MAP
from bridger.crypto import CryptoEngine
from bridger.dataclasses import TelemetryPoint
from bridger.log import logger
from bridger.mesh.handler_registry import HANDLER_MAP


class PacketProcessorError(Exception):
    def __init__(self, message, portnum=None):
        super().__init__(message)
        self.portnum = portnum


class PacketProcessor(ABC):
    def __init__(self, service_envelope: ServiceEnvelope, strip_text: bool = True):
        self.service_envelope = service_envelope
        self.strip_text = strip_text

    @property
    @abstractmethod
    def payload_dict(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def data(self):
        raise NotImplementedError


class PBPacketProcessor(PacketProcessor):
    def __init__(
        self,
        service_envelope: ServiceEnvelope,
        force_decode=False,
        auto_decrypt=True,
        **kwargs,
    ):
        super().__init__(service_envelope, **kwargs)

        self.force_decode = force_decode
        self.crypto_engine = CryptoEngine()

        if auto_decrypt and self.encrypted:
            self.decrypt()

    @property
    def payload_dict(self):
        if isinstance(self.payload, str):
            return {"text": self.payload}
        elif isinstance(self.payload, bytes):
            return {"data": base64.b64encode(self.payload).decode("ascii")}
        else:
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
    def payload(self) -> Union[Message, str, bytes]:
        if self.portnum in HANDLER_MAP:
            payload = self.service_envelope.packet.decoded.payload

            if self.portnum_protocol.protobufFactory:
                return self.portnum_protocol.protobufFactory.FromString(payload)
            else:
                try:
                    return payload.decode("utf-8")
                except UnicodeDecodeError:
                    return payload
        elif self.service_envelope.channel_id == "PKI":
            raise PacketProcessorError(
                f"We cannot decrypt PKI messages: {self.service_envelope.packet}",
                portnum=self.portnum,
            )
        else:
            raise PacketProcessorError(
                f"We cannot yet decode: {PortNum.Name(self.portnum)}",
                portnum=self.portnum,
            )

    @property
    def encrypted(self) -> bool:
        return self.service_envelope.packet.encrypted != b""

    @property
    def data(self) -> Union[TelemetryPoint, list[TelemetryPoint], None]:
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

        point_data.update(self.payload_dict)
        logger.bind(**point_data).debug(f"Decoded packet: {point_data}")

        try:
            for handler_cls in HANDLER_MAP.get(self.portnum, []):
                handler = handler_cls(
                    packet, self.payload_dict, point_data, strip_text=self.strip_text, force_decode=self.force_decode
                )
                result = handler.handle()

                if result:
                    return result

            logger.bind(portnum=self.portnum).warning(f"No matching handler for port number: {self.portnum}")
            logger.debug(f"Payload: {self.payload_dict}")
            return None

        except (AttributeError, KeyError, TypeError) as e:
            logger.exception(f"{type(e).__name__}: {e}")
            return None

    def decrypt(self) -> bool:
        if not self.encrypted:
            return False

        if self.service_envelope.channel_id == "PKI":
            logger.debug("This is a PKI packet so we cannot decrypt it")
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
