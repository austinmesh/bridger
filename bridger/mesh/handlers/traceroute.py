from meshtastic.protobuf.portnums_pb2 import PortNum

from bridger.dataclasses import TracerouteHopPoint
from bridger.log import logger
from bridger.mesh.base import PacketHandler
from bridger.mesh.handler_registry import handler

# RouteDiscovery carries SNR as an int scaled by 4, with -128 meaning "unknown".
SNR_SCALE = 4
UNKNOWN_SNR = -128

# Stripped from base_data before constructing a point: these are the raw repeated fields
# the hops are derived from, not values on any single hop.
TRACEROUTE_PAYLOAD_KEYS = {"route", "snr_towards", "route_back", "snr_back"}


@handler
class TracerouteHandler(PacketHandler):
    portnum = PortNum.TRACEROUTE_APP

    def handle(self):
        # For a traceroute response, packet.to is the node that asked and packet.from is the
        # node that answered, so the forward path runs to -> route... -> from.
        origin = self.base_data.get("to")
        responder = self.base_data.get("_from")

        points = self._legs(
            "towards",
            [origin, *self.payload_dict.get("route", []), responder],
            self.payload_dict.get("snr_towards", []),
        )
        points += self._legs(
            "back",
            [responder, *self.payload_dict.get("route_back", []), origin],
            self.payload_dict.get("snr_back", []),
        )

        return points or None

    def _legs(self, direction, nodes, snrs):
        # A traceroute request carries an empty RouteDiscovery, and a direction with no SNR at
        # all tells us nothing the packet's own rx_snr does not. Skip both rather than writing
        # rows that only restate the adjacency.
        if not snrs:
            return []

        expected = len(nodes) - 1

        if len(snrs) != expected:
            logger.bind(direction=direction, nodes=nodes, snrs=list(snrs)).debug(
                "Traceroute SNR list length does not match the route; emitting hops without SNR"
            )
            snrs = []

        points = []

        for index in range(expected):
            point_data = {k: v for k, v in self.base_data.items() if k not in TRACEROUTE_PAYLOAD_KEYS}
            point_data.update(
                direction=direction,
                hop_index=index,
                from_node_id=nodes[index],
                node_id=nodes[index + 1],
                route_length=expected,
                snr=self._snr(snrs, index),
            )
            points.append(TracerouteHopPoint(**point_data))

        return points

    @staticmethod
    def _snr(snrs, index):
        if index >= len(snrs) or snrs[index] == UNKNOWN_SNR:
            return None

        return snrs[index] / SNR_SCALE
