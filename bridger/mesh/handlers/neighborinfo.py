from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import NeighborInfoPacket
from bridger.log import logger
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class NeighborInfoHandler(PacketHandler):
    portnum = PortNum.NEIGHBORINFO_APP

    def handle(self):
        neighbors = self.base_data.pop("neighbors", None) or []

        if not neighbors:
            logger.bind(**self.base_data).debug("No neighbors found in payload")
            return None

        neighbor_points = []

        for neighbor in neighbors:
            # A fresh copy per neighbor. Mutating one shared dict let each neighbor inherit
            # the previous neighbor's snr whenever its own was missing.
            point_data = dict(self.base_data)
            point_data["neighbor_id"] = neighbor.get("node_id")

            snr = neighbor.get("snr")
            if snr is not None:
                # Explicitly not a truthiness check: proto3 omits snr when it is 0.0, and 0 dB
                # is a real reading, not a missing one.
                point_data["snr"] = snr

            neighbor_points.append(NeighborInfoPacket(**point_data))

        return neighbor_points
