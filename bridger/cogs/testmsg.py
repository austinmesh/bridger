import os
import aiomqtt
from functools import partial

from discord.ext import commands
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
from meshtastic.protobuf.mesh_pb2 import Data
from meshtastic.protobuf.portnums_pb2 import TEXT_MESSAGE_APP
from google.protobuf.message import DecodeError

from bridger.__main__ import MQTT_USER, MQTT_PASS, MQTT_BROKER, MQTT_PORT
from bridger.mqtt import MQTT_TOPIC
from bridger.log import logger
from bridger.crypto import CryptoEngine

MQTT_TEST_CHANNEL_MESHTASTIC = os.getenv("MQTT_TEST_CHANNEL", "testing")
MQTT_TEST_CHANNEL_DISCORD = int(os.getenv("MQTT_TEST_CHANNEL_ID", 1253788609316913265))


class TestMsg(commands.GroupCog, name="testmsg"):
    delete_after = None

    def __init__(self, bot: commands.Bot, discord_channel=None):
        self.bot = bot
        self.discord_channel = discord_channel

    @commands.Cog.listener(name="on_ready")
    async def on_ready(self):
        self.discord_channel = self.bot.get_channel(MQTT_TEST_CHANNEL_DISCORD)
        logger.info(f"TestMsg cog is ready and channel is: {self.discord_channel}")

    async def run_mqtt(self):
        topic = MQTT_TOPIC.removesuffix("/#")
        channel = MQTT_TEST_CHANNEL_MESHTASTIC
        full_topic = f"{topic}/{channel}/#"

        crypto = CryptoEngine()

        async with aiomqtt.Client(MQTT_BROKER, MQTT_PORT, username=MQTT_USER, password=MQTT_PASS) as client:
            await client.subscribe(full_topic)
            logger.info(f"Subscribed to {full_topic}")
            await logger.complete()

            async for message in client.messages:
                service_envelope = ServiceEnvelope.FromString(message.payload)

                if service_envelope.packet.HasField("encrypted"):
                    decrypted_data = crypto.decrypt(
                        getattr(service_envelope.packet, "from"),
                        service_envelope.packet.id,
                        service_envelope.packet.encrypted
                    )

                    try:
                        data = Data()
                        data.ParseFromString(decrypted_data)
                        service_envelope.packet.decoded.CopyFrom(data)
                    except DecodeError as e:
                        logger.exception(f"Error decrypting message: {e}")

                    if service_envelope.packet.decoded.portnum == TEXT_MESSAGE_APP:
                        await self.discord_channel.send(service_envelope.packet.decoded.payload)


def restart_mqtt_on_exception(task, bot: commands.Bot):
    try:
        # This raises the exception if the task failed
        task.result()
    except Exception as e:
        print(f"Task failed with exception: {e}. Restarting task...")
        # Restart the task by creating a new task
        new_task = bot.loop.create_task(bot.cogs["testmsg"].run_mqtt())
        # Add the callback again to handle future exceptions
        new_task.add_done_callback(partial(restart_mqtt_on_exception, bot=bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(TestMsg(bot))
    run_mqtt_task = bot.loop.create_task(bot.cogs["testmsg"].run_mqtt())
    # Restart the task if it crashes
    run_mqtt_task.add_done_callback(partial(restart_mqtt_on_exception, bot=bot))
