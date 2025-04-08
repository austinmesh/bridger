from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import PositionPoint
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class PositionHandler(PacketHandler):
    portnum = PortNum.POSITION_APP

    def handle(self):
        if "latitude_i" in self.payload_dict and "longitude_i" in self.payload_dict:
            # The GPS time field ends up being used by InfluxDB as the record time so we need to rename it
            if self.base_data.get("time"):
                self.base_data["gps_time"] = self.base_data.pop("time", None)

            return PositionPoint(**self.base_data)
