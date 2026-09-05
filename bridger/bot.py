import os
from typing import Optional

from aiohttp import ClientConnectorError
from discord import Intents
from discord.ext import commands

from bridger.influx import create_influx_client
from bridger.log import logger


def get_owner_id() -> Optional[int]:
    """Read DISCORD_BOT_OWNER_ID, tolerating it being unset or blank.

    .env.default ships this as an empty string, and int("") raises ValueError rather than the
    TypeError that unset produces, so the bot used to die on its own documented default.
    """
    raw = (os.getenv("DISCORD_BOT_OWNER_ID") or "").strip()

    if not raw:
        logger.warning("DISCORD_BOT_OWNER_ID is not set, owner-only commands will be unavailable")
        return None

    try:
        return int(raw)
    except ValueError:
        logger.error(f"DISCORD_BOT_OWNER_ID is not an integer: {raw!r}")
        return None


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


@commands.is_owner()
async def sync_commands(ctx: commands.Context):
    try:
        await ctx.bot.tree.sync()
        await ctx.send("Commands synced to all guilds")
    except Exception as e:
        await ctx.send(f"Error syncing commands: {e}")


def create_bot() -> BridgerBot:
    intents = Intents.default()
    intents.message_content = True
    intents.members = True

    bot = BridgerBot(intents=intents, owner_id=get_owner_id())
    bot.command(name="sync-commands", description="Sync the commands with the database")(sync_commands)

    return bot


def main() -> int:
    token = os.getenv("DISCORD_BOT_TOKEN")

    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set, cannot start the bot")
        return 1

    try:
        create_bot().run(token)
    except ClientConnectorError as e:
        logger.error(f"Failed to connect to Discord {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
