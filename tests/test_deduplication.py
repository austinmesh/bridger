from unittest.mock import MagicMock, patch

import pytest

from bridger.deduplication import DEFAULT_MAXLEN, DEFAULT_TTL_SECONDS, PacketDeduplicator


@pytest.fixture
def deduplicator():
    return PacketDeduplicator(maxlen=3)


@pytest.fixture
def deduplicator_with_gateway_id():
    return PacketDeduplicator(maxlen=3, use_gateway_id=True)


@pytest.fixture
def service_envelope():
    envelope = MagicMock()
    envelope.packet.id = 12345
    envelope.gateway_id = "!1a2b3c4d"
    return envelope


@pytest.fixture
def service_envelope_different_id():
    envelope = MagicMock()
    envelope.packet.id = 67890
    envelope.gateway_id = "!1a2b3c4d"
    return envelope


@pytest.fixture
def service_envelope_different_gateway():
    envelope = MagicMock()
    envelope.packet.id = 12345
    envelope.gateway_id = "!5e6f7g8h"
    return envelope


class TestPacketDeduplicator:
    def test_init_default_maxlen(self):
        deduplicator = PacketDeduplicator()
        assert deduplicator.maxlen == DEFAULT_MAXLEN
        assert deduplicator.ttl == DEFAULT_TTL_SECONDS

    def test_init_custom_maxlen(self):
        deduplicator = PacketDeduplicator(maxlen=50)
        assert deduplicator.maxlen == 50

    def test_is_duplicate_empty_queue(self, deduplicator, service_envelope):
        assert not deduplicator.is_duplicate(service_envelope)

    def test_is_duplicate_not_in_queue(self, deduplicator, service_envelope):
        deduplicator.message_queue[99999] = deduplicator._clock()
        assert not deduplicator.is_duplicate(service_envelope)

    def test_is_duplicate_in_queue(self, deduplicator, service_envelope):
        deduplicator.message_queue[12345] = deduplicator._clock()
        assert deduplicator.is_duplicate(service_envelope)

    @patch("bridger.deduplication.logger")
    def test_is_duplicate_logs_message(self, mock_logger, deduplicator, service_envelope):
        deduplicator.message_queue[12345] = deduplicator._clock()
        deduplicator.is_duplicate(service_envelope)
        mock_logger.bind.assert_called_once_with(envelope_id=12345)

    def test_mark_processed_adds_to_queue(self, deduplicator, service_envelope):
        deduplicator.mark_processed(service_envelope)
        assert 12345 in deduplicator.message_queue

    def test_mark_processed_multiple_packets(self, deduplicator, service_envelope, service_envelope_different_id):
        deduplicator.mark_processed(service_envelope)
        deduplicator.mark_processed(service_envelope_different_id)
        assert 12345 in deduplicator.message_queue
        assert 67890 in deduplicator.message_queue
        assert len(deduplicator.message_queue) == 2

    def test_should_process_new_packet(self, deduplicator, service_envelope):
        assert deduplicator.should_process(service_envelope)
        assert 12345 in deduplicator.message_queue

    def test_should_process_duplicate_packet(self, deduplicator, service_envelope):
        deduplicator.mark_processed(service_envelope)
        assert not deduplicator.should_process(service_envelope)

    def test_should_process_different_packets(self, deduplicator, service_envelope, service_envelope_different_id):
        assert deduplicator.should_process(service_envelope)
        assert deduplicator.should_process(service_envelope_different_id)
        assert 12345 in deduplicator.message_queue
        assert 67890 in deduplicator.message_queue

    def test_should_process_same_packet_different_gateway(
        self, deduplicator, service_envelope, service_envelope_different_gateway
    ):
        assert deduplicator.should_process(service_envelope)
        assert not deduplicator.should_process(service_envelope_different_gateway)

    def test_bounded_window_behavior(self, deduplicator):
        # Fill queue to capacity (maxlen=3)
        for i in range(3):
            envelope = MagicMock()
            envelope.packet.id = i
            envelope.gateway_id = "!test"
            deduplicator.mark_processed(envelope)

        assert len(deduplicator.message_queue) == 3
        assert 0 in deduplicator.message_queue
        assert 1 in deduplicator.message_queue
        assert 2 in deduplicator.message_queue

        # Add one more, should evict the oldest (0)
        envelope = MagicMock()
        envelope.packet.id = 3
        envelope.gateway_id = "!test"
        deduplicator.mark_processed(envelope)

        assert len(deduplicator.message_queue) == 3
        assert 0 not in deduplicator.message_queue
        assert 1 in deduplicator.message_queue
        assert 2 in deduplicator.message_queue
        assert 3 in deduplicator.message_queue

    def test_bounded_window_allows_reprocessing_evicted_packets(self, deduplicator):
        # Fill queue to capacity and beyond
        envelopes = []
        for i in range(5):
            envelope = MagicMock()
            envelope.packet.id = i
            envelope.gateway_id = "!test"
            envelopes.append(envelope)
            deduplicator.mark_processed(envelope)

        # Packet 0 should have been evicted and can be processed again
        assert deduplicator.should_process(envelopes[0])
        # Packet 4 should still be in queue and be duplicate
        assert not deduplicator.should_process(envelopes[4])


