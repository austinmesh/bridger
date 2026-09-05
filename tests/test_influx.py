from unittest.mock import MagicMock

import pytest
from influxdb_client.rest import ApiException

from bridger.dataclasses import AnnotationPoint, PositionPoint
from bridger.influx.interfaces import InfluxReader, InfluxWriter


@pytest.fixture
def mock_write_api():
    return MagicMock()


@pytest.fixture
def influx_client(mock_write_api):
    client = MagicMock()
    client.write_api.return_value = mock_write_api
    return client


@pytest.fixture
def influx_writer(influx_client):
    return InfluxWriter(influx_client)


@pytest.fixture
def position_point():
    return PositionPoint(
        _from=1,
        to=2,
        packet_id=123,
        rx_time=1111,
        rx_snr=5.0,
        rx_rssi=-40,
        hop_limit=3,
        hop_start=3,
        channel_id="Test",
        gateway_id="!abcd1234",
        latitude_i=1000000,
        longitude_i=2000000,
        altitude=50,
        precision_bits=10,
        speed=0,
        time=1234567890,
    )


class TestInfluxWriter:
    def test_common_tags_included_in_write(self, influx_writer: InfluxWriter, position_point):
        writer = InfluxWriter(influx_writer)
        writer.write_point(position_point)

        # Extract the tag keys argument from the call to write()
        tag_keys = influx_writer.write_api().write.call_args.kwargs.get("record_tag_keys", [])

        # Check that common tags are included
        expected_tags = {"channel_id", "gateway_id", "_from", "to"}
        assert expected_tags.issubset(set(tag_keys))

    def test_write_single_point(self, influx_writer: InfluxWriter, mock_write_api, position_point):
        influx_writer.write_point(position_point)
        assert mock_write_api.write.called
        args, kwargs = mock_write_api.write.call_args
        assert kwargs["record"] == position_point
        assert "record_field_keys" in kwargs
        assert "record_tag_keys" in kwargs
        assert "position" in kwargs["record_measurement_name"]

    def test_write_multiple_points(self, influx_writer, mock_write_api, position_point):
        influx_writer.write_point([position_point, position_point])
        assert mock_write_api.write.called
        args, kwargs = mock_write_api.write.call_args
        assert isinstance(kwargs["record"], list)
        assert len(kwargs["record"]) == 2

    def test_extracts_tags_and_fields(self, influx_writer, mock_write_api, position_point):
        influx_writer.write_point(position_point)
        _, kwargs = mock_write_api.write.call_args
        tags = kwargs["record_tag_keys"]
        fields = kwargs["record_field_keys"]

        # Check expected common tags
        assert "_from" in tags
        assert "gateway_id" in tags
        assert "channel_id" in tags

        # Check some fields
        assert "rx_time" in fields
        assert "latitude_i" in fields
        assert "altitude" in fields


class _RaisingList(list):
    """Truthy, but indexing blows up -- the shape that broke the old error handler."""

    def __bool__(self):
        return True

    def __getitem__(self, index):
        raise RuntimeError("boom")


@pytest.fixture
def query_api():
    return MagicMock()


@pytest.fixture
def influx_reader(query_api):
    client = MagicMock()
    client.query_api.return_value = query_api
    return InfluxReader(client)


def _table(records):
    table = MagicMock()
    table.records = records
    return table


def _record(values):
    record = MagicMock()
    record.values = values
    return record


class TestExtractFirstRecord:
    def test_returns_the_first_record(self):
        record = _record({"a": 1})

        assert InfluxReader._extract_first_record([_table([record])]) is record

    def test_none_for_an_empty_result(self):
        assert InfluxReader._extract_first_record([]) is None
        assert InfluxReader._extract_first_record(None) is None

    def test_none_when_the_table_has_no_records(self):
        assert InfluxReader._extract_first_record([_table([])]) is None

    def test_returns_none_instead_of_raising_from_the_handler(self):
        # It used to read `table` out of locals() while reporting the error, but the failure
        # it was guarding is what binds `table` -- so it raised KeyError: 'table' instead.
        assert InfluxReader._extract_first_record(_RaisingList()) is None


