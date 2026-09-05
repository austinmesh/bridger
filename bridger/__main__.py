import signal

from paho.mqtt.client import MQTT_ERR_SUCCESS, CallbackAPIVersion
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bridger.config import MQTT_BROKER, MQTT_PASS, MQTT_PORT, MQTT_USER
from bridger.influx import create_influx_client
from bridger.log import logger
from bridger.mqtt import BridgerMQTT


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type((ConnectionError, OSError)),
    reraise=True,
)
def connect_to_mqtt(influx_client):
    logger.info(f"Attempting to connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")

    client = BridgerMQTT(influx_client, CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)

    # This will raise an exception if connection fails
    result = client.connect(MQTT_BROKER, MQTT_PORT, 60)
    if result != MQTT_ERR_SUCCESS:
        raise ConnectionError(f"MQTT connection failed with result code {result}")

    logger.info(f"Successfully connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    return client


def handle_sigterm(signum, frame):
    """Turn SIGTERM into KeyboardInterrupt so the shutdown path below runs.

    Containers are stopped with SIGTERM, not SIGINT. Without this the process dies where it
    stands and whatever is sitting in the write batch is lost on every restart.
    """
    logger.info("Received SIGTERM, shutting down...")
    raise KeyboardInterrupt


def shutdown(client, influx_client):
    if client:
        client.disconnect()
        client.loop_stop()
        client.close()  # flushes pending batches

    if influx_client:
        influx_client.close()


if __name__ == "__main__":
    client = None
    influx_client = None

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        influx_client = create_influx_client("bridger")
        client = connect_to_mqtt(influx_client)

        client.reconnect_delay_set(min_delay=5, max_delay=120)
        client.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        shutdown(client, influx_client)
