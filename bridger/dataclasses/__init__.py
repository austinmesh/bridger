"""Bridger data-point dataclasses used for InfluxDB serialization.

Submodules:
    - ``base``: shared ABCs and non-mesh-specific points (annotations).
    - ``meshtastic``: Meshtastic-specific telemetry points.
    - ``meshcore``: MeshCore packet and status points.

This package re-exports all public names so existing call sites can continue
to use ``from bridger.dataclasses import X`` regardless of which submodule
``X`` lives in.
"""

from bridger.dataclasses.base import (  # noqa: F401
    AnnotationPoint,
    MeshPacketPoint,
    NodeData,
    NodeMixin,
)
from bridger.dataclasses.meshcore import (  # noqa: F401
    MeshCoreAdvertPoint,
    MeshCoreHopPoint,
    MeshCorePacket,
    MeshCorePacketPoint,
    MeshCoreStatsCorePoint,
    MeshCoreStatsRadioPoint,
    MeshCoreStatus,
    MeshCoreStatusPoint,
    MeshCoreTracePoint,
)
from bridger.dataclasses.meshtastic import (  # noqa: F401
    DeviceTelemetryPoint,
    NeighborInfoPacket,
    NodeInfoPoint,
    PositionPoint,
    PowerTelemetryPoint,
    SensorTelemetryPoint,
    TelemetryPoint,
    TextMessagePoint,
    TraceroutePoint,
)
