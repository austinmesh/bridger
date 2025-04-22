from abc import ABC, abstractmethod
from typing import Optional, Union

from meshtastic import KnownProtocol, protocols


class PacketHandler(ABC):
    def __init__(self, packet, payload_dict, base_data, strip_text: bool = True, force_decode: bool = False):
        self.packet = packet
        self.payload_dict = payload_dict
        self.base_data = base_data
        self.strip_text = strip_text
        self.force_decode = force_decode

    def __repr__(self):
        return f"{self.__class__.__name__} {self.portnum_friendly_name} ({self.portnum})"

    def __str__(self):
        return f"{self.__class__.__name__} {self.portnum_friendly_name} ({self.portnum})"

    @property
    def portnum_friendly_name(self) -> Optional[str]:
        return getattr(self.portnum_protocol, "name", None)

    @property
    def portnum_protocol(self) -> Optional[KnownProtocol]:
        return protocols.get(self.portnum, None)

    @abstractmethod
    def handle(self) -> Union[None, dict]:
        pass
