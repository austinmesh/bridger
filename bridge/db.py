import os
from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import Undefined, config, dataclass_json
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
from loguru import logger

INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "meshtastic")
INFLUX_ORG = os.getenv("INFLUX_ORG", "austinmesh")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class TelemetryPoint:
    _from: int = field(metadata=config(field_name="from"))
    to: int
    packet_id: int = field(metadata=config(field_name="id"))
    rx_time: int
    rx_snr: float
    rx_rssi: float
    hop_limit: int
    hop_start: int
    channel_id: str
    gateway_id: str


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class SensorTelemetryPoint(TelemetryPoint):
    barometric_pressure: Optional[float] = None
    current: Optional[float] = None
    gas_resistance: Optional[float] = None
    relative_humidity: Optional[float] = None
    temperature: Optional[float] = None
    voltage: Optional[float] = None
    iaq: Optional[int] = None
    channel_utilization: Optional[float] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class DeviceTelemetryPoint(TelemetryPoint):
    battery_level: Optional[int] = None
    voltage: Optional[float] = None
    air_util_tx: Optional[float] = None
    channel_utilization: Optional[float] = None
    uptime_seconds: Optional[int] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class NodeInfoPoint(TelemetryPoint):
    id: str
    long_name: str
    short_name: str
    macaddr: Optional[str] = None
    hw_model: Optional[str] = None
    role: Optional[str] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class PositionPoint(TelemetryPoint):
    latitude_i: int
    longitude_i: int
    time: Optional[str] = None
    precision_bits: Optional[int] = None
    altitude: Optional[int] = None
    PDOP: Optional[int] = None
    sats_in_view: Optional[int] = None


def write_point(telemetry_data: TelemetryPoint):
    common_fields = ["rx_time", "rx_snr", "rx_rssi", "hop_limit", "hop_start"]
    common_tags = ["channel_id", "gateway_id", "_from", "to"]

    def write_data(record, record_measurement_name, record_field_keys, record_tag_keys):
        try:
            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=record,
                record_measurement_name=record_measurement_name,
                record_field_keys=record_field_keys + common_fields,
                record_tag_keys=record_tag_keys + common_tags,
            )
        except ApiException as e:
            if e.status == 401:
                logger.error(f"Credentials for InfluxDB are either not set or incorrect: {e}")

    if isinstance(telemetry_data, NodeInfoPoint):
        node_info_tags = ["long_name", "short_name", "hw_model"]
        node_info_fields = []
        write_data(telemetry_data, "node", node_info_fields, node_info_tags)

    elif isinstance(telemetry_data, PositionPoint):
        position_tags = []
        position_fields = ["latitude_i", "longitude_i", "altitude", "precision_bits", "speed", "time"]
        write_data(telemetry_data, "position", position_fields, position_tags)

    elif isinstance(telemetry_data, SensorTelemetryPoint):
        sensor_tags = []
        sensor_fields = [
            "air_util_tx",
            "channel_utilization",
            "barometric_pressure",
            "current",
            "gas_resistance",
            "relative_humidity",
            "temperature",
            "voltage",
            "uptime_seconds",
        ]
        write_data(telemetry_data, "sensor", sensor_fields, sensor_tags)

    elif isinstance(telemetry_data, DeviceTelemetryPoint):
        battery_tags = []
        battery_fields = ["battery_level", "voltage", "air_util_tx", "channel_utilization"]
        write_data(telemetry_data, "battery", battery_fields, battery_tags)
