"""Base class for MeshCore message handlers."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    from bridger.meshcore.processor import MeshCoreMetadata


class MeshCoreHandler(ABC):
    """Base class for MeshCore message handlers.

    Attributes:
        metadata: Common metadata from the JSON message (public_key, name, ver, board)
        payload: The decoded payload (dict for stats, decoded packet dict for raw)
        data_type: The detected data type (e.g., "stats/core", "stats/radio", "packets")
    """

    def __init__(self, metadata: "MeshCoreMetadata", payload: dict, data_type: str):
        self.metadata = metadata
        self.payload = payload
        self.data_type = data_type

    @property
    def public_key(self) -> str:
        """Convenience property for accessing public_key from metadata."""
        return self.metadata.public_key

    @abstractmethod
    def handle(self) -> Union[None, Any, list[Any]]:
        """Process the payload and return data point(s) for storage.

        Returns:
            None if data should not be stored, or data point instance(s)
        """
        pass
