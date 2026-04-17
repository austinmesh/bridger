"""MeshCore-specific data point dataclasses."""

from abc import ABC
from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import Undefined, dataclass_json

from bridger.dataclasses.base import MeshPacketPoint


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCorePacket(MeshPacketPoint):
    """Base class for data points from the meshcore/{IATA}/{PK}/packets topic.

    Carries the common envelope metadata present on every packet message:
    the observer relay that received it and the radio-level fields
    (rx_snr, rx_rssi via :class:`MeshPacketPoint`, plus direction, route,
    score, duration) along with the relay's mqtt_hash identifier.
    """

    def __post_init__(self):
        if self.__class__ == MeshCorePacket:
            raise TypeError("Cannot instantiate abstract class MeshCorePacket.")

    public_key: str = field(metadata={"influx_kind": "tag"})
    iata: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    origin: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    # Envelope metadata from the packet JSON
    mqtt_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    direction: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    route: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    score: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    duration: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreStatus(ABC):
    """Base class for data points from the meshcore/{IATA}/{PK}/status topic.

    Carries device info (firmware version, model, etc.) from observer/gateway
    health reports.
    """

    def __post_init__(self):
        if self.__class__ == MeshCoreStatus:
            raise TypeError("Cannot instantiate abstract class MeshCoreStatus.")

    public_key: str = field(metadata={"influx_kind": "tag"})
    iata: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    origin: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    name: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    ver: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    board: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreStatusPoint(MeshCoreStatus):
    """Observer/gateway online status."""

    measurement_name = "mc_status"

    status: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    source: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    client_version: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    radio: Optional[str] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreStatsCorePoint(MeshCoreStatus):
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
class MeshCoreStatsRadioPoint(MeshCoreStatus):
    """Observer radio stats (noise_floor, air time)."""

    measurement_name = "mc_stats_radio"

    noise_floor: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    last_rssi: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    last_snr: Optional[float] = field(default=None, metadata={"influx_kind": "field"})
    tx_air_secs: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    rx_air_secs: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreHopPoint(MeshCorePacket):
    """Individual hop in a packet's path through the mesh.

    One point per hop, enabling queries like "all packets through node X"
    and reconstruction of node-to-node links for geomaps.
    """

    measurement_name = "mc_hop"

    hop_hash: Optional[str] = field(default=None, metadata={"influx_kind": "tag"})
    hop_index: Optional[int] = field(default=None, metadata={"influx_kind": "field"})
    path_length: Optional[int] = field(default=None, metadata={"influx_kind": "field"})


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCorePacketPoint(MeshCorePacket):
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


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreAdvertPoint(MeshCorePacket):
    """Advert packet data (PayloadType.Advert = 4).

    Contains device advertisement with name, location, and role.
    """

    measurement_name = "mc_advert"

    # Packet-level fields from decoded packet
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


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class MeshCoreTracePoint(MeshCorePacket):
    """Trace packet data (PayloadType.Trace = 9).

    Contains route tracing information.
    """

    measurement_name = "mc_trace"

    # Packet-level fields from decoded packet
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
