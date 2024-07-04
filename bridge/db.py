from abc import ABC
from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import Undefined, config, dataclass_json


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class TelemetryPoint(ABC):
    def __post_init__(self):
        if self.__class__ == TelemetryPoint:
            raise TypeError("Cannot instantiate abstract class.")

    _from: int = field(metadata=config(field_name="from"))
    to: int
    packet_id: int = field(metadata=config(field_name="id"))
    rx_time: int
    rx_snr: float
    rx_rssi: float
    hop_limit: int
    hop_start: int
    channel_id: str
    gateway_id: str


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class SensorTelemetryPoint(TelemetryPoint):
    barometric_pressure: Optional[float] = None
    current: Optional[float] = None
    gas_resistance: Optional[float] = None
    relative_humidity: Optional[float] = None
    temperature: Optional[float] = None
    voltage: Optional[float] = None
    iaq: Optional[int] = None
    channel_utilization: Optional[float] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class DeviceTelemetryPoint(TelemetryPoint):
    battery_level: Optional[int] = None
    voltage: Optional[float] = None
    air_util_tx: Optional[float] = None
    channel_utilization: Optional[float] = None
    uptime_seconds: Optional[int] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class NodeInfoPoint(TelemetryPoint):
    id: str
    long_name: str
    short_name: str
    macaddr: Optional[str] = None
    hw_model: Optional[str] = None
    role: Optional[str] = None


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass
class PositionPoint(TelemetryPoint):
    latitude_i: int
    longitude_i: int
    time: Optional[str] = None
    precision_bits: Optional[int] = None
    altitude: Optional[int] = None
    PDOP: Optional[int] = None
    sats_in_view: Optional[int] = None
