import base64
import os
from collections import deque

from google.protobuf.message import DecodeError
from influxdb_client import InfluxDBClient
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from paho.mqtt.client import Client
from sentry_sdk import add_breadcrumb, set_user

from bridge.log import logger
from bridge.mesh import PacketProcessorError, PBPacketProcessor

MQTT_TOPIC = os.getenv("MQTT_TOPIC", "egr/home/2/e/#")


class BridgerMQTT(Client):
    def __init__(self, influx_client: InfluxDBClient, *args, **kwargs):
        self.influx_client = influx_client  # Before super().__init__ call so it isn't passed to the parent class
        super().__init__(*args, **kwargs)
        self.message_queue = deque(maxlen=100)  # Bounded deque for message queue

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

    def on_message(self, client, userdata, message):
        message_payload = base64.b64encode(message.payload)
        breadcrumb_data = {"topic": message.topic, "payload": message_payload}

        logger.bind(**breadcrumb_data).debug(f"Message payload base64 encoded: {message_payload}")
        add_breadcrumb(level="info", data=breadcrumb_data, category="mqtt", message="Received message")

        try:
            service_envelope = ServiceEnvelope.FromString(message.payload)
            packet_id = service_envelope.packet.id
            gateway_id = service_envelope.gateway_id

            if packet_id in self.message_queue:
                logger.bind(envelope_id=packet_id).opt(colors=True).debug(
                    f"Packet <yellow>{packet_id}</yellow> from {gateway_id} already in queue"
                )
                return

            self.message_queue.append(packet_id)  # Append packet_id to bounded deque

            pb_processor = PBPacketProcessor(self.influx_client, service_envelope)
            set_user({"id": getattr(service_envelope.packet, "from")})
            pb_processor.write_point(pb_processor.data)

        except DecodeError as e:
            self._handle_decode_error(e, breadcrumb_data, message.payload)
        except (TypeError, AttributeError) as e:
            logger.bind(**breadcrumb_data).exception(f"Error: {e}")
            logger.bind(**breadcrumb_data).debug(f"Message payload: \n{message.payload}")
        except PacketProcessorError as e:
            logger.info(e)

    def _handle_decode_error(self, error, breadcrumb_data, payload):
        logger.bind(**breadcrumb_data).warning(f"We received a message that can't be decoded as a protobuf: {error}")

        try:
            json_payload = payload.decode("utf-8")
            logger.bind(**breadcrumb_data).debug(f"Message payload: \n{json_payload}")
        except UnicodeDecodeError as e:
            logger.bind(**breadcrumb_data).warning(f"Message payload is not JSON: {e}")
        finally:
            logger.bind(**breadcrumb_data).warning("Message payload is not a protobuf or JSON")
