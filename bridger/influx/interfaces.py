from dataclasses import fields
from functools import lru_cache
from textwrap import dedent
from typing import Union

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

from bridger.config import INFLUXDB_V2_BUCKET, INFLUXDB_V2_WRITE_PRECISION
from bridger.dataclasses import TelemetryPoint
from bridger.log import logger


class InfluxReader:
    def __init__(self, influx_client: InfluxDBClient):
        self.query_api = influx_client.query_api()

    def query_data(self, query: str):
        try:
            return self.query_api.query(query)
        except ApiException as e:
            if e.status == 401:
                logger.bind(query=query).error(f"Credentials for InfluxDB are either not set or incorrect: {e}")
            else:
                logger.bind(query=query).error(f"Error querying InfluxDB: {e}")
        return None

    def get_node_info(self, node_id: int, range: str = "-6h") -> Union[dict, None]:
        query = dedent(
            f"""
            import "strings"
            import "contrib/bonitoo-io/hex"

            hexify = (str) => {{
              hexString = hex.string(v: int(v: str))
              return if strings.strlen(v: hexString) == 7 then "0" + hexString else hexString
            }}

            from(bucket: "{INFLUXDB_V2_BUCKET}")
              |> range(start: {range})
              |> filter(fn: (r) => r._measurement == "node" and r._from == "{node_id}" and r._field == "packet_id")
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> group(columns: ["_from"])
              |> last(column: "_from")
              |> map(fn: (r) => ({{ r with user_id: "!" + hexify(str: r._from) }}))
        """
        )

        record = self._extract_first_record(self.query_data(query))
        return record.values if record else None

    @staticmethod
    def _extract_first_record(table_list):
        if not table_list:
            return None
        try:
            table = table_list[0]
            if not table.records:
                return None
            return table.records[0]
        except Exception as e:
            extra = {k: locals()[k] for k in ("table_list", "table")}
            logger.bind(**extra).error(f"Error processing query result: {e}")
            return None


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
                logger.bind(**extra).error(f"Credentials for InfluxDB are either not set or incorrect: {e}")
            else:
                logger.bind(**extra).error(f"Error writing to InfluxDB: {e}")

    def write_point(self, telemetry_data: Union[TelemetryPoint, list[TelemetryPoint]]):
        if not telemetry_data:
            return

        point_cls = type(telemetry_data[0]) if isinstance(telemetry_data, list) else type(telemetry_data)
        measurement = getattr(point_cls, "measurement_name", None)
        tag_keys, field_keys = self.extract_keys(point_cls)

        if measurement:
            self.write_data(telemetry_data, measurement, field_keys, tag_keys)

    @staticmethod
    @lru_cache(maxsize=64)
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
