from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import TraceroutePoint
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class TracerouteHandler(PacketHandler):
    portnum = PortNum.TRACEROUTE_APP

    def handle(self):
        # TODO: The fields could be lists so we need to send each list item as a separate point
        return TraceroutePoint(**self.base_data)
