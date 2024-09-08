from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import TextMessagePoint
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler


@handler
class TextHandler(PacketHandler):
    portnum = PortNum.TEXT_MESSAGE_APP

    def handle(self):
        if "text" in self.payload_dict:
            # We are leaving out the actual text property here as we don't want to store actual messages
            if self.strip_text:
                self.base_data.pop("text", None)
            return TextMessagePoint(**self.base_data)
        return None
