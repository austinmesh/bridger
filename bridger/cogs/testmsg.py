import asyncio
import random
import re
import time
from contextlib import suppress
from datetime import datetime
from functools import partial
from typing import Optional

import aiomqtt
from aiocache import SimpleMemoryCache
from discord import Embed, Message
from discord.ext import commands
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import TEXT_MESSAGE_APP

from bridger.cache import TTLCache
from bridger.config import (
    MQTT_BROKER,
    MQTT_CLIENT_ID,
    MQTT_HEALTHY_SECONDS,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_RESTART_MAX_DELAY,
    MQTT_RESTART_MIN_DELAY,
    MQTT_TEST_CHANNEL,
    MQTT_TEST_CHANNEL_ID,
    MQTT_TOPIC,
    MQTT_USER,
    NODE_INFO_CACHE_TTL,
    TEST_MESSAGE_MATCH_ALL,
)
from bridger.dataclasses import NodeData, TextMessagePoint
from bridger.deduplication import PacketDeduplicator
from bridger.influx.interfaces import InfluxReader
from bridger.log import logger
from bridger.mqtt import PBPacketProcessor
from bridger.utils import should_ignore_pki_message

DEFAULT_EMBED_COLOR = 0x5865F2  # Discord blurple, used when the gateway id will not parse
TEST_MESSAGE_MATCHERS = [
    re.compile(r"^.*$", flags=re.IGNORECASE) if TEST_MESSAGE_MATCH_ALL else None,
    re.compile(r"^\!\b.+$", flags=re.IGNORECASE),
]


