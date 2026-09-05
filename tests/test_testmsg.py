import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiomqtt
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
        assert testmsg_cog.deduplicator.maxlen == 2000
        assert testmsg_cog.deduplicator.ttl == 3600

    def test_deduplicator_processes_unique_message(self, testmsg_cog, mock_service_envelope):
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope)
        assert ("!1a2b3c4d", 12345) in testmsg_cog.deduplicator.message_queue

    def test_deduplicator_processes_same_packet_different_gateway(
        self, testmsg_cog, mock_service_envelope, mock_service_envelope_duplicate
    ):
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope)
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope_duplicate)

    def test_deduplicator_processes_different_messages(
        self, testmsg_cog, mock_service_envelope, mock_service_envelope_different
    ):
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope)
        assert testmsg_cog.deduplicator.should_process(mock_service_envelope_different)
        assert ("!1a2b3c4d", 12345) in testmsg_cog.deduplicator.message_queue
        assert ("!1a2b3c4d", 67890) in testmsg_cog.deduplicator.message_queue

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
        testmsg_cog.deduplicator = PacketDeduplicator(maxlen=3, use_gateway_id=True)

        for i in range(3):
            envelope = MagicMock()
            envelope.packet.id = i
            envelope.gateway_id = "!test"
            testmsg_cog.deduplicator.mark_processed(envelope)

        assert len(testmsg_cog.deduplicator.message_queue) == 3
        assert ("!test", 0) in testmsg_cog.deduplicator.message_queue
        assert ("!test", 1) in testmsg_cog.deduplicator.message_queue
        assert ("!test", 2) in testmsg_cog.deduplicator.message_queue

        envelope = MagicMock()
        envelope.packet.id = 3
        envelope.gateway_id = "!test"
        testmsg_cog.deduplicator.mark_processed(envelope)

        assert len(testmsg_cog.deduplicator.message_queue) == 3
        assert ("!test", 0) not in testmsg_cog.deduplicator.message_queue
        assert ("!test", 1) in testmsg_cog.deduplicator.message_queue
        assert ("!test", 2) in testmsg_cog.deduplicator.message_queue
        assert ("!test", 3) in testmsg_cog.deduplicator.message_queue

    @patch("bridger.deduplication.logger")
    def test_deduplicator_logs_duplicate_detection(self, mock_logger, testmsg_cog, mock_service_envelope):
        testmsg_cog.deduplicator.should_process(mock_service_envelope)
        testmsg_cog.deduplicator.is_duplicate(mock_service_envelope)
        mock_logger.bind.assert_called_with(envelope_id=12345)

    def test_integration_deduplication_processes_different_gateways(self, testmsg_cog):
        envelope1 = MagicMock()
        envelope1.packet.id = 99999
        envelope1.gateway_id = "!gateway1"

        envelope2 = MagicMock()
        envelope2.packet.id = 99999
        envelope2.gateway_id = "!gateway2"

        should_process_first = testmsg_cog.deduplicator.should_process(envelope1)
        assert should_process_first

        should_process_second = testmsg_cog.deduplicator.should_process(envelope2)
        assert should_process_second

    def test_integration_deduplication_prevents_true_duplicates(self, testmsg_cog):
        envelope1 = MagicMock()
        envelope1.packet.id = 99999
        envelope1.gateway_id = "!gateway1"

        envelope2 = MagicMock()
        envelope2.packet.id = 99999
        envelope2.gateway_id = "!gateway1"

        should_process_first = testmsg_cog.deduplicator.should_process(envelope1)
        assert should_process_first

        should_process_second = testmsg_cog.deduplicator.should_process(envelope2)
        assert not should_process_second


class TestFormatNodeName:
    def test_format_node_name_no_node_info(self):
        result = TestMsg.format_node_name(123456789, None)
        assert result == "**123456789**"

    def test_format_node_name_empty_node_info(self):
        result = TestMsg.format_node_name(123456789, {})
        assert result == "**123456789**"

    def test_format_node_name_with_short_and_long(self):
        node_info = {"short_name": "ABC", "long_name": "Station ABC"}
        result = TestMsg.format_node_name(123456789, node_info)
        assert result == "**ABC** - Station ABC"

    def test_format_node_name_with_short_only(self):
        node_info = {"short_name": "ABC"}
        result = TestMsg.format_node_name(123456789, node_info)
        assert result == "**123456789**"

    def test_format_node_name_with_long_only(self):
        node_info = {"long_name": "Station ABC"}
        result = TestMsg.format_node_name(123456789, node_info)
        assert result == "**123456789**"

    def test_format_node_name_with_empty_strings(self):
        node_info = {"short_name": "", "long_name": ""}
        result = TestMsg.format_node_name(123456789, node_info)
        assert result == "**123456789**"

    def test_format_node_name_with_none_values(self):
        node_info = {"short_name": None, "long_name": None}
        result = TestMsg.format_node_name(123456789, node_info)
        assert result == "**123456789**"


