import pytest

from bridger.dataclasses import TracerouteHopPoint
from bridger.influx.interfaces import InfluxWriter
from bridger.mesh.handlers.traceroute import TracerouteHandler

REQUESTER = 0xBBBB
RESPONDER = 0xAAAA


class TestTracerouteHandler:
    def setup_method(self):
        self.base_data = {
            "_from": RESPONDER,
            "to": REQUESTER,
            "packet_id": 789,
            "rx_time": 1600000000,
            "rx_snr": 12.5,
            "rx_rssi": -30,
            "hop_limit": 3,
            "hop_start": 3,
            "channel_id": "LongFast",
            "gateway_id": "!abc123",
        }

    def handle(self, payload):
        return TracerouteHandler(packet=None, payload_dict=payload, base_data={**self.base_data, **payload}).handle()

    def test_forward_path_is_one_point_per_hop(self):
        # Forward path runs requester -> route... -> responder, and each SNR is measured by
        # the receiver of that leg.
        points = self.handle({"route": [0x1111, 0x2222], "snr_towards": [20, 12, 8]})

        assert [(p.hop_index, p.from_node_id, p.node_id, p.snr) for p in points] == [
            (0, REQUESTER, 0x1111, 5.0),
            (1, 0x1111, 0x2222, 3.0),
            (2, 0x2222, RESPONDER, 2.0),
        ]
        assert {p.direction for p in points} == {"towards"}
        assert {p.route_length for p in points} == {3}

    def test_direct_connection_is_a_single_hop(self):
        points = self.handle({"snr_towards": [24]})

        assert len(points) == 1
        assert (points[0].from_node_id, points[0].node_id, points[0].snr) == (REQUESTER, RESPONDER, 6.0)

    def test_round_trip_emits_both_directions(self):
        points = self.handle(
            {
                "route": [0x1111],
                "snr_towards": [20, 12],
                "route_back": [0x1111],
                "snr_back": [16, 8],
            }
        )

        towards = [p for p in points if p.direction == "towards"]
        back = [p for p in points if p.direction == "back"]

        assert [(p.from_node_id, p.node_id) for p in towards] == [(REQUESTER, 0x1111), (0x1111, RESPONDER)]
        assert [(p.from_node_id, p.node_id) for p in back] == [(RESPONDER, 0x1111), (0x1111, REQUESTER)]

    def test_unknown_snr_sentinel_becomes_none(self):
        # -128 means "unknown", not -32 dB.
        points = self.handle({"route": [0x1111], "snr_towards": [20, -128]})

        assert [p.snr for p in points] == [5.0, None]

    def test_zero_snr_is_preserved(self):
        points = self.handle({"snr_towards": [0]})

        assert points[0].snr == 0.0

    def test_a_traceroute_request_writes_nothing(self):
        # A request carries an empty RouteDiscovery, so MessageToDict yields {}.
        assert self.handle({}) is None

    def test_a_direction_without_snr_is_skipped(self):
        points = self.handle({"route": [0x1111], "snr_towards": [20, 12], "route_back": [0x1111]})

        assert {p.direction for p in points} == {"towards"}

    def test_mismatched_snr_length_still_emits_hops(self):
        points = self.handle({"route": [0x1111, 0x2222], "snr_towards": [20]})

        assert len(points) == 3
        assert [p.snr for p in points] == [None, None, None]

    def test_raw_route_fields_do_not_leak_onto_the_point(self):
        points = self.handle({"route": [0x1111], "snr_towards": [20, 12]})

        assert not hasattr(points[0], "route")
        assert not hasattr(points[0], "snr_towards")


class TestTracerouteInfluxMapping:
    def test_tags_and_fields(self):
        tags, fields = InfluxWriter.extract_keys(TracerouteHopPoint)

        # hop_index and direction must be tags: with no explicit timestamp the server assigns
        # ingest time, so as fields every hop would collapse into one series and overwrite.
        for tag in ("direction", "hop_index", "from_node_id", "node_id"):
            assert tag in tags, f"{tag} must be a tag"

        for field_name in ("snr", "route_length"):
            assert field_name in fields, f"{field_name} must be a field"


def _telemetry_point_subclasses():
    from bridger.dataclasses import TelemetryPoint

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return sorted(set(walk(TelemetryPoint)), key=lambda c: c.__name__)


# Fields deliberately never written to InfluxDB. Listing them explicitly means a new omission
# has to be a conscious decision rather than an oversight.
INTENTIONALLY_UNWRITTEN = {
    ("TextMessagePoint", "text"),  # we record that a message happened, never its contents
    ("NodeInfoPoint", "id"),  # the hex form of _from, which is already a tag
}


@pytest.mark.parametrize("point_cls", _telemetry_point_subclasses(), ids=lambda c: c.__name__)
def test_every_point_field_declares_an_influx_kind(point_cls):
    """Guard against the bug that motivated this change.

    TraceroutePoint declared route/snr_towards/route_back/snr_back with no influx_kind, so
    extract_keys silently dropped all four and the measurement recorded nothing useful.
    """
    from dataclasses import fields as dataclass_fields

    missing = [
        f.name
        for f in dataclass_fields(point_cls)
        if "influx_kind" not in f.metadata and (point_cls.__name__, f.name) not in INTENTIONALLY_UNWRITTEN
    ]

    assert not missing, f"{point_cls.__name__} fields without an influx_kind: {missing}"
