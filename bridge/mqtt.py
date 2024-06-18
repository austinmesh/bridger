import os
import base64
from collections import deque

from google.protobuf.message import DecodeError
from loguru import logger
from paho.mqtt.client import CallbackAPIVersion, Client
from meshtastic.mqtt_pb2 import ServiceEnvelope
from sentry_sdk import add_breadcrumb, set_user

from bridge.db import write_point
from bridge.mesh import PBPacketProcessor

MQTT_TOPIC = os.getenv("MQTT_TOPIC", "egr/home/2/json/#")
MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.110")
MQTT_USER = os.getenv("MQTT_USER", "station")
MQTT_PASS = os.getenv("MQTT_PASS")


class MeshBridge(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.subscribe(MQTT_TOPIC)
        logger.success(f"Connected and subscribed to topic: {MQTT_TOPIC}")

    def on_message(self, client, userdata, message):
        received_message = f"Received message on topic {message.topic}"
        logger.info(received_message)
        add_breadcrumb(data=base64.b64encode(message.payload), category="mqtt", message=received_message)

        try:
            serice_envelope = ServiceEnvelope.FromString(message.payload)
            set_user({"id": getattr(serice_envelope.packet, "from")})

            pb_processor = PBPacketProcessor(serice_envelope)
            write_point(pb_processor.data)
        except DecodeError as e:
            logger.error(f"Error decoding protobuf message: {e}")
        except TypeError as e:
            logger.error(f"Error writing point: {e}")
            logger.debug(f"Message payload: \n{message.payload}")
            logger.debug(f"Service envelope: \n{pb_processor.service_envelope}")


if __name__ == "__main__":
    try:
        client = MeshBridge(CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_BROKER, 1883, 60)
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        logger.info("Exiting...")
        client.disconnect()
        client.loop_stop()
        client = None
