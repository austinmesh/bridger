"""Base class for MeshCore message handlers."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from bridger.meshcore.processor import MeshCoreMetadata


class MeshCoreHandler(ABC):
    """Base class for MeshCore message handlers.

    Attributes:
        metadata: Common metadata (public_key, iata, origin, name, ver, board)
        payload: The decoded payload (dict for stats/status, decoded packet dict for packets)
        data_type: The data type from the topic ("packets" or "status")
    """

    def __init__(self, metadata: "MeshCoreMetadata", payload: dict, data_type: str):
        self.metadata = metadata
        self.payload = payload
        self.data_type = data_type

    @property
    def public_key(self) -> str:
        return self.metadata.public_key

    @property
    def iata(self) -> str:
        return self.metadata.iata

    @property
    def origin(self) -> Optional[str]:
        return self.metadata.origin

    @abstractmethod
    def handle(self) -> Union[None, Any, list[Any]]:
        """Process the payload and return data point(s) for storage."""
        pass
