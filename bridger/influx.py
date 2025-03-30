import os
from dataclasses import fields
from typing import Union

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

from bridger.dataclasses import TelemetryPoint
from bridger.log import logger

INFLUXDB_V2_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "meshtastic")
INFLUXDB_V2_WRITE_PRECISION = os.getenv("INFLUXDB_V2_WRITE_PRECISION", "s")  # s, ms, us, or ns


class InfluxWriter:
    def __init__(self, influx_client: InfluxDBClient):
        self.write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    def write_data(self, record, measurement, fields, tags):
        try:
            extra = {
                "measurement": measurement,
                "tags": tags,
                "fields": fields,
                "record": record,
            }

            self.write_api.write(
                bucket=INFLUXDB_V2_BUCKET,
                record=record,
                record_measurement_name=measurement,
                record_field_keys=fields,
                record_tag_keys=tags,
                write_precision=INFLUXDB_V2_WRITE_PRECISION,
            )

            if isinstance(record, list):
                logger.bind(**extra).opt(colors=True).info(
                    f"Wrote {len(record)} {measurement} packets from gateway: <green>{record[0].gateway_id}</green>"
                )
            else:
                logger.bind(**extra).opt(colors=True).info(
                    f"Wrote {measurement} packet <yellow>{record.packet_id}</yellow> from gateway: <green>{record.gateway_id}</green>"  # noqa: E501
                )
        except ApiException as e:
            if e.status == 401:
                logger.error(f"Credentials for InfluxDB are either not set or incorrect: {e}")

    def write_point(self, telemetry_data: Union[TelemetryPoint, list[TelemetryPoint]]):
        def extract_keys(cls):
            tag_keys = []
            field_keys = []
            for f in fields(cls):
                kind = f.metadata.get("influx_kind")
                if kind == "tag":
                    tag_keys.append(f.name)
                elif kind == "field":
                    field_keys.append(f.name)
            return tag_keys, field_keys

        point_cls = type(telemetry_data[0]) if isinstance(telemetry_data, list) else type(telemetry_data)
        measurement = getattr(point_cls, "measurement_name", None)
        tag_keys, field_keys = extract_keys(point_cls)

        if measurement:
            self.write_data(telemetry_data, measurement, field_keys, tag_keys)
