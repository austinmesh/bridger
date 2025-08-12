import base64
from argparse import ArgumentParser

from google.protobuf.message import DecodeError
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope

from bridger.influx import create_influx_client
from bridger.log import file_logger, logger
from bridger.mesh import PacketProcessorError, PBPacketProcessor

if __name__ == "__main__":
    logger.remove(file_logger)
    influx_client = create_influx_client("cli")
    parser = ArgumentParser()
    parser.add_argument("packet", help="Base64 encoded protobuf message")
    args = parser.parse_args()

    try:
        service_envelope = ServiceEnvelope.FromString(base64.b64decode(args.packet))
        logger.info(f"Service envelope: \n{service_envelope}")

        processor = PBPacketProcessor(service_envelope, force_decode=True)
        logger.info(f"Decoded packet: \n{processor.payload_dict}")
        logger.info(f"Data: {processor.data}")

    except PacketProcessorError as e:
        logger.warning(f"Error processing packet: {e}")
    except DecodeError as e:
        logger.exception(f"Error decoding message: {e}")
    except Exception as e:
        logger.exception(f"Error processing packet: {e}")
