from dataclasses import fields
from functools import lru_cache
from textwrap import dedent
from typing import Optional, Union

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS, WriteOptions
from influxdb_client.rest import ApiException

from bridger.config import INFLUXDB_V2_BUCKET, INFLUXDB_V2_WRITE_PRECISION
from bridger.dataclasses import TelemetryPoint
from bridger.log import logger

# Used by the MQTT bridge only. on_message runs on paho's network thread, so a synchronous
# HTTP round trip per point would block packet handling -- and with per-gateway deduplication
# there are several times more points than before. flush_interval bounds worst-case loss on a
# hard kill to two seconds of packets.
BRIDGE_WRITE_OPTIONS = WriteOptions(
    batch_size=200,
    flush_interval=2_000,
    jitter_interval=200,
    retry_interval=5_000,
    max_retries=5,
    max_retry_delay=30_000,
    exponential_base=2,
)


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

    def get_node_info(self, node_id: int, range: str = "-6h") -> Optional[dict]:
        query = dedent(f"""
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
        """)

        record = self._extract_first_record(self.query_data(query))
        return record.values if record else None

    def get_all_node_ids(self, range: str = "-30d") -> list[dict]:
        """Get all unique node IDs with display names from the last 30 days for autocomplete."""
        query = dedent(f"""
            import "strings"
            import "contrib/bonitoo-io/hex"

            hexify = (str) => {{
              hexString = hex.string(v: int(v: str))
              return if strings.strlen(v: hexString) == 7 then "0" + hexString else hexString
            }}

            from(bucket: "{INFLUXDB_V2_BUCKET}")
              |> range(start: {range})
              |> filter(fn: (r) => r._field == "packet_id")
              |> filter(fn: (r) => r._measurement == "node")
              |> group(columns: ["_from"])
              |> unique(column: "_from")
              |> map(fn: (r) => ({{ _value: hexify(str: r._from),
                                   name: r.short_name + " (" + hexify(str: r._from) + ") - " + r.long_name}}))
              |> sort(columns: ["_value"])
        """)

        try:
            tables = self.query_data(query)
        except ApiException as e:
            logger.error(f"Error querying InfluxDB for node IDs: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during query execution: {e}")
            return []

        if not tables:
            return []

        nodes = []
        seen_values = set()
        try:
            for table in tables:
                for record in table.records:
                    value = record.values.get("_value")
                    name = record.values.get("name")
                    if value and value not in seen_values:
                        nodes.append({"value": value, "name": name if name else value})
                        seen_values.add(value)

            return sorted(nodes, key=lambda x: x["value"])
        except Exception as e:
            logger.error(f"Error getting node IDs: {e}")
            return []

    def get_recent_packets(self, gateway_id: str, range: str = "-1h"):
        """Get recent packets for a gateway within the specified time range."""
        query = dedent(f"""
            from(bucket: "{INFLUXDB_V2_BUCKET}")
              |> range(start: {range})
              |> filter(fn: (r) => r["gateway_id"] == "{gateway_id}")
              |> filter(fn: (r) => r["_field"] == "packet_id")
              |> keep(columns: ["_from", "_time", "_measurement"])
              |> group()
              |> sort(columns: ["_time"])
        """)

        return self.query_data(query)

    @staticmethod
    def _extract_first_record(table_list):
        if not table_list:
            return None

        try:
            table = table_list[0]
        except Exception as e:
            # Guard only the indexing. The previous version read `table` out of locals() in
            # the handler, which raised KeyError when the indexing itself was what failed.
            logger.bind(table_list=repr(table_list)).error(f"Error processing query result: {e}")
            return None

        if not table.records:
            return None
        return table.records[0]


class InfluxWriter:
    def __init__(self, influx_client: InfluxDBClient, write_options=SYNCHRONOUS):
        # SYNCHRONOUS by default so callers that depend on write failures raising -- the
        # annotation command, and the tests -- are unaffected. Only the bridge opts into
        # batching, where failures surface through the callbacks instead.
        self.batching = write_options is not SYNCHRONOUS
        self.write_api = influx_client.write_api(
            write_options=write_options,
            error_callback=self._on_write_error,
            success_callback=self._on_write_success,
            retry_callback=self._on_write_retry,
        )

    @staticmethod
    def _on_write_error(conf, data, exception):
        # The callback receives serialized line protocol rather than the dataclass, so the
        # rich context available on the synchronous path is not available here.
        if isinstance(exception, ApiException) and exception.status == 401:
            logger.bind(conf=conf).error(f"Credentials for InfluxDB are either not set or incorrect: {exception}")
        else:
            logger.bind(conf=conf, data=str(data)[:500]).error(f"Failed to write batch to InfluxDB: {exception}")

    @staticmethod
    def _on_write_success(conf, data):
        logger.bind(conf=conf).debug("Wrote batch to InfluxDB")

    @staticmethod
    def _on_write_retry(conf, data, exception):
        logger.bind(conf=conf).warning(f"Retrying InfluxDB write: {exception}")

    def close(self):
        """Flush and dispose. Pending batches are lost if this is skipped."""
        self.write_api.close()

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

            verb = "Queued" if self.batching else "Wrote"

            if isinstance(record, list):
                logger.bind(**extra).opt(colors=True).info(
                    f"{verb} {len(record)} {measurement} packets from gateway: <green>{record[0].gateway_id}</green>"
                )
            else:
                logger.bind(**extra).opt(colors=True).info(
                    f"{verb} {measurement} packet <yellow>{record.packet_id}</yellow> "
                    f"from gateway: <green>{record.gateway_id}</green>"
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

    def write_annotation(self, annotation_data):
        """Write annotation data to the annotations bucket."""
        import time

        from bridger.dataclasses import AnnotationPoint

        try:
            # Set start_time to current time if not provided
            if annotation_data.start_time is None:
                annotation_data.start_time = int(time.time())

            tag_keys, field_keys = self.extract_keys(AnnotationPoint)

            self.write_api.write(
                bucket="annotations",
                record=annotation_data,
                record_measurement_name=annotation_data.measurement_name,
                record_field_keys=field_keys,
                record_tag_keys=tag_keys,
                write_precision=INFLUXDB_V2_WRITE_PRECISION,
            )

            end_info = f" to {annotation_data.end_time}" if annotation_data.end_time else ""
            logger.opt(colors=True).info(
                f"Wrote annotation for node <green>{annotation_data.node_id}</green> of type "
                f"<yellow>{annotation_data.annotation_type}</yellow> by <cyan>{annotation_data.author}</cyan> "
                f"from {annotation_data.start_time}{end_info}"
            )
        except ApiException as e:
            if e.status == 401:
                logger.error(f"Credentials for InfluxDB are either not set or incorrect: {e}")
            else:
                logger.error(f"Error writing annotation to InfluxDB: {e}")
            raise