class TestPacketDeduplicatorWithGatewayId:
    def test_init_with_gateway_id(self, deduplicator_with_gateway_id):
        assert deduplicator_with_gateway_id.use_gateway_id is True
        assert deduplicator_with_gateway_id.maxlen == 3

    def test_mark_processed_adds_to_queue_with_gateway_id(self, deduplicator_with_gateway_id, service_envelope):
        deduplicator_with_gateway_id.mark_processed(service_envelope)
        assert ("!1a2b3c4d", 12345) in deduplicator_with_gateway_id.message_queue

    def test_is_duplicate_with_gateway_id_not_in_queue(self, deduplicator_with_gateway_id, service_envelope):
        deduplicator_with_gateway_id.message_queue[("!different", 99999)] = deduplicator_with_gateway_id._clock()
        assert not deduplicator_with_gateway_id.is_duplicate(service_envelope)

    def test_is_duplicate_with_gateway_id_in_queue(self, deduplicator_with_gateway_id, service_envelope):
        deduplicator_with_gateway_id.message_queue[("!1a2b3c4d", 12345)] = deduplicator_with_gateway_id._clock()
        assert deduplicator_with_gateway_id.is_duplicate(service_envelope)

    def test_should_process_same_packet_different_gateway_with_gateway_id(
        self, deduplicator_with_gateway_id, service_envelope, service_envelope_different_gateway
    ):
        assert deduplicator_with_gateway_id.should_process(service_envelope)
        assert deduplicator_with_gateway_id.should_process(service_envelope_different_gateway)

    def test_should_process_duplicate_packet_same_gateway_with_gateway_id(
        self, deduplicator_with_gateway_id, service_envelope
    ):
        deduplicator_with_gateway_id.mark_processed(service_envelope)
        assert not deduplicator_with_gateway_id.should_process(service_envelope)

    def test_bounded_window_behavior_with_gateway_id(self, deduplicator_with_gateway_id):
        # Fill queue to capacity (maxlen=3)
        for i in range(3):
            envelope = MagicMock()
            envelope.packet.id = i
            envelope.gateway_id = "!test"
            deduplicator_with_gateway_id.mark_processed(envelope)

        assert len(deduplicator_with_gateway_id.message_queue) == 3
        assert ("!test", 0) in deduplicator_with_gateway_id.message_queue
        assert ("!test", 1) in deduplicator_with_gateway_id.message_queue
        assert ("!test", 2) in deduplicator_with_gateway_id.message_queue

        # Add one more, should evict the oldest (0)
        envelope = MagicMock()
        envelope.packet.id = 3
        envelope.gateway_id = "!test"
        deduplicator_with_gateway_id.mark_processed(envelope)

        assert len(deduplicator_with_gateway_id.message_queue) == 3
        assert ("!test", 0) not in deduplicator_with_gateway_id.message_queue
        assert ("!test", 1) in deduplicator_with_gateway_id.message_queue
        assert ("!test", 2) in deduplicator_with_gateway_id.message_queue
        assert ("!test", 3) in deduplicator_with_gateway_id.message_queue


def _envelope(gateway_id, packet_id):
    envelope = MagicMock()
    envelope.gateway_id = gateway_id
    envelope.packet.id = packet_id
    return envelope


