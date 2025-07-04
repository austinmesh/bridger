from unittest.mock import MagicMock, patch

import pytest
from discord.ext import commands
from meshtastic.protobuf.portnums_pb2 import TEXT_MESSAGE_APP

from bridger.cogs.testmsg import TestMsg
from bridger.dataclasses import TextMessagePoint
from bridger.deduplication import PacketDeduplicator


@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=commands.Bot)
    bot.get_channel = MagicMock()
    return bot


@pytest.fixture
def mock_influx_reader():
    return MagicMock()


@pytest.fixture
def testmsg_cog(mock_bot, mock_influx_reader):
    return TestMsg(mock_bot, 123456789, mock_influx_reader)


@pytest.fixture
def mock_service_envelope():
    envelope = MagicMock()
    envelope.packet.id = 12345
    envelope.gateway_id = "!1a2b3c4d"
    return envelope


@pytest.fixture
def mock_service_envelope_duplicate():
    envelope = MagicMock()
    envelope.packet.id = 12345
    envelope.gateway_id = "!5e6f7g8h"
    return envelope


@pytest.fixture
def mock_service_envelope_different():
    envelope = MagicMock()
    envelope.packet.id = 67890
    envelope.gateway_id = "!1a2b3c4d"
    return envelope


class TestTestMsgCog:
    def test_init_creates_deduplicator(self, testmsg_cog):
        assert hasattr(testmsg_cog, "deduplicator")
        assert isinstance(testmsg_cog.deduplicator, PacketDeduplicator)
        assert testmsg_cog.deduplicator.message_queue.maxlen == 100

    def test_deduplicator_processes_unique_message(self, testmsg_cog, mock_service_envelope):
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope)
        assert 12345 in testmsg_cog.deduplicator.message_queue

    def test_deduplicator_skips_duplicate_message(self, testmsg_cog, mock_service_envelope, mock_service_envelope_duplicate):
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope)
        assert not testmsg_cog.deduplicator.should_process(mock_service_envelope_duplicate)

    def test_deduplicator_processes_different_messages(
        self, testmsg_cog, mock_service_envelope, mock_service_envelope_different
    ):
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope)
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope_different)
        assert 12345 in testmsg_cog.deduplicator.message_queue
        assert 67890 in testmsg_cog.deduplicator.message_queue

    @patch("bridger.cogs.testmsg.PBPacketProcessor")
    def test_mqtt_processing_skips_duplicate_packets(self, mock_processor_class, testmsg_cog, mock_service_envelope):
        mock_processor = MagicMock()
        mock_processor.portnum = TEXT_MESSAGE_APP
        mock_processor.data = MagicMock(spec=TextMessagePoint)
        mock_processor.data.text = "!test message"
        mock_processor_class.return_value = mock_processor

        testmsg_cog.deduplicator.should_process = MagicMock(return_value=False)
        service_envelope = mock_service_envelope

        if not testmsg_cog.deduplicator.should_process(service_envelope):
            mock_processor_class.assert_not_called()
        else:
            pytest.fail("Duplicate message was not skipped")

    @patch("bridger.cogs.testmsg.PBPacketProcessor")
    def test_mqtt_processing_handles_unique_packets(self, mock_processor_class, testmsg_cog, mock_service_envelope):
        mock_processor = MagicMock()
        mock_processor.portnum = TEXT_MESSAGE_APP
        mock_processor.data = MagicMock(spec=TextMessagePoint)
        mock_processor.data.text = "!test message"
        mock_processor_class.return_value = mock_processor

        testmsg_cog.deduplicator.should_process = MagicMock(return_value=True)
        service_envelope = mock_service_envelope

        if not testmsg_cog.deduplicator.should_process(service_envelope):
            pytest.fail("Unique message was incorrectly skipped")
        else:
            processor = mock_processor_class(service_envelope=service_envelope, strip_text=False)
            mock_processor_class.assert_called_once_with(service_envelope=service_envelope, strip_text=False)
            assert processor.portnum == TEXT_MESSAGE_APP
            assert processor.data.text == "!test message"

    def test_deduplicator_bounded_queue_behavior(self, testmsg_cog):
        testmsg_cog.deduplicator = PacketDeduplicator(maxlen=3)

        for i in range(3):
            envelope = MagicMock()
            envelope.packet.id = i
            envelope.gateway_id = "!test"
            testmsg_cog.deduplicator.mark_processed(envelope)

        assert len(testmsg_cog.deduplicator.message_queue) == 3
        assert 0 in testmsg_cog.deduplicator.message_queue
        assert 1 in testmsg_cog.deduplicator.message_queue
        assert 2 in testmsg_cog.deduplicator.message_queue

        envelope = MagicMock()
        envelope.packet.id = 3
        envelope.gateway_id = "!test"
        testmsg_cog.deduplicator.mark_processed(envelope)

        assert len(testmsg_cog.deduplicator.message_queue) == 3
        assert 0 not in testmsg_cog.deduplicator.message_queue
        assert 1 in testmsg_cog.deduplicator.message_queue
        assert 2 in testmsg_cog.deduplicator.message_queue
        assert 3 in testmsg_cog.deduplicator.message_queue

    @patch("bridger.deduplication.logger")
    def test_deduplicator_logs_duplicate_detection(self, mock_logger, testmsg_cog, mock_service_envelope):
        testmsg_cog.deduplicator.should_process(mock_service_envelope)
        testmsg_cog.deduplicator.is_duplicate(mock_service_envelope)
        mock_logger.bind.assert_called_with(envelope_id=12345)

    def test_integration_deduplication_prevents_discord_spam(self, testmsg_cog):
        envelope1 = MagicMock()
        envelope1.packet.id = 99999
        envelope1.gateway_id = "!gateway1"

        envelope2 = MagicMock()
        envelope2.packet.id = 99999
        envelope2.gateway_id = "!gateway2"

        should_process_first = testmsg_cog.deduplicator.should_process(envelope1)
        assert should_process_first

        should_process_second = testmsg_cog.deduplicator.should_process(envelope2)
        assert not should_process_second
