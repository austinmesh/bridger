from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import NodeInfoPoint
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class NodeInfoHandler(PacketHandler):
    portnum = PortNum.NODEINFO_APP

    def handle(self):
        return NodeInfoPoint(**self.base_data)
