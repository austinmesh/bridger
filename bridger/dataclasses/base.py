"""Shared base ABCs for Bridger data points.

Kept in a dedicated submodule so mesh-specific modules can import them
without creating a circular dependency with ``bridger.dataclasses.__init__``
(which re-exports everything for backward-compatible top-level imports).
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import Undefined, dataclass_json


class NodeMixin:
    def _get_node_id(self) -> int:
        if hasattr(self, "_from"):
            return self._from
        elif hasattr(self, "node_id"):
            return self.node_id
        else:
            raise AttributeError("Object must have either '_from' or 'node_id' attribute")

    @property
    def node_hex_id_with_bang(self) -> str:
        return f"!{self._get_node_id():08x}"

    @property
    def node_hex_id_without_bang(self) -> str:
        return f"{self._get_node_id():08x}"

    @property
    def color(self) -> str:
        return self.node_hex_id_without_bang[-6:]


@dataclass
class NodeData(NodeMixin):
    node_id: int


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshPacketPoint(ABC):
    """Base class for mesh packet points that carry radio-level metadata.

    Both Meshtastic (``TelemetryPoint``) and MeshCore (``MeshCorePacket``)
    inherit from this to share the ``rx_snr`` / ``rx_rssi`` fields.

    The fields are declared ``kw_only=True`` so subclasses can still have
    required positional fields without violating the dataclass rule that
    non-default arguments cannot follow default ones.
    """

    def __post_init__(self):
        if self.__class__ == MeshPacketPoint:
            raise TypeError("Cannot instantiate abstract class MeshPacketPoint.")

    rx_snr: Optional[float] = field(default=None, kw_only=True, metadata={"influx_kind": "field"})
    rx_rssi: Optional[float] = field(default=None, kw_only=True, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class AnnotationPoint:
    """Grafana annotation, mesh-agnostic."""

    measurement_name = "annotation"

    node_id: str = field(metadata={"influx_kind": "tag"})
    annotation_type: str = field(metadata={"influx_kind": "tag"})
    body: str = field(metadata={"influx_kind": "field"})
    author: str = field(metadata={"influx_kind": "tag"})
    global_annotation: bool = field(default=False, metadata={"influx_kind": "tag"})
    start_time: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    end_time: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
