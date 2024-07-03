import base64
import os

from google.protobuf.message import DecodeError
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from paho.mqtt.client import Client
from sentry_sdk import add_breadcrumb, set_user

from bridge.db import write_point
from bridge.log import logger
from bridge.mesh import PacketProcessorError, PBPacketProcessor

MQTT_TOPIC = os.getenv("MQTT_TOPIC", "egr/home/2/e/#")


class MeshBridge(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            logger.error(f"Connection failed with code: {reason_code}. Attempting to reconnect...")
            return

        subscription = self.subscribe(MQTT_TOPIC)

        if subscription[0] != 0:
            logger.error(f"Failed to subscribe to topic: {MQTT_TOPIC}")
            return

        logger.info(f"Connected and subscribed to topic: {MQTT_TOPIC}")

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Disconnected")
            return

    def on_message(self, client, userdata, message):
        received_message = "Received message"
        message_payload = base64.b64encode(message.payload)
        breadcrumb_data = {"topic": message.topic, "payload": message_payload}

        logger.bind(**breadcrumb_data).debug(f"Message payload base64 encoded: {message_payload}")
        add_breadcrumb(level="info", data=breadcrumb_data, category="mqtt", message=received_message)

        try:
            serice_envelope = ServiceEnvelope.FromString(message.payload)
            pb_processor = PBPacketProcessor(serice_envelope)
        except DecodeError as e:
            # This is a common error when the message is not a protobuf
            logger.bind(**breadcrumb_data).warning(f"We received a message that can't be decoded as a protobuf: {e}")

            # Try decoding as JSON
            try:
                json_payload = message.payload.decode("utf-8")
                logger.bind(**breadcrumb_data).debug(f"Message payload: \n{json_payload}")
            except UnicodeDecodeError as e:
                logger.bind(**breadcrumb_data).warning(f"Message payload is not JSON: {e}")
            finally:
                logger.bind(**breadcrumb_data).warning("Message payload is not a protobuf or JSON")
                return

        except TypeError as e:
            # This is more like we don't have a payload or the payload is empty
            logger.bind(**breadcrumb_data).exception(f"Error writing point: {e}")
            logger.bind(**breadcrumb_data).debug(f"Message payload: \n{message.payload}")

        except PacketProcessorError as e:
            logger.info(e)
            return

        set_user({"id": getattr(serice_envelope.packet, "from")})
        write_point(pb_processor.data)
