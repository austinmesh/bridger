import os

from discord import Embed, Interaction, app_commands
from discord.ext import commands
from discord.utils import get

from bridger.gateway import GatewayError, GatewayManagerEMQX, emqx
from bridger.log import logger

BRIDGER_ADMIN_ROLE = os.getenv("BRIDGER_ADMIN_ROLE", "Bridger Admin")


def check_gateway_owner(interaction: Interaction) -> bool:
    node_id = None
    gateway_manager = GatewayManagerEMQX(emqx)

    logger.debug(f"Interaction data: {interaction.data}")

    if "options" in interaction.data:
        # Look through nested options
        for option in interaction.data["options"]:
            if "options" in option:
                for sub_option in option["options"]:
                    if sub_option["name"] == "node_id":
                        node_id = sub_option["value"]
                        break

    if not node_id:
        raise ValueError("node_id not found in the command options")

    logger.debug(f"Node ID: {node_id}")

    try:
        gateway = gateway_manager.get_gateway(node_id)
        owner = interaction.client.get_user(gateway.owner_id)
    except ValueError as e:
        raise app_commands.AppCommandError(f"Error retrieving gateway: {e}")

    logger.debug(f"Gateway owner: {owner}")
    logger.debug(f"Interaction user: {interaction.user}")

    compared = owner == interaction.user

    logger.debug(f"Owner and interaction user compared: {compared}")

    return owner == interaction.user


def is_bridger_admin_or_owner(interaction: Interaction):
    bridger_admin_role = get(interaction.guild.roles, name=BRIDGER_ADMIN_ROLE)
    if bridger_admin_role in interaction.user.roles or check_gateway_owner(interaction):
        return True
    return False


class MQTTCog(commands.GroupCog, name="bridger-mqtt"):
    delete_after = None

    def __init__(self, bot: commands.Bot, gateway_manager: GatewayManagerEMQX):
        self.bot = bot
        self.gateway_manager = gateway_manager

    async def cog_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        # Log the type of error and error message
        logger.debug(f"App command error: {type(error)}: {error}")

        if isinstance(error, app_commands.errors.CommandInvokeError):
            if isinstance(error.original, GatewayError):
                await interaction.response.send_message(
                    f"Gateway already exists: {error.original.gateway.node_hex_id}",
                    ephemeral=True,
                    delete_after=self.delete_after,
                )
            else:
                await interaction.response.send_message(
                    f"Command invoke error: {error.original}", ephemeral=True, delete_after=self.delete_after
                )
        elif isinstance(error, (app_commands.errors.MissingRole, app_commands.errors.CheckFailure)):
            await interaction.response.send_message(
                f"Check failure: {error}", ephemeral=True, delete_after=self.delete_after
            )
        elif isinstance(error, ValueError):
            await interaction.response.send_message(f"Value error: {error}", ephemeral=True, delete_after=self.delete_after)
        else:
            await interaction.response.send_message(
                f"Unknown error: {error}", ephemeral=True, delete_after=self.delete_after
            )

    @app_commands.command(name="request-account", description="Request a new MQTT account")
    @app_commands.describe(
        node_id="The hex node ID to request an account for. With or without the preceding ! such as !cbaf0421 or cbaf0421"
    )
    async def request_account(self, ctx: Interaction, node_id: str):
        gateway, password = self.gateway_manager.create_gateway_user(node_id, ctx.user)
        message = f"Gateway created: {gateway.node_hex_id} with password: {password}"

        await ctx.response.send_message(message, ephemeral=True)

    @app_commands.checks.has_role(BRIDGER_ADMIN_ROLE)
    @app_commands.command(name="delete-account", description="Delete MQTT account")
    async def delete_account(self, ctx: Interaction, node_id: str):
        if self.gateway_manager.delete_gateway_user(node_id, ctx.user):
            await ctx.response.send_message(f"Gateway deleted: {node_id}", ephemeral=True, delete_after=self.delete_after)
        else:
            await ctx.response.send_message(f"Gateway not found: {node_id}", ephemeral=True, delete_after=self.delete_after)

    @app_commands.checks.has_role(BRIDGER_ADMIN_ROLE)
    @app_commands.command(name="list-accounts", description="List all MQTT accounts")
    async def list_accounts(self, ctx: Interaction):
        gateways = self.gateway_manager.list_gateways()

        if not gateways:
            await ctx.response.send_message(content="There are no provisioned gateways in the system.", ephemeral=True)
            return

        embed = Embed(description="Currently provisioned gateways:", color=0x6CEB94)

        for gateway in gateways:
            owner = self.bot.get_user(gateway.owner_id)

            embed.add_field(
                name="Gateway",
                value=f"ID: **{gateway.node_hex_id}**\nOwner: **{owner.name}**",
                inline=True,
            )

        await ctx.response.send_message(
            content=f"There are {len(gateways)} provisioned gateways in the system.",
            embed=embed,
            ephemeral=True,
        )

    @app_commands.check(check_gateway_owner)
    @app_commands.command(name="reset-password", description="Reset MQTT account password")
    async def reset_password(self, ctx: Interaction, node_id: str):
        gateway, password = self.gateway_manager.reset_gateway_password(node_id, ctx.user)

        await ctx.response.send_message(
            f"Gateway password reset: {gateway.node_hex_id} with new password: {password}",
            ephemeral=True,
        )


async def setup(bot):
    gateway_manager = GatewayManagerEMQX(emqx)
    await bot.add_cog(MQTTCog(bot, gateway_manager))
