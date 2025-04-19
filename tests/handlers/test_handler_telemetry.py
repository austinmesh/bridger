from bridger.dataclasses import DeviceTelemetryPoint, PowerTelemetryPoint, SensorTelemetryPoint
from bridger.mesh.handlers.telemetry import TelemetryHandler


class TestTelemetryHandler:
    def setup_method(self):
        self.base_data = {
            "_from": 1,
            "to": 4294967295,
            "packet_id": 1234,
            "rx_time": 1725990585,
            "rx_snr": 5.0,
            "rx_rssi": -50,
            "hop_limit": 3,
            "hop_start": 3,
            "channel_id": "test",
            "gateway_id": "test_gateway",
        }

    def test_environment_metrics(self):
        handler = TelemetryHandler(
            packet=None,
            payload_dict={"environment_metrics": {"temperature": 25.3, "humidity": 50.2}},
            base_data=self.base_data.copy(),
        )
        result = handler.handle()
        assert isinstance(result, SensorTelemetryPoint)
        assert result.temperature == 25.3

    def test_device_metrics(self):
        handler = TelemetryHandler(
            packet=None,
            payload_dict={"device_metrics": {"voltage": 3.7, "battery_level": 85}},
            base_data=self.base_data.copy(),
        )
        result = handler.handle()
        assert isinstance(result, DeviceTelemetryPoint)
        assert result.voltage == 3.7

    def test_power_metrics_complete(self):
        payload = {
            "power_metrics": {
                "ch1_voltage": 5.0,
                "ch1_current": 0.4,
                "ch2_voltage": 6.1,
                "ch2_current": 0.8,
            }
        }
        handler = TelemetryHandler(packet=None, payload_dict=payload, base_data=self.base_data.copy())
        result = handler.handle()
        assert isinstance(result, list)
        assert all(isinstance(p, PowerTelemetryPoint) for p in result)
        assert len(result) == 2

    def test_power_metrics_incomplete(self):
        payload = {
            "power_metrics": {
                "ch1_voltage": 5.0,
                # Missing ch1_current
                "ch2_current": 0.8,
                # Missing ch2_voltage
                "ch3_voltage": 4.1,
                "ch3_current": 0.5,
            }
        }
        handler = TelemetryHandler(packet=None, payload_dict=payload, base_data=self.base_data.copy())
        result = handler.handle()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].channel == "ch3"
        assert result[0].voltage == 4.1
        assert result[0].current == 0.5
