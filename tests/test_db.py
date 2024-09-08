import pytest

from bridger.dataclasses import DeviceTelemetryPoint, NodeInfoPoint, PositionPoint, SensorTelemetryPoint, TelemetryPoint


@pytest.fixture
def common_parameters_good():
    return {
        "_from": 111222333,
        "to": 444555666,
        "packet_id": 123456789,
        "rx_time": 123456789,
        "rx_snr": 6.5,
        "rx_rssi": 7.5,
        "hop_limit": 2,
        "hop_start": 3,
        "channel_id": "LongFast",
        "gateway_id": "!db32fae4",
    }


class TestHappyPathPoints:
    def test_telemetry_point(self, common_parameters_good):
        with pytest.raises(TypeError):
            TelemetryPoint(**common_parameters_good)

    def test_node_info_point(self, common_parameters_good):
        node_info = NodeInfoPoint(**common_parameters_good, id=3764567, long_name="test", short_name="test")
        assert node_info.id == 3764567
        assert node_info.long_name == "test"
        assert node_info.short_name == "test"
        assert node_info._from == 111222333
        assert node_info.to == 444555666
        assert node_info.role is None

    def test_sensor_telemetry_point(self, common_parameters_good):
        sensor_telemetry = SensorTelemetryPoint(**common_parameters_good, barometric_pressure=1.0, temperature=96.0)
        assert sensor_telemetry.barometric_pressure == 1.0
        assert sensor_telemetry.temperature == 96.0

    def test_position_point(self, common_parameters_good):
        position = PositionPoint(**common_parameters_good, latitude_i=30293845, longitude_i=9736521)
        assert position.latitude_i == 30293845
        assert position.longitude_i == 9736521

    def test_device_telemetry_point(self, common_parameters_good):
        device_telemetry = DeviceTelemetryPoint(**common_parameters_good, voltage=1.0, battery_level=1)
        assert device_telemetry.voltage == 1.0
        assert device_telemetry.battery_level == 1


class TestExtraArgumentsPasses:
    def test_telemetry_point(self, common_parameters_good):
        with pytest.raises(TypeError):
            TelemetryPoint(**common_parameters_good, extra=1)

    def test_node_info_point(self, common_parameters_good):
        node_info = NodeInfoPoint(**common_parameters_good, id=3764567, long_name="test", short_name="test", extra=1)

        with pytest.raises(AttributeError):
            node_info.extra

    def test_sensor_telemetry_point(self, common_parameters_good):
        sensor_telemetry = SensorTelemetryPoint(**common_parameters_good, barometric_pressure=1.0, temperature=96.0, extra=1)

        with pytest.raises(AttributeError):
            sensor_telemetry.extra

    def test_position_point(self, common_parameters_good):
        position = PositionPoint(**common_parameters_good, latitude_i=30293845, longitude_i=9736521, extra=1)

        with pytest.raises(AttributeError):
            position.extra

    def test_device_telemetry_point(self, common_parameters_good):
        device_telemetry = DeviceTelemetryPoint(**common_parameters_good, voltage=1.0, battery_level=1, extra=1)

        with pytest.raises(AttributeError):
            device_telemetry.extra
