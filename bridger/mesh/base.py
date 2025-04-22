from abc import ABC, abstractmethod
from typing import Union


class PacketHandler(ABC):
    def __init__(self, packet, payload_dict, base_data, strip_text: bool = True, force_decode: bool = False):
        self.packet = packet
        self.payload_dict = payload_dict
        self.base_data = base_data
        self.strip_text = strip_text
        self.force_decode = force_decode

    @abstractmethod
    def handle(self) -> Union[None, dict]:
        pass
