import base64

from google.protobuf.message import DecodeError
from influxdb_client import InfluxDBClient
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from paho.mqtt.client import Client
from sentry_sdk import add_breadcrumb, set_user

from bridger.config import MQTT_TOPIC
from bridger.deduplication import PacketDeduplicator
from bridger.influx.interfaces import BRIDGE_WRITE_OPTIONS, InfluxWriter
from bridger.log import logger
from bridger.mesh import PacketProcessorError, PBPacketProcessor
from bridger.utils import should_ignore_pki_message


class BridgerMQTT(Client):
    def __init__(self, influx_client: InfluxDBClient, *args, **kwargs):
        self.influx_client = influx_client  # Before super().__init__ call so it isn't passed to the parent class
        super().__init__(*args, **kwargs)
        # Scoped by gateway: rx_snr, rx_rssi and the hop counts are per-gateway measurements,
        # and gateway_id is a tag, so collapsing on packet id alone threw away every reception
        # after the first to arrive.
        self.deduplicator = PacketDeduplicator(use_gateway_id=True)
        # One writer for the process. A new WriteApi per message meant a fresh batching
        # pipeline per message, and rebuilding it defeats batching entirely.
        self.influx_writer = InfluxWriter(influx_client, write_options=BRIDGE_WRITE_OPTIONS)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            logger.error(f"Connection failed with code: {reason_code}. Attempting to reconnect...")
            return

        # This result is paho's local error code, not the broker's. A broker that denies the
        # subscription still returns success here, which is why on_subscribe exists below.
        subscription = self.subscribe(MQTT_TOPIC)
        if subscription[0] != 0:
            logger.error(f"Failed to subscribe to topic: {MQTT_TOPIC}")
            return

        logger.info(f"Requested subscription to topic: {MQTT_TOPIC}")

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        """Report the broker's SUBACK.

        Without this a denied subscription looks identical to a healthy one: the bridge logs
        that it subscribed and then silently receives nothing at all.
        """
        for reason_code in reason_code_list:
            if getattr(reason_code, "is_failure", False):
                logger.error(f"Broker refused subscription to {MQTT_TOPIC}: {reason_code}. No packets will arrive.")
            else:
                logger.info(f"Subscribed to {MQTT_TOPIC} with QoS {reason_code.value}")

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Disconnected")

    def close(self):
        """Flush pending writes. Batched points are lost otherwise."""
        self.influx_writer.close()

    def on_message(self, client, userdata, message):
        message_payload = base64.b64encode(message.payload)
        breadcrumb_data = {"topic": message.topic, "payload": message_payload}

        logger.bind(**breadcrumb_data).opt(colors=True).debug(
            f"MQTT message on topic <green>{message.topic}</green>: {message_payload}"
        )
        add_breadcrumb(level="info", data=breadcrumb_data, category="mqtt", message="Received message")

        # Ignoring PKI messages for now as we cannot decrypt them without storing keys somewhere
        if should_ignore_pki_message(message.topic):
            logger.bind(**breadcrumb_data).debug(f"Ignoring PKI message on topic {message.topic}")
            return

        try:
            service_envelope = ServiceEnvelope.FromString(message.payload)

            if not self.deduplicator.should_process(service_envelope):
                return

            packet_id = service_envelope.packet.id
            pb_processor = PBPacketProcessor(service_envelope)
            set_user({"id": getattr(service_envelope.packet, "from")})

            data = pb_processor.data

            if data:
                logger.bind(envelope_id=packet_id).debug(f"Trying to write data: {data}")
                self.influx_writer.write_point(data)
            else:
                logger.bind(envelope_id=packet_id).debug("No data to write")

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
