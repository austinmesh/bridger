import base64

from google.protobuf.message import DecodeError
from influxdb_client import InfluxDBClient
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from paho.mqtt.client import Client
from sentry_sdk import add_breadcrumb, set_user

from bridger.config import MESHCORE_ENABLED, MESHCORE_INFLUXDB_BUCKET, MESHCORE_MQTT_TOPIC, MQTT_TOPIC
from bridger.deduplication import MeshCoreDeduplicator, PacketDeduplicator
from bridger.influx.interfaces import InfluxWriter
from bridger.log import logger
from bridger.mesh import PacketProcessorError, PBPacketProcessor
from bridger.utils import should_ignore_pki_message


class BridgerMQTT(Client):
    def __init__(self, influx_client: InfluxDBClient, *args, **kwargs):
        self.influx_client = influx_client  # Before super().__init__ call so it isn't passed to the parent class
        super().__init__(*args, **kwargs)
        self.deduplicator = PacketDeduplicator(maxlen=100)
        self.meshcore_deduplicator = MeshCoreDeduplicator(maxlen=100)
        # Extract the base prefix from meshcore topic (remove the wildcard)
        self.meshcore_topic_prefix = MESHCORE_MQTT_TOPIC.rstrip("#")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            logger.error(f"Connection failed with code: {reason_code}. Attempting to reconnect...")
            return

        # Subscribe to meshtastic topic
        subscription = self.subscribe(MQTT_TOPIC)
        if subscription[0] != 0:
            logger.error(f"Failed to subscribe to topic: {MQTT_TOPIC}")
            return

        logger.info(f"Connected and subscribed to meshtastic topic: {MQTT_TOPIC}")

        # Subscribe to meshcore topic if enabled
        if MESHCORE_ENABLED:
            mc_subscription = self.subscribe(MESHCORE_MQTT_TOPIC)
            if mc_subscription[0] != 0:
                logger.error(f"Failed to subscribe to MeshCore topic: {MESHCORE_MQTT_TOPIC}")
            else:
                logger.info(f"Subscribed to MeshCore topic: {MESHCORE_MQTT_TOPIC}")

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Disconnected")

    def on_message(self, client, userdata, message):
        # Route to appropriate handler based on topic
        if MESHCORE_ENABLED and message.topic.startswith(self.meshcore_topic_prefix):
            self._handle_meshcore_message(message)
        else:
            self._handle_meshtastic_message(message)

    def _handle_meshtastic_message(self, message):
        """Handle meshtastic MQTT messages."""
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
            influx_writer = InfluxWriter(self.influx_client)
            set_user({"id": getattr(service_envelope.packet, "from")})

            data = pb_processor.data

            if data:
                logger.bind(envelope_id=packet_id).debug(f"Trying to write data: {data}")
                influx_writer.write_point(data)
            else:
                logger.bind(envelope_id=packet_id).debug("No data to write")

        except DecodeError as e:
            self._handle_decode_error(e, breadcrumb_data, message.payload)
        except (TypeError, AttributeError) as e:
            logger.bind(**breadcrumb_data).exception(f"Error: {e}")
            logger.bind(**breadcrumb_data).debug(f"Message payload: \n{message.payload}")
        except PacketProcessorError as e:
            logger.info(e)

    def _handle_meshcore_message(self, message):
        """Handle MeshCore MQTT messages."""
        from bridger.meshcore import MCPacketProcessor, MeshCoreProcessorError

        breadcrumb_data = {"topic": message.topic, "payload_size": len(message.payload)}

        logger.bind(**breadcrumb_data).opt(colors=True).info(f"MeshCore message on topic <cyan>{message.topic}</cyan>")
        add_breadcrumb(level="info", data=breadcrumb_data, category="mqtt.meshcore", message="Received MeshCore message")

        try:
            processor = MCPacketProcessor(message.topic, message.payload)

            # Deduplicate packet messages by (public_key, message_hash).
            # Same hash from different observers is kept (distinct SNR/RSSI);
            # status messages have no hash and skip the check.
            if processor.message_hash and not self.meshcore_deduplicator.should_process(
                processor.message_hash, processor.public_key
            ):
                return

            data = processor.data

            if data:
                influx_writer = InfluxWriter(self.influx_client)
                # Status messages return a list of different point types (different measurements),
                # so write each individually. Packet messages return a single point.
                if isinstance(data, list):
                    for point in data:
                        influx_writer.write_point(point, bucket=MESHCORE_INFLUXDB_BUCKET)
                else:
                    influx_writer.write_point(data, bucket=MESHCORE_INFLUXDB_BUCKET)
                logger.bind(**breadcrumb_data).info(f"Wrote MeshCore data: {data}")
            else:
                logger.bind(**breadcrumb_data).info(f"No MeshCore data to write for data_type: {processor.data_type}")

        except MeshCoreProcessorError as e:
            logger.bind(**breadcrumb_data).info(f"MeshCore processing: {e}")
        except Exception as e:
            logger.bind(**breadcrumb_data).exception(f"Error processing MeshCore message: {e}")

    def _handle_decode_error(self, error, breadcrumb_data, payload):
        logger.bind(**breadcrumb_data).warning(f"We received a message that can't be decoded as a protobuf: {error}")

        try:
            json_payload = payload.decode("utf-8")
            logger.bind(**breadcrumb_data).debug(f"Message payload: \n{json_payload}")
        except UnicodeDecodeError as e:
            logger.bind(**breadcrumb_data).warning(f"Message payload is not JSON: {e}")
        finally:
            logger.bind(**breadcrumb_data).warning("Message payload is not a protobuf or JSON")
