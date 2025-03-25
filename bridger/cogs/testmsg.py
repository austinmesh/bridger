import os
import traceback
from collections import deque
from datetime import datetime
from functools import partial

import aiomqtt
import pendulum
from discord import Embed, Message
from discord.ext import commands
from meshtastic import protocols
from meshtastic.protobuf.mesh_pb2 import RouteDiscovery, Routing
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.portnums_pb2 import ROUTING_APP, TRACEROUTE_APP

from bridger.__main__ import MQTT_BROKER, MQTT_PASS, MQTT_PORT, MQTT_USER
from bridger.crypto import CryptoEngine
from bridger.log import logger
from bridger.mqtt import MQTT_TOPIC, PBPacketProcessor

MQTT_TEST_CHANNEL_MESHTASTIC = os.getenv("MQTT_TEST_CHANNEL", "LongFast")
MQTT_TEST_CHANNEL_DISCORD = int(os.getenv("MQTT_TEST_CHANNEL_ID", 1253788609316913265))


class TestMsg(commands.GroupCog, name="testmsg"):
    def __init__(self, bot: commands.Bot, discord_channel_id: int):
        self.bot = bot
        self.discord_channel_id = discord_channel_id
        self.discord_channel = None

    @commands.Cog.listener(name="on_ready")
    async def on_ready(self):
        # We have to do this here because the bot can't find the channel when done in setup()
        self.discord_channel = self.bot.get_channel(self.discord_channel_id)
        logger.info(f"TestMsg cog is ready and channel is: {self.discord_channel}")

    @staticmethod
    def create_embed(service_envelope: ServiceEnvelope):
        gateway = service_envelope.gateway_id
        color = int(gateway[-6:], 16)
        snr = service_envelope.packet.rx_snr
        rssi = service_envelope.packet.rx_rssi
        unix_time = service_envelope.packet.rx_time

        formatted_time = datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M:%S")

        embed = Embed(color=color)
        embed.set_author(name=gateway)
        embed.add_field(name="SNR", value=snr, inline=True)
        embed.add_field(name="RSSI", value=rssi, inline=True)
        embed.add_field(name="Time", value=formatted_time, inline=True)
        return embed

    async def run_mqtt(self):
        topic = MQTT_TOPIC.removesuffix("/#")
        channel = MQTT_TEST_CHANNEL_MESHTASTIC
        full_topic = f"{topic}/{channel}/#"

        crypto = CryptoEngine()
        queue = deque(maxlen=100)

        async with aiomqtt.Client(MQTT_BROKER, MQTT_PORT, username=MQTT_USER, password=MQTT_PASS) as client:
            await client.subscribe(full_topic)
            logger.info(f"Subscribed to {full_topic}")
            await logger.complete()

            async for message in client.messages:
                service_envelope = ServiceEnvelope.FromString(message.payload)

                if service_envelope.packet.HasField("encrypted"):
                    PBPacketProcessor.process_encrypted_data(service_envelope, crypto)
                    app = ROUTING_APP

                    if service_envelope.packet.decoded.portnum == app:
                        packet_id = service_envelope.packet.id
                        # payload = RouteDiscovery.FromString(service_envelope.packet.decoded.payload)
                        # payload = Routing.FromString(service_envelope.packet.decoded.payload)
                        payload = protocols[app].protobufFactory.FromString(service_envelope.packet.decoded.payload)
                        source_node_id = getattr(service_envelope.packet, "from")

                        if any(item[0] == packet_id for item in queue):
                            message_id = next(item[1] for item in queue if item[0] == packet_id)
                            message = await self.discord_channel.fetch_message(message_id)
                            embeds = message.embeds
                            embeds.append(self.create_embed(service_envelope))
                            await message.edit(embeds=embeds)

                        else:
                            initial_embeds = [self.create_embed(service_envelope)]
                            content = f"Traceroute received from **{source_node_id}**:\n```\n{payload}\n```"  # noqa: E501
                            message: Message = await self.discord_channel.send(content, embeds=initial_embeds)
                            queue.append((service_envelope.packet.id, message.id))


def restart_mqtt_on_exception(task, bot: commands.Bot):
    try:
        # This raises the exception if the task failed
        task.result()
    except Exception as e:
        print(f"Task failed with exception: {e}. Restarting task...")
        traceback.print_exc()
        # Restart the task by creating a new task
        new_task = bot.loop.create_task(bot.cogs["testmsg"].run_mqtt())
        # Add the callback again to handle future exceptions
        new_task.add_done_callback(partial(restart_mqtt_on_exception, bot=bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(TestMsg(bot, MQTT_TEST_CHANNEL_DISCORD))
    run_mqtt_task = bot.loop.create_task(bot.cogs["testmsg"].run_mqtt())
    # Restart the task if it crashes
    run_mqtt_task.add_done_callback(partial(restart_mqtt_on_exception, bot=bot))
