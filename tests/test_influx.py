from unittest.mock import MagicMock

import pytest

from bridger.dataclasses import PositionPoint
from bridger.influx import InfluxWriter


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