class TestMsg(commands.GroupCog, name="testmsg"):
    __test__ = False  # Disable pytest discovery for this cog
    queue = SimpleMemoryCache()

    def __init__(self, bot: commands.Bot, discord_channel_id: int, influx_reader: InfluxReader):
        self.bot = bot
        self.discord_channel_id = discord_channel_id
        self.discord_channel = None
        self.influx_reader = influx_reader
        # The 1h TTL matches the embed-tracking queue below, so a packet re-heard while its
        # Discord message is still being updated is still recognised as a duplicate.
        self.deduplicator = PacketDeduplicator(maxlen=2000, use_gateway_id=True, ttl=3600)
        # Per instance rather than a class attribute, so it does not leak between tests.
        self.node_info_cache = TTLCache(NODE_INFO_CACHE_TTL, name="node-info")
        self._mqtt_task = None
        # Injectable so the supervisor's backoff can be tested without patching the shared
        # time module, which pytest and asyncio also rely on.
        self._clock = time.monotonic

    async def cog_load(self):
        self._mqtt_task = asyncio.create_task(self._mqtt_supervisor(), name="testmsg-mqtt")

    async def cog_unload(self):
        if self._mqtt_task:
            self._mqtt_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._mqtt_task

    @commands.Cog.listener(name="on_ready")
    async def on_ready(self):
        self.discord_channel = self.bot.get_channel(self.discord_channel_id)
        logger.info(f"TestMsg cog is ready and channel is: {self.discord_channel}")

    async def get_node_info(self, node_id: int) -> Optional[dict]:
        """Look up node info off the event loop, cached.

        This runs once per matched message inside the MQTT loop, and the underlying Flux query
        covers 6 hours, so it is both blocking and repetitive without the cache.
        """
        return await self.node_info_cache.get_or_load(str(node_id), partial(self.influx_reader.get_node_info, node_id))

    @staticmethod
    def format_node_name(node_id: int, node_info: Optional[dict] = None) -> str:
        """Format a consistent node name based on available info"""
        if not node_info:
            return f"**{node_id}**"

        short = node_info.get("short_name")
        long = node_info.get("long_name")

        if short and long:
            return f"**{short}** - {long}"
        else:
            return f"**{node_id}**"

    @staticmethod
    def parse_gateway_id(gateway_id: str) -> Optional[int]:
        try:
            return int((gateway_id or "").lstrip("!"), 16)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse gateway ID '{gateway_id}': {e}")
            return None

    async def build_embed(self, service_envelope: ServiceEnvelope) -> Embed:
        """Look up the gateway's node info, then render. The lookup is the only blocking part."""
        gateway_id = self.parse_gateway_id(service_envelope.gateway_id)
        node_info = None

        if gateway_id is not None:
            try:
                node_info = await self.get_node_info(gateway_id)
            except Exception:
                logger.exception(f"Failed to look up node info for gateway {service_envelope.gateway_id}")

        return self.create_embed(service_envelope, node_info)

    def create_embed(self, service_envelope: ServiceEnvelope, node_info: Optional[dict] = None):
        packet = service_envelope.packet
        gateway = service_envelope.gateway_id or ""
        snr = packet.rx_snr
        rssi = packet.rx_rssi
        hop_count = None
        hop_start = packet.hop_start
        formatted_time = datetime.fromtimestamp(packet.rx_time).strftime("%H:%M:%S")

        if packet.hop_start > 0:
            hop_count = packet.hop_start - packet.hop_limit

        # Degrades to a default rather than raising: this renders inside the MQTT loop, where
        # an exception drops the message.
        gateway_id = self.parse_gateway_id(gateway)

        if gateway_id is None:
            color = DEFAULT_EMBED_COLOR
            gateway_name = f"**{gateway or 'unknown'}**"
        else:
            color = gateway_id & 0xFFFFFF
            gateway_name = self.format_node_name(gateway_id, node_info)

        embed = Embed(color=color)
        embed.description = f"Heard by {gateway_name} - `{gateway}` at {formatted_time}"
        embed.add_field(name="SNR", value=snr, inline=True)
        embed.add_field(name="RSSI", value=rssi, inline=True)

        if hop_count == 0:
            embed.add_field(name="Hops", value=f"Direct/{hop_start}", inline=True)
        elif hop_count is not None:
            embed.add_field(name="Hops", value=f"{hop_count}/{hop_start}", inline=True)

        return embed

    async def update_message_embeds(self, message: Message, envelope: ServiceEnvelope):
        if len(message.embeds) >= 10:
            message_id = message.id
            logger.warning(f"Embed limit reached for message ID {message_id}, skipping update")
            return
        message.embeds.append(await self.build_embed(envelope))
        await message.edit(embeds=message.embeds)

    async def _mqtt_supervisor(self):
        """Keep run_mqtt alive for the lifetime of the cog.

        Restarts are unbounded on purpose: a broker outage should never permanently kill the
        bridge. Delay grows exponentially with full jitter and is capped, and the budget is
        reset only once a run has stayed up long enough to count as healthy.
        """
        await self.bot.wait_until_ready()

        if self.discord_channel is None:
            self.discord_channel = self.bot.get_channel(self.discord_channel_id)

        delay = MQTT_RESTART_MIN_DELAY

        while True:
            started = self._clock()

            try:
                await self.run_mqtt()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("MQTT loop failed")

            if self._clock() - started >= MQTT_HEALTHY_SECONDS:
                delay = MQTT_RESTART_MIN_DELAY

            sleep_for = min(delay, MQTT_RESTART_MAX_DELAY) * (0.5 + random.random())
            logger.info(f"Restarting MQTT loop in {sleep_for:.1f}s")
            await asyncio.sleep(sleep_for)
            delay = min(delay * 2, MQTT_RESTART_MAX_DELAY)

    async def run_mqtt(self):
        topic = MQTT_TOPIC.removesuffix("/#")
        channel = MQTT_TEST_CHANNEL
        full_topic = f"{topic}/{channel}/#"

        logger.info(f"Attempting to connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
        async with aiomqtt.Client(
            MQTT_BROKER,
            MQTT_PORT,
            username=MQTT_USER,
            password=MQTT_PASS,
            identifier=f"{MQTT_CLIENT_ID}-testmsg",
            clean_session=True,
        ) as client:
            reason_codes = await client.subscribe(full_topic)

            # A refused subscription otherwise looks exactly like a healthy one: connected,
            # and then no messages ever arrive.
            for reason_code in reason_codes or []:
                if getattr(reason_code, "is_failure", False):
                    raise aiomqtt.MqttError(f"Broker refused subscription to {full_topic}: {reason_code}")

            logger.info(f"Subscribed to {full_topic}")
            await logger.complete()

            async for mqtt_message in client.messages:
                # Ignoring PKI messages for now as we cannot decrypt them without storing keys somewhere
                if should_ignore_pki_message(str(mqtt_message.topic)):
                    logger.bind(topic=topic, channel=channel).debug(f"Ignoring PKI message on topic {mqtt_message.topic}")  # noqa: E501
                    continue

                try:
                    service_envelope = ServiceEnvelope.FromString(mqtt_message.payload)
                except Exception:
                    logger.exception("Failed to decode MQTT message")
                    continue

                if not self.deduplicator.should_process(service_envelope):
                    continue

                processor = PBPacketProcessor(service_envelope=service_envelope, strip_text=False)

                if processor.portnum == TEXT_MESSAGE_APP:
                    data: TextMessagePoint = processor.data
                    if not data or not data.text:
                        continue

                    if not any(pattern.match(data.text) for pattern in TEST_MESSAGE_MATCHERS if pattern):
                        continue

                    logger.debug(f"Test message matched: {data.text}")

                    packet = service_envelope.packet
                    packet_id = packet.id
                    source_node_id = getattr(packet, "from")
                    source_node = NodeData(node_id=source_node_id)
                    node_info = await self.get_node_info(source_node_id)

                    name = self.format_node_name(source_node_id, node_info)
                    message_id = await self.queue.get(packet_id)

                    extra = {
                        "packet_id": packet_id,
                        "source_node_id": source_node_id,
                        "source_node_hex_id": source_node.node_hex_id_with_bang,
                        "text": data.text,
                        "gateway": service_envelope.gateway_id,
                        "short_name": node_info.get("short_name") if node_info else None,
                        "long_name": node_info.get("long_name") if node_info else None,
                        "name": name,
                        "node_info": node_info,
                    }

                    logger.bind(**extra).debug(f"Message ID {message_id} for packet ID {packet_id} from {name}")

                    if message_id:
                        try:
                            message = await self.discord_channel.fetch_message(message_id)
                            await self.update_message_embeds(message, service_envelope)
                        except Exception:
                            logger.exception("Failed to fetch or edit Discord message")
                    else:
                        now_timestamp = int(datetime.now().timestamp())
                        content = f"Test message from {name} - `{source_node.node_hex_id_with_bang}` <t:{now_timestamp}:R>\n> {data.text}"  # noqa: E501

                        embeds = [await self.build_embed(service_envelope)]
                        try:
                            message: Message = await self.discord_channel.send(content, embeds=embeds)
                            await self.queue.set(packet_id, message.id, ttl=3600)
                        except Exception:
                            logger.exception("Failed to send Discord message")


async def setup(bot: commands.Bot):
    influx_reader = InfluxReader(influx_client=bot.influx_client)
    # cog_load starts the supervisor, and cog_unload cancels it.
    await bot.add_cog(TestMsg(bot, MQTT_TEST_CHANNEL_ID, influx_reader))
