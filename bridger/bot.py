import os

from aiohttp import ClientConnectorError
from discord import Intents
from discord.ext import commands

from bridger.influx import create_influx_client
from bridger.log import logger

try:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    DISCORD_BOT_OWNER_ID = int(os.getenv("DISCORD_BOT_OWNER_ID"))
except TypeError as e:
    logger.error(f"Failed to load environment variable {e}")
    exit(1)


class BridgerBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(command_prefix="./bridger ", **kwargs)

        self.influx_client = None
        self.initial_extensions = [
            "bridger.cogs.mqtt",
            "bridger.cogs.testmsg",
        ]

    async def setup_hook(self):
        self.influx_client = create_influx_client("bot")

        for ext in self.initial_extensions:
            await self.load_extension(ext)
            logger.info(f"Loaded extension: {ext}")


intents = Intents.default()
intents.message_content = True
intents.members = True

bot = BridgerBot(
    intents=intents,
    owner_id=DISCORD_BOT_OWNER_ID,
)


@commands.is_owner()
@bot.command(name="sync-commands", description="Sync the commands with the database")
async def sync_commands(ctx: commands.Context):
    try:
        await ctx.bot.tree.sync()
        await ctx.send("Commands synced to all guilds")
    except Exception as e:
        await ctx.send(f"Error syncing commands: {e}")


try:
    bot.run(DISCORD_BOT_TOKEN)
except ClientConnectorError as e:
    logger.error(f"Failed to connect to Discord {e}")
    exit(1)