class TestTTLWindow:
    @staticmethod
    def _clocked(**kwargs):
        now = [0.0]
        dedup = PacketDeduplicator(clock=lambda: now[0], **kwargs)
        return dedup, now

    def test_entries_expire_and_allow_reprocessing(self):
        dedup, now = self._clocked(ttl=60)
        envelope = _envelope("!gw", 1)

        assert dedup.should_process(envelope) is True
        assert dedup.should_process(envelope) is False

        now[0] = 61
        assert dedup.should_process(envelope) is True

    def test_entries_survive_within_the_ttl(self):
        dedup, now = self._clocked(ttl=60)
        envelope = _envelope("!gw", 1)

        dedup.should_process(envelope)
        now[0] = 59
        assert dedup.should_process(envelope) is False

    def test_expiry_is_per_entry(self):
        dedup, now = self._clocked(ttl=60)

        dedup.should_process(_envelope("!gw", 1))
        now[0] = 30
        dedup.should_process(_envelope("!gw", 2))
        now[0] = 61

        # The first has aged out, the second has not.
        assert dedup.should_process(_envelope("!gw", 1)) is True
        assert dedup.should_process(_envelope("!gw", 2)) is False

    def test_ttl_none_disables_expiry(self):
        dedup, now = self._clocked(ttl=None)
        envelope = _envelope("!gw", 1)

        dedup.should_process(envelope)
        now[0] = 10**9

        assert dedup.should_process(envelope) is False

    def test_maxlen_still_caps_the_window(self):
        dedup, _ = self._clocked(ttl=10**6, maxlen=3)

        for packet_id in range(5):
            dedup.should_process(_envelope("!gw", packet_id))

        assert len(dedup.message_queue) == 3
        assert dedup.should_process(_envelope("!gw", 0)) is True  # evicted, so seen as new
        assert dedup.should_process(_envelope("!gw", 4)) is False


class TestGatewayScoping:
    def test_same_packet_from_two_gateways_is_kept_when_scoped(self):
        # The bridge relies on this: rx_snr/rx_rssi are per-gateway measurements, so every
        # gateway's reception of a packet has to be written, not just the first to arrive.
        dedup = PacketDeduplicator(use_gateway_id=True)

        assert dedup.should_process(_envelope("!gw1", 1)) is True
        assert dedup.should_process(_envelope("!gw2", 1)) is True
        assert dedup.should_process(_envelope("!gw1", 1)) is False

    def test_same_packet_from_two_gateways_is_collapsed_when_unscoped(self):
        dedup = PacketDeduplicator(use_gateway_id=False)

        assert dedup.should_process(_envelope("!gw1", 1)) is True
        assert dedup.should_process(_envelope("!gw2", 1)) is False


class TestProtocolAgnosticApi:
    def test_packet_level_api_matches_the_envelope_api(self):
        # The (gateway_id, packet_id) entry point is what a second mesh protocol would use.
        dedup = PacketDeduplicator(use_gateway_id=True)

        assert dedup.should_process_packet("!gw", 1) is True
        assert dedup.is_duplicate(_envelope("!gw", 1)) is True


class TestWindowFullWarning:
    @staticmethod
    def _clocked(**kwargs):
        now = [0.0]
        dedup = PacketDeduplicator(clock=lambda: now[0], **kwargs)
        return dedup, now

    @patch("bridger.deduplication.logger")
    def test_no_warning_while_the_window_has_room(self, mock_logger):
        dedup, _ = self._clocked(ttl=10**6, maxlen=10)

        for packet_id in range(10):
            dedup.should_process(_envelope("!gw", packet_id))

        mock_logger.warning.assert_not_called()

    @patch("bridger.deduplication.logger")
    def test_warns_once_however_long_the_window_stays_full(self, mock_logger):
        # A saturated window is one entry over the cap on every subsequent packet, so an
        # unlatched warning fires per packet and floods the log when the bridge is busiest.
        dedup, _ = self._clocked(ttl=10**6, maxlen=3)

        for packet_id in range(100):
            dedup.should_process(_envelope("!gw", packet_id))

        assert mock_logger.warning.call_count == 1

    @patch("bridger.deduplication.logger")
    def test_rearms_once_the_window_drains(self, mock_logger):
        dedup, now = self._clocked(ttl=60, maxlen=3)

        for packet_id in range(10):
            dedup.should_process(_envelope("!gw", packet_id))

        assert mock_logger.warning.call_count == 1

        # Everything ages out, so saturating again is a fresh occurrence.
        now[0] = 1000
        for packet_id in range(100, 110):
            dedup.should_process(_envelope("!gw", packet_id))

        assert mock_logger.warning.call_count == 2
