from abc import ABC
from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import Undefined, config, dataclass_json


@dataclass
class NodeMixin:
    @property
    def node_hex_id_with_bang(self) -> str:
        if hasattr(self, "_from"):
            return f"!{self._from:08x}"
        elif hasattr(self, "node_id"):
            return f"!{self.node_id:08x}"
        elif hasattr(self, "node_hex_id"):
            # Handle GatewayData case where we already have hex_id
            if self.node_hex_id.startswith("!"):
                return self.node_hex_id
            return f"!{self.node_hex_id}"
        else:
            raise AttributeError("Object must have either '_from', 'node_id', or 'node_hex_id' attribute")

    @property
    def node_hex_id_without_bang(self) -> str:
        if hasattr(self, "node_hex_id"):
            # Handle GatewayData case where we already have hex_id
            return self.node_hex_id.lstrip("!")
        else:
            return self.node_hex_id_with_bang[1:]

    @property
    def color(self) -> str:
        return self.node_hex_id_without_bang[-6:]


@dataclass
class NodeData(NodeMixin):
    node_id: int


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class TelemetryPoint(ABC):
    def __post_init__(self):
        if self.__class__ == TelemetryPoint:
            raise TypeError("Cannot instantiate abstract class.")

    _from: int = field(metadata=config(field_name="from", metadata={"influx_kind": "tag"}))
    to: int = field(metadata={"influx_kind": "tag"})
    packet_id: int = field(metadata=config(field_name="id", metadata={"influx_kind": "field"}))
    rx_time: int = field(metadata={"influx_kind": "field"})
    rx_snr: float = field(metadata={"influx_kind": "field"})
    rx_rssi: float = field(metadata={"influx_kind": "field"})
    hop_limit: int = field(metadata={"influx_kind": "field"})
    hop_start: int = field(metadata={"influx_kind": "field"})
    channel_id: str = field(metadata={"influx_kind": "tag"})
    gateway_id: str = field(metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class SensorTelemetryPoint(TelemetryPoint):
    measurement_name = "sensor"

    barometric_pressure: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    current: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    gas_resistance: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    relative_humidity: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    temperature: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    voltage: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    iaq: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    channel_utilization: Optional[float] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class DeviceTelemetryPoint(TelemetryPoint):
    measurement_name = "battery"

    battery_level: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    voltage: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    air_util_tx: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    channel_utilization: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    uptime_seconds: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class NodeInfoPoint(TelemetryPoint):
    measurement_name = "node"

    id: str
    long_name: str = field(metadata={"influx_kind": "tag"})
    short_name: str = field(metadata={"influx_kind": "tag"})
    macaddr: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    hw_model: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    role: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class PositionPoint(TelemetryPoint):
    measurement_name = "position"

    latitude_i: int = field(metadata={"influx_kind": "field"})
    longitude_i: int = field(metadata={"influx_kind": "field"})
    gps_time: Optional[str] = field(default=None, metadata={"influx_kind": "field"})
    precision_bits: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    altitude: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    PDOP: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    sats_in_view: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class NeighborInfoPacket(TelemetryPoint):
    measurement_name = "neighbor"

    node_id: int = field(metadata={"influx_kind": "tag"})
    last_sent_by_id: int = field(metadata={"influx_kind": "tag"})
    neighbor_id: int = field(metadata={"influx_kind": "tag"})
    node_broadcast_interval_secs: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    snr: Optional[float] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class PowerTelemetryPoint(TelemetryPoint):
    measurement_name = "power"

    voltage: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    current: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    channel: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class TextMessagePoint(TelemetryPoint):
    measurement_name = "message"

    text: Optional[str] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class TraceroutePoint(TelemetryPoint):
    measurement_name = "traceroute"

    route: Optional[int] = None
    snr_towards: Optional[int] = None
    route_back: Optional[int] = None
    snr_back: Optional[int] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class AnnotationPoint:
    measurement_name = "annotation"

    node_id: str = field(metadata={"influx_kind": "tag"})
    annotation_type: str = field(metadata={"influx_kind": "tag"})
    body: str = field(metadata={"influx_kind": "field"})
    author: str = field(metadata={"influx_kind": "tag"})
    global_annotation: bool = field(default=False, metadata={"influx_kind": "tag"})
    start_time: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    end_time: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
