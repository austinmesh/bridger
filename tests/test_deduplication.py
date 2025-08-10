from unittest.mock import MagicMock, patch

import pytest

from bridger.deduplication import PacketDeduplicator


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
        assert deduplicator.message_queue.maxlen == 100

    def test_init_custom_maxlen(self):
        deduplicator = PacketDeduplicator(maxlen=50)
        assert deduplicator.message_queue.maxlen == 50

    def test_is_duplicate_empty_queue(self, deduplicator, service_envelope):
        assert not deduplicator.is_duplicate(service_envelope)

    def test_is_duplicate_not_in_queue(self, deduplicator, service_envelope):
        deduplicator.message_queue.append(99999)
        assert not deduplicator.is_duplicate(service_envelope)

    def test_is_duplicate_in_queue(self, deduplicator, service_envelope):
        deduplicator.message_queue.append(12345)
        assert deduplicator.is_duplicate(service_envelope)

    @patch("bridger.deduplication.logger")
    def test_is_duplicate_logs_message(self, mock_logger, deduplicator, service_envelope):
        deduplicator.message_queue.append(12345)
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

    def test_bounded_deque_behavior(self, deduplicator):
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

    def test_bounded_deque_allows_reprocessing_evicted_packets(self, deduplicator):
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
        assert deduplicator_with_gateway_id.message_queue.maxlen == 3

    def test_mark_processed_adds_to_queue_with_gateway_id(self, deduplicator_with_gateway_id, service_envelope):
        deduplicator_with_gateway_id.mark_processed(service_envelope)
        assert ("!1a2b3c4d", 12345) in deduplicator_with_gateway_id.message_queue

    def test_is_duplicate_with_gateway_id_not_in_queue(self, deduplicator_with_gateway_id, service_envelope):
        deduplicator_with_gateway_id.message_queue.append(("!different", 99999))
        assert not deduplicator_with_gateway_id.is_duplicate(service_envelope)

    def test_is_duplicate_with_gateway_id_in_queue(self, deduplicator_with_gateway_id, service_envelope):
        deduplicator_with_gateway_id.message_queue.append(("!1a2b3c4d", 12345))
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

    def test_bounded_deque_behavior_with_gateway_id(self, deduplicator_with_gateway_id):
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
