from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import NeighborInfoPacket
from bridger.log import logger
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class NeighborInfoHandler(PacketHandler):
    portnum = PortNum.NEIGHBORINFO_APP

    def handle(self):
        neighbors = [
            {"neighbor_id": neighbor.get("node_id", None), "snr": neighbor.get("snr", None)}
            for neighbor in self.base_data.get("neighbors", [])
        ]

        if not neighbors:
            logger.bind(**self.base_data).debug("No neighbors found in payload")
            return None

        neighbor_points = []
        self.base_data.pop("neighbors")

        for neighbor in neighbors:
            self.base_data["neighbor_id"] = neighbor.get("neighbor_id")

            if neighbor.get("snr"):
                self.base_data["snr"] = neighbor.get("snr")

            neighbor_points.append(NeighborInfoPacket(**self.base_data))

        return neighbor_points