def _embed_envelope(gateway_id, *, rx_time=1600000000, hop_start=3, hop_limit=2):
    envelope = MagicMock()
    envelope.gateway_id = gateway_id
    envelope.packet.rx_snr = 6.25
    envelope.packet.rx_rssi = -95
    envelope.packet.rx_time = rx_time
    envelope.packet.hop_start = hop_start
    envelope.packet.hop_limit = hop_limit
    return envelope


class TestCreateEmbed:
    def test_uses_node_info_and_derives_colour_from_gateway(self, testmsg_cog):
        node_info = {"short_name": "ABCD", "long_name": "A Node"}

        embed = testmsg_cog.create_embed(_embed_envelope("!1a2b3c4d"), node_info)

        assert embed.color.value == 0x2B3C4D
        assert "**ABCD** - A Node" in embed.description

    def test_unparseable_gateway_id_does_not_raise(self, testmsg_cog):
        # Previously this raised twice: once on int(gateway[-6:], 16) before the try block,
        # and again on the fallback, which retried the parse with the "!" still attached.
        embed = testmsg_cog.create_embed(_embed_envelope("!notahexvalue"))

        assert embed.color.value == 0x5865F2
        assert "notahexvalue" in embed.description

    def test_empty_gateway_id_does_not_raise(self, testmsg_cog):
        embed = testmsg_cog.create_embed(_embed_envelope(""))

        assert embed.color.value == 0x5865F2
        assert "unknown" in embed.description

    def test_renders_without_node_info(self, testmsg_cog):
        embed = testmsg_cog.create_embed(_embed_envelope("!1a2b3c4d"), None)

        assert embed.color.value == 0x2B3C4D
        assert "**439041101**" in embed.description  # falls back to the bare node id

    def test_hop_fields(self, testmsg_cog):
        direct = testmsg_cog.create_embed(_embed_envelope("!1a2b3c4d", hop_start=3, hop_limit=3))
        hopped = testmsg_cog.create_embed(_embed_envelope("!1a2b3c4d", hop_start=3, hop_limit=1))

        assert [f.value for f in direct.fields if f.name == "Hops"] == ["Direct/3"]
        assert [f.value for f in hopped.fields if f.name == "Hops"] == ["2/3"]


class TestBuildEmbed:
    async def test_looks_up_node_info_and_caches_it(self, testmsg_cog, mock_influx_reader):
        mock_influx_reader.get_node_info.return_value = {"short_name": "ABCD", "long_name": "A Node"}

        first = await testmsg_cog.build_embed(_embed_envelope("!1a2b3c4d"))
        second = await testmsg_cog.build_embed(_embed_envelope("!1a2b3c4d"))

        assert "**ABCD** - A Node" in first.description
        assert "**ABCD** - A Node" in second.description
        # The MQTT loop hits this per matched message, so it must not re-query every time.
        mock_influx_reader.get_node_info.assert_called_once_with(0x1A2B3C4D)

    async def test_skips_the_lookup_for_an_unparseable_gateway(self, testmsg_cog, mock_influx_reader):
        embed = await testmsg_cog.build_embed(_embed_envelope("!notahexvalue"))

        assert embed.color.value == 0x5865F2
        mock_influx_reader.get_node_info.assert_not_called()

    async def test_influx_failure_still_renders(self, testmsg_cog, mock_influx_reader):
        # A transient InfluxDB error must not propagate into the MQTT loop and drop the message.
        mock_influx_reader.get_node_info.side_effect = RuntimeError("influx down")

        embed = await testmsg_cog.build_embed(_embed_envelope("!1a2b3c4d"))

        assert embed.color.value == 0x2B3C4D
        assert "**439041101**" in embed.description

    async def test_caches_an_unknown_node(self, testmsg_cog, mock_influx_reader):
        # get_node_info returns None for unknown nodes; without the cache sentinel every
        # packet from an unknown node would re-run the query.
        mock_influx_reader.get_node_info.return_value = None

        await testmsg_cog.build_embed(_embed_envelope("!1a2b3c4d"))
        await testmsg_cog.build_embed(_embed_envelope("!1a2b3c4d"))

        mock_influx_reader.get_node_info.assert_called_once()

    async def test_lookup_runs_off_the_event_loop(self, testmsg_cog, mock_influx_reader):
        ran_on_loop = {}

        def get_node_info(node_id):
            try:
                ran_on_loop["value"] = asyncio.get_running_loop() is not None
            except RuntimeError:
                ran_on_loop["value"] = False
            return None

        mock_influx_reader.get_node_info.side_effect = get_node_info

        await testmsg_cog.build_embed(_embed_envelope("!1a2b3c4d"))

        assert ran_on_loop["value"] is False