class TestQueryData:
    def test_returns_query_results(self, influx_reader, query_api):
        query_api.query.return_value = ["table"]

        assert influx_reader.query_data('from(bucket: "x")') == ["table"]

    def test_none_on_a_credentials_error(self, influx_reader, query_api):
        query_api.query.side_effect = ApiException(status=401)

        assert influx_reader.query_data("query") is None

    def test_none_on_any_api_error(self, influx_reader, query_api):
        query_api.query.side_effect = ApiException(status=500)

        assert influx_reader.query_data("query") is None


class TestGetNodeInfo:
    def test_returns_the_record_values(self, influx_reader, query_api):
        query_api.query.return_value = [_table([_record({"short_name": "ABCD", "long_name": "A Node"})])]

        assert influx_reader.get_node_info(123) == {"short_name": "ABCD", "long_name": "A Node"}

    def test_none_for_an_unknown_node(self, influx_reader, query_api):
        query_api.query.return_value = []

        assert influx_reader.get_node_info(123) is None

    def test_queries_the_requested_node_and_range(self, influx_reader, query_api):
        query_api.query.return_value = []

        influx_reader.get_node_info(123, range="-12h")

        query = query_api.query.call_args[0][0]
        assert 'r._from == "123"' in query
        assert "range(start: -12h)" in query


class TestGetAllNodeIds:
    def test_deduplicates_and_sorts(self, influx_reader, query_api):
        query_api.query.return_value = [
            _table(
                [
                    _record({"_value": "cbaf0421", "name": "CBAF"}),
                    _record({"_value": "0a1b2c3d", "name": "ABCD"}),
                    _record({"_value": "cbaf0421", "name": "CBAF"}),
                ]
            )
        ]

        assert influx_reader.get_all_node_ids() == [
            {"value": "0a1b2c3d", "name": "ABCD"},
            {"value": "cbaf0421", "name": "CBAF"},
        ]

    def test_falls_back_to_the_value_when_there_is_no_name(self, influx_reader, query_api):
        query_api.query.return_value = [_table([_record({"_value": "cbaf0421", "name": None})])]

        assert influx_reader.get_all_node_ids() == [{"value": "cbaf0421", "name": "cbaf0421"}]

    def test_empty_list_when_the_query_fails(self, influx_reader, query_api):
        query_api.query.side_effect = ApiException(status=500)

        assert influx_reader.get_all_node_ids() == []


class TestGetRecentPackets:
    def test_filters_by_gateway(self, influx_reader, query_api):
        query_api.query.return_value = ["table"]

        assert influx_reader.get_recent_packets("!cbaf0421") == ["table"]

        query = query_api.query.call_args[0][0]
        assert '"gateway_id"] == "!cbaf0421"' in query


class TestWriteAnnotation:
    def test_defaults_start_time_to_now(self, influx_writer, mock_write_api):
        annotation = AnnotationPoint(node_id="cbaf0421", annotation_type="reposition", body="moved", author="andy")

        influx_writer.write_annotation(annotation)

        assert annotation.start_time is not None
        assert mock_write_api.write.call_args.kwargs["bucket"] == "annotations"

    def test_keeps_an_explicit_start_time(self, influx_writer, mock_write_api):
        annotation = AnnotationPoint(
            node_id="cbaf0421", annotation_type="reposition", body="moved", author="andy", start_time=1600000000
        )

        influx_writer.write_annotation(annotation)

        assert annotation.start_time == 1600000000

    def test_reraises_so_the_command_can_report_it(self, influx_writer, mock_write_api):
        mock_write_api.write.side_effect = ApiException(status=500)

        with pytest.raises(ApiException):
            influx_writer.write_annotation(
                AnnotationPoint(node_id="cbaf0421", annotation_type="reposition", body="moved", author="andy")
            )
