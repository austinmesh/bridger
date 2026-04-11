from abc import ABC
from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import Undefined, config, dataclass_json


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


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCorePoint(ABC):
    """Base class for MeshCore data points."""

    def __post_init__(self):
        if self.__class__ == MeshCorePoint:
            raise TypeError("Cannot instantiate abstract class MeshCorePoint.")

    public_key: str = field(metadata={"influx_kind": "tag"})
    iata: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    origin: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    name: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    ver: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    board: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreStatusPoint(MeshCorePoint):
    """Observer/gateway online status."""

    measurement_name = "mc_status"

    status: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    source: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    client_version: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    radio: Optional[str] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreStatsCorePoint(MeshCorePoint):
    """Observer core stats (battery, uptime, errors, queue_len)."""

    measurement_name = "mc_stats_core"

    battery_mv: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    uptime_secs: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    errors: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    queue_len: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    debug_flags: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    recv_errors: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreStatsRadioPoint(MeshCorePoint):
    """Observer radio stats (noise_floor, air time)."""

    measurement_name = "mc_stats_radio"

    noise_floor: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    last_rssi: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    last_snr: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    tx_air_secs: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    rx_air_secs: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCorePacketPoint(MeshCorePoint):
    """Decoded packet metadata (from meshcoredecoder).

    Used as fallback for unknown payload types or types without specific handlers.
    """

    measurement_name = "mc_packet"

    message_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    route_type: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    payload_type: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    payload_version: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    path_length: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    total_bytes: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    is_valid: Optional[bool] = field(default=None, metadata={"influx_kind": "field"})

    # Envelope metadata from the observer relay
    snr: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    rssi: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    direction: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    mqtt_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreAdvertPoint(MeshCorePoint):
    """Advert packet data (PayloadType.Advert = 4).

    Contains device advertisement with name, location, and role.
    """

    measurement_name = "mc_advert"

    # Packet-level fields
    message_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    route_type: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    payload_type: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    path_length: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    total_bytes: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    is_valid: Optional[bool] = field(default=None, metadata={"influx_kind": "field"})

    # Advert-specific fields from payload.decoded
    sender_public_key: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    timestamp: Optional[int] = field(default=None, metadata={"influx_kind": "field"})

    # From appData
    device_name: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    device_role: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    flags: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    has_location: Optional[bool] = field(default=None, metadata={"influx_kind": "field"})
    latitude: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    longitude: Optional[float] = field(default=None, metadata={"influx_kind": "field"})

    # Envelope metadata from the observer relay
    snr: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    rssi: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    direction: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    mqtt_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreTracePoint(MeshCorePoint):
    """Trace packet data (PayloadType.Trace = 9).

    Contains route tracing information.
    """

    measurement_name = "mc_trace"

    # Packet-level fields
    message_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    route_type: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    payload_type: Optional[int] = field(default=None, metadata={"influx_kind": "tag"})
    path_length: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    total_bytes: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    is_valid: Optional[bool] = field(default=None, metadata={"influx_kind": "field"})

    # Trace-specific fields from payload.decoded
    trace_tag: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    auth_code: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    flags: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    # Store path_hashes as comma-separated string since InfluxDB doesn't support lists
    path_hashes: Optional[str] = field(default=None, metadata={"influx_kind": "field"})

    # Envelope metadata from the observer relay
    snr: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    rssi: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    direction: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    mqtt_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
