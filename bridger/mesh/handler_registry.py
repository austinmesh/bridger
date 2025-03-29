from collections import defaultdict
from typing import Type

from meshtastic.protobuf.portnums_pb2 import PortNum

HANDLER_MAP = defaultdict(list)


def handler(cls: Type) -> Type:
    portnum: PortNum = getattr(cls, "portnum", None)
    if portnum is None:
        raise ValueError(f"{cls.__name__} is missing a `portnum` class attribute")
    HANDLER_MAP[portnum].append(cls)
    return cls
