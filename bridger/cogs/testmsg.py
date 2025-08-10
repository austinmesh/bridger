import os
import re
from datetime import datetime
from functools import partial

import aiomqtt
from aiocache import SimpleMemoryCache
from discord import Embed, Message
from discord.ext import commands
from influxdb_client import InfluxDBClient
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import TEXT_MESSAGE_APP

from bridger.config import MQTT_BROKER, MQTT_PASS, MQTT_PORT, MQTT_TOPIC, MQTT_USER
from bridger.dataclasses import NodeData, TextMessagePoint
from bridger.deduplication import PacketDeduplicator
from bridger.influx.interfaces import InfluxReader
from bridger.log import logger
from bridger.mqtt import PBPacketProcessor

MQTT_TEST_CHANNEL_MESHTASTIC = os.getenv("MQTT_TEST_CHANNEL", "+")
MQTT_TEST_CHANNEL_DISCORD = int(os.getenv("MQTT_TEST_CHANNEL_ID", 1253788609316913265))
TEST_MESSAGE_MATCHERS = [
    re.compile(r"^.*$", flags=re.IGNORECASE) if os.getenv("TEST_MESSAGE_MATCH_ALL", "false").lower() == "true" else None,
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
        self.deduplicator = PacketDeduplicator(maxlen=100, use_gateway_id=True)

    @commands.Cog.listener(name="on_ready")
    async def on_ready(self):
        self.discord_channel = self.bot.get_channel(self.discord_channel_id)
        logger.info(f"TestMsg cog is ready and channel is: {self.discord_channel}")

    @staticmethod
    def format_node_name(node_id: int, node_info: dict = None) -> str:
        """Format a consistent node name based on available info"""
        if not node_info:
            return f"**{node_id}**"

        short = node_info.get("short_name")
        long = node_info.get("long_name")

        if short and long:
            return f"**{short}** - {long}"
        else:
            return f"**{node_id}**"

    def create_embed(self, service_envelope: ServiceEnvelope):
        packet = service_envelope.packet
        gateway = service_envelope.gateway_id
        color = int(gateway[-6:], 16)
        snr = packet.rx_snr
        rssi = packet.rx_rssi
        hop_count = None
        formatted_time = datetime.fromtimestamp(packet.rx_time).strftime("%H:%M:%S")

        if packet.hop_start > 0:
            hop_count = packet.hop_start - packet.hop_limit

        embed = Embed(color=color)
        # Try to get node info for the gateway hex ID
        try:
            gateway_id = int(gateway.strip("!"), 16)
            node_info = self.influx_reader.get_node_info(gateway_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to parse gateway ID '{gateway}': {e}")
            node_info = None

        gateway_name = self.format_node_name(gateway_id if "gateway_id" in locals() else gateway, node_info)
        embed.description = f"Heard by {gateway_name} - `{gateway}` at {formatted_time}"
        embed.add_field(name="SNR", value=snr, inline=True)
        embed.add_field(name="RSSI", value=rssi, inline=True)

        if hop_count == 0:
            embed.add_field(name="Hops", value="Direct", inline=True)
        elif hop_count is not None:
            embed.add_field(name="Hops", value=hop_count, inline=True)

        return embed

    async def update_message_embeds(self, message: Message, envelope: ServiceEnvelope):
        if len(message.embeds) >= 10:
            message_id = message.id
            logger.warning(f"Embed limit reached for message ID {message_id}, skipping update")
            return
        message.embeds.append(self.create_embed(envelope))
        await message.edit(embeds=message.embeds)

    async def run_mqtt(self):
        topic = MQTT_TOPIC.removesuffix("/#")
        channel = MQTT_TEST_CHANNEL_MESHTASTIC
        full_topic = f"{topic}/{channel}/#"

        async with aiomqtt.Client(
            MQTT_BROKER,
            MQTT_PORT,
            username=MQTT_USER,
            password=MQTT_PASS,
            clean_session=True,
        ) as client:
            await client.subscribe(full_topic)
            logger.info(f"Subscribed to {full_topic}")
            await logger.complete()

            async for message in client.messages:
                try:
                    service_envelope = ServiceEnvelope.FromString(message.payload)
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
                    node_info = self.influx_reader.get_node_info(source_node_id)

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

                        embeds = [self.create_embed(service_envelope)]
                        try:
                            message: Message = await self.discord_channel.send(content, embeds=embeds)
                            await self.queue.set(packet_id, message.id, ttl=3600)
                        except Exception:
                            logger.exception("Failed to send Discord message")


def restart_mqtt_on_exception(task, bot: commands.Bot):
    try:
        task.result()
    except Exception:
        logger.exception("MQTT task failed. Restarting...")
        new_task = bot.loop.create_task(bot.cogs["testmsg"].run_mqtt())
        new_task.add_done_callback(partial(restart_mqtt_on_exception, bot=bot))


async def setup(bot: commands.Bot):
    influx_client = InfluxDBClient.from_env_properties()
    influx_reader = InfluxReader(influx_client=influx_client)
    await bot.add_cog(TestMsg(bot, MQTT_TEST_CHANNEL_DISCORD, influx_reader))
    run_mqtt_task = bot.loop.create_task(bot.cogs["testmsg"].run_mqtt())
    run_mqtt_task.add_done_callback(partial(restart_mqtt_on_exception, bot=bot))