class TestMqttSupervisor:
    @pytest.fixture
    def cog(self, testmsg_cog):
        testmsg_cog.bot.wait_until_ready = AsyncMock()
        testmsg_cog.bot.get_channel.return_value = MagicMock()
        return testmsg_cog

    async def test_restarts_after_a_failure_and_backs_off(self, cog, monkeypatch):
        sleeps = []
        monkeypatch.setattr("bridger.cogs.testmsg.asyncio.sleep", AsyncMock(side_effect=sleeps.append))
        monkeypatch.setattr("bridger.cogs.testmsg.random.random", lambda: 0.5)

        attempts = []

        async def run_mqtt():
            attempts.append(1)
            if len(attempts) >= 4:
                raise asyncio.CancelledError
            raise aiomqtt.MqttError("broker gone")

        monkeypatch.setattr(cog, "run_mqtt", run_mqtt)

        with pytest.raises(asyncio.CancelledError):
            await cog._mqtt_supervisor()

        # Unbounded restarts, with the delay doubling each time rather than hot-looping.
        assert len(attempts) == 4
        assert sleeps == [1.0, 2.0, 4.0]

    async def test_delay_is_capped(self, cog, monkeypatch):
        sleeps = []
        monkeypatch.setattr("bridger.cogs.testmsg.asyncio.sleep", AsyncMock(side_effect=sleeps.append))
        monkeypatch.setattr("bridger.cogs.testmsg.random.random", lambda: 0.5)
        monkeypatch.setattr("bridger.cogs.testmsg.MQTT_RESTART_MAX_DELAY", 4)

        attempts = []

        async def run_mqtt():
            attempts.append(1)
            if len(attempts) >= 6:
                raise asyncio.CancelledError
            raise aiomqtt.MqttError("broker gone")

        monkeypatch.setattr(cog, "run_mqtt", run_mqtt)

        with pytest.raises(asyncio.CancelledError):
            await cog._mqtt_supervisor()

        assert max(sleeps) <= 4

    async def test_a_healthy_run_resets_the_backoff(self, cog, monkeypatch):
        sleeps = []
        monkeypatch.setattr("bridger.cogs.testmsg.asyncio.sleep", AsyncMock(side_effect=sleeps.append))
        monkeypatch.setattr("bridger.cogs.testmsg.random.random", lambda: 0.5)

        # The clock is read twice per iteration (start, then the health check). The third run
        # lasts well past MQTT_HEALTHY_SECONDS; the first two are instant failures.
        ticks = iter([0, 1, 1, 2, 2, 100, 100])
        cog._clock = lambda: next(ticks)

        attempts = []

        async def run_mqtt():
            attempts.append(1)
            if len(attempts) >= 4:
                raise asyncio.CancelledError
            raise aiomqtt.MqttError("broker gone")

        monkeypatch.setattr(cog, "run_mqtt", run_mqtt)

        with pytest.raises(asyncio.CancelledError):
            await cog._mqtt_supervisor()

        # Third delay is back to the minimum because the second run stayed up long enough.
        assert sleeps == [1.0, 2.0, 1.0]

    async def test_cancellation_propagates(self, cog, monkeypatch):
        monkeypatch.setattr(cog, "run_mqtt", AsyncMock(side_effect=asyncio.CancelledError))

        with pytest.raises(asyncio.CancelledError):
            await cog._mqtt_supervisor()

    async def test_cog_unload_cancels_the_task(self, cog, monkeypatch):
        started = asyncio.Event()

        async def run_mqtt():
            started.set()
            await asyncio.sleep(3600)

        monkeypatch.setattr(cog, "run_mqtt", run_mqtt)

        await cog.cog_load()
        await asyncio.wait_for(started.wait(), timeout=1)
        await cog.cog_unload()

        assert cog._mqtt_task.cancelled()
