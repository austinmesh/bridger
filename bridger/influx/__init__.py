from influxdb_client import InfluxDBClient
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bridger.log import logger


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type((ConnectionError, OSError, Exception)),
    reraise=True,
)
def create_influx_client(component_name: str = "application") -> InfluxDBClient:
    logger.info(f"Attempting to connect to InfluxDB for {component_name}...")

    client = InfluxDBClient.from_env_properties()
    ready = client.ping()

    if not ready:
        raise ConnectionError(f"Cannot ping InfluxDB at {client.url}. Is it running?")

    logger.info(f"Successfully connected to InfluxDB at {client.url} for {component_name}")
    return client
