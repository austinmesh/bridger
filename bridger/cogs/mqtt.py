import os
import re
import time
from datetime import datetime, timezone
from typing import List, Literal, Optional

from discord import ButtonStyle, Embed, Interaction, app_commands, ui
from discord.ext import commands
from discord.utils import get
from influxdb_client import InfluxDBClient

from bridger.dataclasses import AnnotationPoint
from bridger.gateway import GatewayError, GatewayManagerEMQX, emqx
from bridger.influx.interfaces import InfluxReader, InfluxWriter
from bridger.log import logger

BRIDGER_ADMIN_ROLE = os.getenv("BRIDGER_ADMIN_ROLE", "Bridger Admin")

influx_client: InfluxDBClient = InfluxDBClient.from_env_properties()
query_client = influx_client.query_api()
influx_reader = InfluxReader(influx_client)


async def node_id_autocomplete(interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete function for node_id parameter."""
    try:
        logger.debug(f"Autocomplete called with current='{current}'")

        # Get all known node IDs with display names from InfluxDB
        nodes = influx_reader.get_all_node_ids()
        logger.debug(f"Found {len(nodes)} nodes from InfluxDB")

        # Filter based on what user has typed so far
        if current:
            # Remove leading ! if present for filtering
            current_clean = current.lstrip("!").lower()
            filtered_nodes = [
                node for node in nodes if (current_clean in node["value"].lower() or current_clean in node["name"].lower())
            ]
            logger.debug(f"Filtered to {len(filtered_nodes)} nodes matching '{current_clean}'")
        else:
            filtered_nodes = nodes[:25]  # Limit even when no filter
            logger.debug(f"No filter provided, showing first {len(filtered_nodes)} nodes")

        # Limit to 25 choices (Discord limit)
        choices = []
        for node in filtered_nodes[:25]:
            # Use the name for display and value for the actual parameter
            choices.append(app_commands.Choice(name=node["name"], value=node["value"]))

        logger.debug(f"Returning {len(choices)} choices for autocomplete")
        return choices
    except Exception as e:
        logger.error(f"Error in node_id autocomplete: {e}")
        # Return empty list on error rather than None to avoid Discord API errors
        return []


def check_gateway_owner(interaction: Interaction) -> bool:
    """Check if the user owns the gateway specified in the node_id parameter."""
    node_id = None

    logger.debug(f"Interaction data: {interaction.data}")

    # Extract node_id from interaction options
    if "options" in interaction.data:
        for option in interaction.data["options"]:
            if "options" in option:
                for sub_option in option["options"]:
                    if sub_option["name"] == "node_id":
                        node_id = sub_option["value"]
                        break
            # Also check direct options (not nested)
            elif option.get("name") == "node_id":
                node_id = option["value"]
                break

    if not node_id:
        logger.warning("node_id not found in command options")
        raise ValueError("node_id not found in the command options")

    # Normalize node_id (remove leading !)
    normalized_node_id = node_id.lstrip("!")
    logger.debug(f"Checking ownership for node ID: {normalized_node_id}")

    try:
        gateway_manager = GatewayManagerEMQX(emqx)
        gateway = gateway_manager.get_gateway(normalized_node_id)
        owner = interaction.client.get_user(gateway.owner_id)

        if not owner:
            logger.warning(f"Could not find owner user with ID {gateway.owner_id}")
            return False

        is_owner = owner == interaction.user
        logger.debug(f"User {interaction.user} is owner: {is_owner}")
        return is_owner

    except ValueError as e:
        logger.warning(f"Gateway not found for node {normalized_node_id}: {e}")
        # Don't raise here - let the calling command handle the error
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking gateway ownership: {e}")
        return False


def is_bridger_admin(interaction: Interaction) -> bool:
    """Check if user has the Bridger admin role."""
    bridger_admin_role = get(interaction.guild.roles, name=BRIDGER_ADMIN_ROLE)
    has_admin_role = bridger_admin_role and bridger_admin_role in interaction.user.roles
    logger.debug(f"User {interaction.user} has admin role: {has_admin_role}")
    return has_admin_role


def check_any_gateway_ownership(interaction: Interaction) -> bool:
    """Check if user owns any gateway."""
    try:
        gateway_manager = GatewayManagerEMQX(emqx)
        all_gateways = gateway_manager.list_gateways()
        user_owns_gateway = any(gateway.owner_id == interaction.user.id for gateway in all_gateways)
        logger.debug(f"User {interaction.user} owns any gateway: {user_owns_gateway}")
        return user_owns_gateway
    except Exception as e:
        logger.warning(f"Error checking if user owns any gateway: {e}")
        return False


def is_bridger_admin_or_owner(interaction: Interaction) -> bool:
    """Check if user is either a Bridger admin or owns the gateway in question."""
    # Check admin role first (more efficient)
    if is_bridger_admin(interaction):
        return True

    # If not admin, check if they own the specific gateway
    try:
        is_owner = check_gateway_owner(interaction)
        logger.debug(f"User {interaction.user} gateway ownership check: {is_owner}")
        return is_owner
    except Exception as e:
        logger.warning(f"Error checking gateway ownership: {e}")
        return False


def is_bridger_admin_or_gateway_owner(interaction: Interaction) -> bool:
    """Check if user is either a Bridger admin or owns any gateway."""
    # Check admin role first (more efficient)
    if is_bridger_admin(interaction):
        return True

    # If not admin, check if they own any gateway
    return check_any_gateway_ownership(interaction)


class GatewayPaginationView(ui.View):
    def __init__(self, gateways, bot, *, timeout=300):
        super().__init__(timeout=timeout)
        self.gateways = gateways
        self.bot = bot
        self.current_page = 0
        self.max_page = (len(gateways) - 1) // 25  # 25 fields per page

        self.update_buttons()

    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.max_page

    def get_page_embed(self):
        start_idx = self.current_page * 25
        end_idx = min(start_idx + 25, len(self.gateways))
        page_gateways = self.gateways[start_idx:end_idx]

        embed = Embed(description="Currently provisioned gateways:", color=0x6CEB94)

        for gateway in page_gateways:
            owner = self.bot.get_user(gateway.owner_id)
            owner_name = owner.name if owner else "Unknown"

            embed.add_field(
                name="Gateway",
                value=f"ID: **{gateway.node_hex_id}**\nOwner: **{owner_name}**\nUsername: **{gateway.user_string}**",
                inline=False,
            )

        embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_page + 1} • Total gateways: {len(self.gateways)}")

        return embed

    @ui.button(label="Previous", style=ButtonStyle.secondary, emoji="⬅️")
    async def previous_button(self, interaction: Interaction, button: ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Next", style=ButtonStyle.secondary, emoji="➡️")
    async def next_button(self, interaction: Interaction, button: ui.Button):
        if self.current_page < self.max_page:
            self.current_page += 1
            self.update_buttons()
            embed = self.get_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


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
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def request_account(self, ctx: Interaction, node_id: str):
        gateway, password = self.gateway_manager.create_gateway_user(node_id, ctx.user)
        message = f"Gateway created for node **{gateway.node_hex_id}**\n\nUsername: **{gateway.user_string}**\nPassword: **{password}**"  # noqa: E501

        await ctx.response.send_message(message, ephemeral=True)

    @app_commands.check(is_bridger_admin_or_owner)
    @app_commands.command(name="delete-account", description="Delete MQTT account")
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def delete_account(self, ctx: Interaction, node_id: str):
        if self.gateway_manager.delete_gateway_user(node_id):
            await ctx.response.send_message(f"Gateway deleted: {node_id}", ephemeral=True, delete_after=self.delete_after)
        else:
            await ctx.response.send_message(f"Gateway not found: {node_id}", ephemeral=True, delete_after=self.delete_after)

    @app_commands.check(is_bridger_admin_or_gateway_owner)
    @app_commands.command(name="list-accounts", description="List MQTT accounts (all if admin, your own if owner)")
    async def list_accounts(self, ctx: Interaction):
        # Check if user is a Bridger Admin
        is_admin = is_bridger_admin(ctx.user)

        # Get all gateways
        all_gateways = self.gateway_manager.list_gateways()

        if is_admin:
            # Admin sees all gateways
            gateways = all_gateways
            list_type = "gateways"
        else:
            # Regular user sees only their own gateways
            gateways = [gateway for gateway in all_gateways if gateway.owner_id == ctx.user.id]
            list_type = "of your own gateways"

        if not gateways:
            if is_admin:
                await ctx.response.send_message(content="There are no provisioned gateways in the system.", ephemeral=True)
            else:
                await ctx.response.send_message(content="You don't own any provisioned gateways.", ephemeral=True)
            return

        if len(gateways) <= 25:
            # Simple embed for 25 or fewer gateways
            embed = Embed(description=f"Currently provisioned gateways ({list_type}):", color=0x6CEB94)

            for gateway in gateways:
                owner = self.bot.get_user(gateway.owner_id)
                owner_name = owner.name if owner else "Unknown"

                embed.add_field(
                    name="Gateway",
                    value=f"ID: **{gateway.node_hex_id}**\nOwner: **{owner_name}**\nUsername: **{gateway.user_string}**",
                    inline=False,
                )

            await ctx.response.send_message(
                content=f"There are {len(gateways)} {list_type} in the system.",
                embed=embed,
                ephemeral=True,
            )
        else:
            # Use pagination for more than 25 gateways
            view = GatewayPaginationView(gateways, self.bot)
            embed = view.get_page_embed()

            await ctx.response.send_message(
                content=f"There are {len(gateways)} {list_type} in the system.",
                embed=embed,
                view=view,
                ephemeral=True,
            )

    @app_commands.check(check_gateway_owner)
    @app_commands.command(name="reset-password", description="Reset MQTT account password")
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def reset_password(self, ctx: Interaction, node_id: str):
        gateway, password = self.gateway_manager.reset_gateway_password(node_id, ctx.user)

        await ctx.response.send_message(
            f"Gateway **{gateway.node_hex_id}** password reset. The username is **{gateway.user_string}** with new password: `{password}`",  # noqa: E501
            ephemeral=True,
        )

    @app_commands.command(name="is-alive", description="Check if MQTT gateway is alive and receiving packets")
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def is_alive(self, ctx: Interaction, node_id: str):
        gateway = self.gateway_manager.get_gateway(node_id)
        tables = influx_reader.get_recent_packets(gateway.node_hex_id_with_bang)

        if not tables:
            await ctx.response.send_message(
                f"We haven't received any packets from **{gateway.node_hex_id}** in the last hour", ephemeral=True
            )
        else:
            records = tables[0].records
            record = max(records, key=lambda r: r.values.get("_time"))
            packet_time = int(record.values.get("_time").timestamp())

            await ctx.response.send_message(
                f"Gateway **{gateway.node_hex_id}** is alive. We have received **{len(records)}** packets in the last hour. The most recent was received at <t:{packet_time}> (<t:{packet_time}:R>)",  # noqa: E501
                ephemeral=True,
            )

    @app_commands.check(is_bridger_admin_or_owner)
    @app_commands.command(name="add-annotation", description="Add an annotation for Grafana")
    @app_commands.describe(
        node_id="The hex node ID to annotate. With or without the preceding ! such as !cbaf0421 or cbaf0421",
        annotation_type="The type of annotation",
        text="Description text for the annotation",
        global_annotation="Make this annotation global (admins only)",
        start_time="Start time (optional). Formats: Unix timestamp, ISO (2024-01-01T12:00:00Z), "
        "date (2024-01-01), or relative (+1h, +30m, +2d). Defaults to now.",
        end_time="End time (optional). Same formats as start_time. Leave empty for point-in-time annotation.",
    )
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def add_annotation(
        self,
        ctx: Interaction,
        node_id: str,
        annotation_type: Literal[
            "general_maintenance",
            "reposition",
            "configuration_change",
            "power_cycle",
            "antenna_adjustment",
            "firmware_update",
            "unresponsive_state",
        ],
        text: str,
        global_annotation: bool = False,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ):
        # Normalize node_id to hex format without !
        normalized_node_id = node_id.lstrip("!")

        # Parse time parameters
        parsed_start_time = None
        parsed_end_time = None

        if start_time:
            parsed_start_time = parse_time_string(start_time)
            if parsed_start_time is None:
                await ctx.response.send_message(
                    f"Invalid start_time format: '{start_time}'. "
                    "Use Unix timestamp, ISO format (2024-01-01T12:00:00Z), "
                    "date (2024-01-01), or relative (+1h, +30m, +2d).",
                    ephemeral=True,
                    delete_after=self.delete_after,
                )
                return

        if end_time:
            parsed_end_time = parse_time_string(end_time)
            if parsed_end_time is None:
                await ctx.response.send_message(
                    f"Invalid end_time format: '{end_time}'. "
                    "Use Unix timestamp, ISO format (2024-01-01T12:00:00Z), "
                    "date (2024-01-01), or relative (+1h, +30m, +2d).",
                    ephemeral=True,
                    delete_after=self.delete_after,
                )
                return

        # Validate that end_time is after start_time if both are provided
        if parsed_start_time and parsed_end_time and parsed_end_time <= parsed_start_time:
            await ctx.response.send_message(
                "End time must be after start time.", ephemeral=True, delete_after=self.delete_after
            )
            return

        # Check if user has permission for this specific node (for non-admins)
        bridger_admin_role = get(ctx.guild.roles, name=BRIDGER_ADMIN_ROLE)
        is_admin = bridger_admin_role and bridger_admin_role in ctx.user.roles

        # Validate global annotation permission
        if global_annotation and not is_admin:
            await ctx.response.send_message(
                "Only Bridger Admins can create global annotations.", ephemeral=True, delete_after=self.delete_after
            )
            return

        if not is_admin:
            # For non-admins, verify they own this specific node
            gateway_manager = GatewayManagerEMQX(emqx)
            try:
                gateway = gateway_manager.get_gateway(normalized_node_id)
                owner = ctx.client.get_user(gateway.owner_id)
                if owner != ctx.user:
                    await ctx.response.send_message(
                        "You can only add annotations for nodes you own.", ephemeral=True, delete_after=self.delete_after
                    )
                    return
            except ValueError:
                await ctx.response.send_message(
                    f"Node {normalized_node_id} not found or you don't have permission to annotate it.",
                    ephemeral=True,
                    delete_after=self.delete_after,
                )
                return

        # Create the annotation
        annotation = AnnotationPoint(
            node_id=normalized_node_id,
            annotation_type=annotation_type,
            body=text,
            author=ctx.user.display_name,
            global_annotation=global_annotation,
            start_time=parsed_start_time,  # Will default to now() in write_annotation if None
            end_time=parsed_end_time,
        )

        # Write to InfluxDB
        try:
            writer = InfluxWriter(influx_client)
            writer.write_annotation(annotation)

            # Build response message
            global_text = " (GLOBAL)" if global_annotation else ""
            response_msg = f"Annotation{global_text} added for node **{normalized_node_id}**:\n"
            response_msg += f"Type: **{annotation_type}**\n"
            response_msg += f"Text: {text}\n"

            # Add timing information
            if parsed_start_time:
                response_msg += f"Start: <t:{parsed_start_time}> (<t:{parsed_start_time}:R>)\n"
            else:
                response_msg += "Start: Now\n"

            if parsed_end_time:
                response_msg += f"End: <t:{parsed_end_time}> (<t:{parsed_end_time}:R>)"
            else:
                response_msg += "End: Not specified (point-in-time annotation)"

            await ctx.response.send_message(response_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to write annotation: {e}")
            await ctx.response.send_message(
                f"Failed to add annotation: {str(e)}", ephemeral=True, delete_after=self.delete_after
            )


def parse_time_string(time_str: str) -> Optional[int]:
    """Parse various time string formats to Unix timestamp.

    Supported formats:
    - Unix timestamp: 1640995200
    - ISO format: 2022-01-01T00:00:00Z or 2022-01-01T00:00:00
    - Date only: 2022-01-01 (assumes 00:00:00 UTC)
    - Relative: +1h, +30m, +2d (relative to now)
    """
    if not time_str:
        return None

    time_str = time_str.strip()

    try:
        # Try parsing as Unix timestamp
        if time_str.isdigit():
            return int(time_str)

        # Try parsing relative time (+1h, +30m, +2d, etc.)
        relative_match = re.match(r"^([+-]?)(\d+)([hdmw])$", time_str.lower())
        if relative_match:
            sign, amount, unit = relative_match.groups()
            amount = int(amount)
            if sign == "-":
                amount = -amount

            multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
            offset_seconds = amount * multipliers.get(unit, 0)
            return int(time.time()) + offset_seconds

        # Try parsing ISO format
        if "T" in time_str:
            if time_str.endswith("Z"):
                dt = datetime.fromisoformat(time_str[:-1] + "+00:00")
            elif "+" in time_str or time_str.count("-") > 2:
                dt = datetime.fromisoformat(time_str)
            else:
                # Assume UTC if no timezone
                dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())

        # Try parsing date only (YYYY-MM-DD)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", time_str):
            dt = datetime.fromisoformat(time_str + "T00:00:00").replace(tzinfo=timezone.utc)
            return int(dt.timestamp())

    except (ValueError, OverflowError) as e:
        logger.warning(f"Failed to parse time string '{time_str}': {e}")

    return None


async def setup(bot):
    gateway_manager = GatewayManagerEMQX(emqx)
    await bot.add_cog(MQTTCog(bot, gateway_manager))
