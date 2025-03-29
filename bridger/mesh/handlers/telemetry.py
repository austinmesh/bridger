from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import DeviceTelemetryPoint, PowerTelemetryPoint, SensorTelemetryPoint
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class TelemetryHandler(PacketHandler):
    portnum = PortNum.TELEMETRY_APP

    def handle(self):
        if "environment_metrics" in self.payload_dict:
            self.base_data.update(self.payload_dict["environment_metrics"])
            return SensorTelemetryPoint(**self.base_data)
        elif "device_metrics" in self.payload_dict:
            self.base_data.update(self.payload_dict["device_metrics"])
            return DeviceTelemetryPoint(**self.base_data)
        elif "power_metrics" in self.payload_dict:
            power_metrics = self.payload_dict["power_metrics"]
            power_points = []
            channels = set(key.split("_")[0] for key in power_metrics.keys())

            for channel in channels:
                power_points.append(
                    PowerTelemetryPoint(
                        **self.base_data,
                        channel=channel,
                        voltage=power_metrics[f"{channel}_voltage"],
                        current=power_metrics[f"{channel}_current"],
                    )
                )
            return power_points
