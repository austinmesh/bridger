from collections import defaultdict

from meshtastic.protobuf.portnums_pb2 import PortNum

DEFAULT_PROTOCOL = "meshtastic"

# Keyed on (protocol, message_type). Meshtastic PortNum values are small integers, so keying
# on the bare portnum would collide with any second protocol's message-type enum.
HANDLER_MAP = defaultdict(list)


def handler(cls: type) -> type:
    portnum: PortNum = getattr(cls, "portnum", None)
    if portnum is None:
        raise ValueError(f"{cls.__name__} is missing a `portnum` class attribute")

    protocol = getattr(cls, "protocol", DEFAULT_PROTOCOL)
    HANDLER_MAP[(protocol, portnum)].append(cls)
    return cls
