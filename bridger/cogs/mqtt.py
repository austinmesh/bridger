import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Literal, Optional

from discord import ButtonStyle, Embed, Interaction, Member, app_commands, ui
from discord.ext import commands, tasks
from discord.utils import get

from bridger.cache import TTLCache
from bridger.config import (
    AUTOCOMPLETE_DEADLINE,
    BRIDGER_ADMIN_ROLE,
    GATEWAY_CACHE_TTL,
    NODE_CACHE_REFRESH_SECONDS,
    NODE_CACHE_TTL,
)
from bridger.dataclasses import AnnotationPoint
from bridger.gateway import (
    GatewayAlreadyExistsError,
    GatewayError,
    GatewayManagerEMQX,
    GatewayValidationError,
    emqx,
)
from bridger.influx.interfaces import InfluxReader, InfluxWriter
from bridger.log import logger

# The node list TTL is deliberately twice the refresh interval, so one failed background
# refresh never empties the cache and drops users back onto the blocking path.
NODE_CACHE_KEY = "all"
GATEWAY_CACHE_KEY = "all"

node_cache = TTLCache(NODE_CACHE_TTL, name="node-ids")
gateway_cache = TTLCache(GATEWAY_CACHE_TTL, name="gateways")


async def node_id_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for the node_id parameter.

    Fires per keystroke against Discord's ~3s deadline, so the 30-day Flux query behind it is
    cached and run on a worker thread, and we give up early rather than let the interaction
    time out with nothing.
    """
    try:
        influx_reader = InfluxReader(interaction.client.influx_client)
        nodes = await asyncio.wait_for(
            node_cache.get_or_load(NODE_CACHE_KEY, influx_reader.get_all_node_ids),
            timeout=AUTOCOMPLETE_DEADLINE,
        )
    except TimeoutError:
        logger.warning("Autocomplete timed out waiting for the node list")
        return []
    except Exception as e:
        logger.error(f"Error in node_id autocomplete: {e}")
        # An empty list rather than None, which the Discord API rejects.
        return []

    if current:
        needle = current.lstrip("!").lower()
        nodes = [node for node in nodes if needle in node["value"].lower() or needle in (node["name"] or "").lower()]

    # Discord rejects a choice with no name, and the query can yield one when a node has
    # never reported a short or long name.
    return [app_commands.Choice(name=node["name"] or node["value"], value=node["value"]) for node in nodes[:25]]


def extract_node_id(interaction: Interaction) -> Optional[str]:
    """Pull the node_id argument out of an interaction.

    discord.py fills in interaction.namespace before checks run, so prefer that and fall back
    to walking the raw payload.
    """
    node_id = getattr(interaction.namespace, "node_id", None)
    if node_id:
        return str(node_id)

    for option in (interaction.data or {}).get("options", []):
        if option.get("name") == "node_id":
            return str(option["value"])

        for sub_option in option.get("options", []):
            if sub_option.get("name") == "node_id":
                return str(sub_option["value"])

    return None


async def list_gateways_cached(gateway_manager: GatewayManagerEMQX):
    return await gateway_cache.get_or_load(GATEWAY_CACHE_KEY, gateway_manager.list_gateways)


async def check_gateway_owner(interaction: Interaction) -> bool:
    """Check whether the caller owns the gateway named in the node_id parameter."""
    node_id = extract_node_id(interaction)

    if not node_id:
        # Returning False rather than raising: a non-AppCommandError raised from a check
        # escapes the command tree as an unhandled task, and the user just sees
        # "the application did not respond".
        logger.warning("node_id not found in command options")
        return False

    normalized_node_id = node_id.lstrip("!")

    try:
        gateways = await list_gateways_cached(GatewayManagerEMQX(emqx))
        node_id_int = int(normalized_node_id, 16)
    except ValueError:
        logger.warning(f"Not a valid node ID: {normalized_node_id}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking gateway ownership: {e}")
        return False

    for gateway in gateways:
        if gateway.node_id == node_id_int:
            # Compare ids directly. get_user() is cache-only and returns None for a user who
            # is not in the local cache, which denied legitimate owners.
            return gateway.owner_id == interaction.user.id

    logger.warning(f"Gateway not found for node {normalized_node_id}")
    return False


def is_bridger_admin(interaction: Interaction) -> bool:
    """Check whether the caller holds the Bridger admin role."""
    # guild is None in DMs, and roles only exists on Member, not User.
    if interaction.guild is None or not isinstance(interaction.user, Member):
        return False

    role = get(interaction.guild.roles, name=BRIDGER_ADMIN_ROLE)
    return role is not None and role in interaction.user.roles


async def check_any_gateway_ownership(interaction: Interaction) -> bool:
    """Check whether the caller owns any gateway at all."""
    try:
        gateways = await list_gateways_cached(GatewayManagerEMQX(emqx))
    except Exception as e:
        logger.warning(f"Error checking if user owns any gateway: {e}")
        return False

    return any(gateway.owner_id == interaction.user.id for gateway in gateways)


async def is_bridger_admin_or_owner(interaction: Interaction) -> bool:
    """Admin, or the owner of the gateway in question."""
    return is_bridger_admin(interaction) or await check_gateway_owner(interaction)


async def is_bridger_admin_or_gateway_owner(interaction: Interaction) -> bool:
    """Admin, or the owner of any gateway."""
    return is_bridger_admin(interaction) or await check_any_gateway_ownership(interaction)


def format_owner(bot, owner_id: int) -> str:
    """Render a gateway owner for display.

    Deliberately cache-only: list_accounts renders up to 25 gateways per page, so fetch_user
    would be 25 REST calls inside a 3s window. A mention resolves client-side for free when
    the user is not cached.
    """
    owner = bot.get_user(owner_id)
    return owner.name if owner else f"<@{owner_id}>"


class GatewayPaginationView(ui.View):
    def __init__(self, gateways, bot, *, timeout=300):
        super().__init__(timeout=timeout)
        self.gateways = gateways
        self.bot = bot
        self.current_page = 0
        self.max_page = max(0, (len(gateways) - 1) // 25)  # 25 fields per page

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
            owner_name = format_owner(self.bot, gateway.owner_id)

            embed.add_field(
                name="Gateway",
                value=(
                    f"ID: **{gateway.node_hex_id_without_bang}**\n"
                    f"Owner: **{owner_name}**\n"
                    f"Username: **{gateway.user_string}**"
                ),
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


@app_commands.guild_only()
class MQTTCog(commands.GroupCog, name="bridger-mqtt"):
    delete_after = None

    def __init__(self, bot: commands.Bot, gateway_manager: GatewayManagerEMQX, influx_reader: InfluxReader):
        self.bot = bot
        self.gateway_manager = gateway_manager
        self.influx_reader = influx_reader

    async def cog_load(self):
        self.refresh_caches.start()

    async def cog_unload(self):
        self.refresh_caches.cancel()

    @tasks.loop(seconds=NODE_CACHE_REFRESH_SECONDS)
    async def refresh_caches(self):
        """Keep the caches warm.

        Checks run before a command body and cannot defer, so the gateway list has to be a
        cache hit or it eats the interaction's 3s budget.
        """
        try:
            await node_cache.refresh(NODE_CACHE_KEY, self.influx_reader.get_all_node_ids)
            await gateway_cache.refresh(GATEWAY_CACHE_KEY, self.gateway_manager.list_gateways)
        except Exception:
            logger.exception("Cache refresh failed, serving stale entries")

    @refresh_caches.before_loop
    async def _before_refresh_caches(self):
        await self.bot.wait_until_ready()

    async def reply(self, interaction: Interaction, content: str, **kwargs):
        """Reply to an interaction whether or not it has already been deferred.

        Note delete_after is not a Webhook.send parameter, so it is dropped on the followup
        path rather than raising.
        """
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True, **kwargs)
        else:
            await interaction.response.send_message(content, ephemeral=True, delete_after=self.delete_after, **kwargs)

    @staticmethod
    def _describe_gateway_error(error: GatewayError) -> str:
        node_id = error.gateway.node_hex_id_without_bang

        if isinstance(error, GatewayAlreadyExistsError):
            return f"Gateway already exists: {node_id}"

        if isinstance(error, GatewayValidationError):
            return f"Invalid gateway request for {node_id}. Check the node ID and try again."

        # Deliberately no exception text here: the string requests builds for an HTTPError
        # carries the EMQX URL and API path, and this message goes to a Discord user. The
        # detail is logged in cog_app_command_error instead.
        status = f" (HTTP {error.status_code})" if error.status_code else ""
        return f"Gateway backend error for {node_id}{status}. Please try again later or contact an admin."

    async def cog_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        logger.debug(f"App command error: {type(error)}: {error}")

        if isinstance(error, app_commands.errors.CommandInvokeError):
            if isinstance(error.original, GatewayError):
                logger.opt(exception=error.original).warning(
                    f"Gateway command failed for node {error.original.gateway.node_hex_id_without_bang}"
                )
                message = self._describe_gateway_error(error.original)
            else:
                logger.opt(exception=error.original).warning("Command invoke error")
                message = f"Command invoke error: {error.original}"
        elif isinstance(error, (app_commands.errors.MissingRole, app_commands.errors.CheckFailure)):
            message = f"Check failure: {error}"
        else:
            message = f"Unknown error: {error}"

        await self.reply(interaction, message)

    @app_commands.command(name="request-account", description="Request a new MQTT account")
    @app_commands.describe(
        node_id="The hex node ID to request an account for. With or without the preceding ! such as !cbaf0421 or cbaf0421"
    )
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def request_account(self, ctx: Interaction, node_id: str):
        await ctx.response.defer(ephemeral=True)

        gateway, password = await asyncio.to_thread(self.gateway_manager.create_gateway_user, node_id, ctx.user)
        await gateway_cache.invalidate()

        logger.bind(actor=ctx.user.id, node_id=gateway.node_hex_id_without_bang).info("Gateway account created")

        await self.reply(
            ctx,
            f"Gateway created for node **{gateway.node_hex_id_without_bang}**\n\n"
            f"Username: **{gateway.user_string}**\nPassword: **{password}**",
        )

    @app_commands.check(is_bridger_admin_or_owner)
    @app_commands.command(name="delete-account", description="Delete MQTT account")
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def delete_account(self, ctx: Interaction, node_id: str):
        await ctx.response.defer(ephemeral=True)

        deleted = await asyncio.to_thread(self.gateway_manager.delete_gateway_user, node_id)
        await gateway_cache.invalidate()

        if deleted:
            logger.bind(actor=ctx.user.id, node_id=node_id).info("Gateway account deleted")
            await self.reply(ctx, f"Gateway deleted: {node_id}")
        else:
            await self.reply(ctx, f"Gateway not found: {node_id}")

    @app_commands.check(is_bridger_admin_or_gateway_owner)
    @app_commands.command(name="list-accounts", description="List MQTT accounts (all if admin, your own if owner)")
    async def list_accounts(self, ctx: Interaction):
        await ctx.response.defer(ephemeral=True)

        is_admin = is_bridger_admin(ctx)
        all_gateways = await list_gateways_cached(self.gateway_manager)

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
                await self.reply(ctx, "There are no provisioned gateways in the system.")
            else:
                await self.reply(ctx, "You don't own any provisioned gateways.")
            return

        if len(gateways) <= 25:
            # Simple embed for 25 or fewer gateways
            embed = Embed(description=f"Currently provisioned gateways ({list_type}):", color=0x6CEB94)

            for gateway in gateways:
                owner_name = format_owner(self.bot, gateway.owner_id)

                embed.add_field(
                    name="Gateway",
                    value=(
                        f"ID: **{gateway.node_hex_id_without_bang}**\n"
                        f"Owner: **{owner_name}**\n"
                        f"Username: **{gateway.user_string}**"
                    ),
                    inline=False,
                )

            await self.reply(ctx, f"There are {len(gateways)} {list_type} in the system.", embed=embed)
        else:
            # Use pagination for more than 25 gateways
            view = GatewayPaginationView(gateways, self.bot)
            embed = view.get_page_embed()

            await self.reply(ctx, f"There are {len(gateways)} {list_type} in the system.", embed=embed, view=view)

    @app_commands.check(check_gateway_owner)
    @app_commands.command(name="reset-password", description="Reset MQTT account password")
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def reset_password(self, ctx: Interaction, node_id: str):
        await ctx.response.defer(ephemeral=True)

        gateway, password = await asyncio.to_thread(self.gateway_manager.reset_gateway_password, node_id)

        logger.bind(actor=ctx.user.id, node_id=gateway.node_hex_id_without_bang).info("Gateway password reset")

        await self.reply(
            ctx,
            f"Gateway **{gateway.node_hex_id_without_bang}** password reset. "
            f"The username is **{gateway.user_string}** with new password: `{password}`",
        )

    @app_commands.command(name="is-alive", description="Check if MQTT gateway is alive and receiving packets")
    @app_commands.autocomplete(node_id=node_id_autocomplete)
    async def is_alive(self, ctx: Interaction, node_id: str):
        await ctx.response.defer(ephemeral=True)

        gateway = await asyncio.to_thread(self.gateway_manager.get_gateway, node_id)
        tables = await asyncio.to_thread(self.influx_reader.get_recent_packets, gateway.node_hex_id_with_bang)

        if not tables:
            await self.reply(
                ctx,
                f"We haven't received any packets from **{gateway.node_hex_id_without_bang}** in the last hour",
            )
        else:
            records = tables[0].records
            record = max(records, key=lambda r: r.values.get("_time"))
            packet_time = int(record.values.get("_time").timestamp())

            await self.reply(
                ctx,
                f"Gateway **{gateway.node_hex_id_without_bang}** is alive. "
                f"We have received **{len(records)}** packets in the last hour. "
                f"The most recent was received at <t:{packet_time}> (<t:{packet_time}:R>)",
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
        await ctx.response.defer(ephemeral=True)

        normalized_node_id = node_id.lstrip("!")

        # Parse time parameters
        parsed_start_time = None
        parsed_end_time = None

        if start_time:
            parsed_start_time = parse_time_string(start_time)
            if parsed_start_time is None:
                await self.reply(
                    ctx,
                    f"Invalid start_time format: '{start_time}'. "
                    "Use Unix timestamp, ISO format (2024-01-01T12:00:00Z), "
                    "date (2024-01-01), or relative (+1h, +30m, +2d).",
                )
                return

        if end_time:
            parsed_end_time = parse_time_string(end_time)
            if parsed_end_time is None:
                await self.reply(
                    ctx,
                    f"Invalid end_time format: '{end_time}'. "
                    "Use Unix timestamp, ISO format (2024-01-01T12:00:00Z), "
                    "date (2024-01-01), or relative (+1h, +30m, +2d).",
                )
                return

        # Validate that end_time is after start_time if both are provided
        if parsed_start_time and parsed_end_time and parsed_end_time <= parsed_start_time:
            await self.reply(ctx, "End time must be after start time.")
            return

        # Check if user has permission for this specific node (for non-admins)
        is_admin = is_bridger_admin(ctx)

        # Validate global annotation permission
        if global_annotation and not is_admin:
            await self.reply(ctx, "Only Bridger Admins can create global annotations.")
            return

        if not is_admin:
            # For non-admins, verify they own this specific node
            gateway_manager = GatewayManagerEMQX(emqx)
            try:
                gateway = await asyncio.to_thread(gateway_manager.get_gateway, normalized_node_id)
                if gateway.owner_id != ctx.user.id:
                    await self.reply(ctx, "You can only add annotations for nodes you own.")
                    return
            except ValueError:
                await self.reply(
                    ctx,
                    f"Node {normalized_node_id} not found or you don't have permission to annotate it.",
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
            writer = InfluxWriter(self.bot.influx_client)
            await asyncio.to_thread(writer.write_annotation, annotation)

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

            await self.reply(ctx, response_msg)
        except Exception as e:
            logger.error(f"Failed to write annotation: {e}")
            await self.reply(ctx, f"Failed to add annotation: {e}")

    @app_commands.check(is_bridger_admin)
    @app_commands.command(
        name="update-all-gateway-rules",
        description="Update MQTT rules for all gateways to support wildcard channels",
    )
    async def update_all_gateway_rules(self, ctx: Interaction):
        await ctx.response.defer(ephemeral=True)

        try:
            all_gateways = await list_gateways_cached(self.gateway_manager)
        except Exception as e:
            logger.error(f"Failed to list gateways: {e}")
            await self.reply(ctx, f"Failed to list gateways: {e}")
            return

        if not all_gateways:
            await self.reply(ctx, "No gateways found to update.")
            return

        total_gateways = len(all_gateways)
        successful_updates = 0
        failed_updates = []

        for gateway in all_gateways:
            try:
                success = await asyncio.to_thread(
                    self.gateway_manager.update_gateway_user_rules, gateway.node_hex_id_without_bang
                )
                if success:
                    successful_updates += 1
                    logger.info(f"Successfully updated rules for gateway {gateway.node_hex_id_without_bang}")
                else:
                    failed_updates.append(gateway.node_hex_id_without_bang)
                    logger.warning(f"Failed to update rules for gateway {gateway.node_hex_id_without_bang}")
            except Exception as e:
                failed_updates.append(gateway.node_hex_id_without_bang)
                logger.error(f"Exception updating rules for gateway {gateway.node_hex_id_without_bang}: {e}")

        response = "Gateway rules update completed!\n\n"
        response += f"**Total gateways:** {total_gateways}\n"
        response += f"**Successful updates:** {successful_updates}\n"
        response += f"**Failed updates:** {len(failed_updates)}\n"

        if failed_updates:
            response += "\n**Failed gateway IDs:**\n"
            for failed_gateway in failed_updates[:10]:  # Limit to first 10 to avoid message length issues
                response += f"• {failed_gateway}\n"
            if len(failed_updates) > 10:
                response += f"• ... and {len(failed_updates) - 10} more\n"

        if successful_updates == total_gateways:
            response += "\nAll gateway rules have been successfully updated to support wildcard channel subscriptions!"
        elif successful_updates > 0:
            response += "\nPartial success. Check logs for details on failed updates."
        else:
            response += "\nNo gateway rules were successfully updated. Check logs for errors."

        await gateway_cache.invalidate()
        await self.reply(ctx, response)


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
                dt = datetime.fromisoformat(time_str).replace(tzinfo=UTC)
            return int(dt.timestamp())

        # Try parsing date only (YYYY-MM-DD)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", time_str):
            dt = datetime.fromisoformat(time_str + "T00:00:00").replace(tzinfo=UTC)
            return int(dt.timestamp())

    except (ValueError, OverflowError) as e:
        logger.warning(f"Failed to parse time string '{time_str}': {e}")

    return None


async def setup(bot):
    gateway_manager = GatewayManagerEMQX(emqx)
    influx_reader = InfluxReader(influx_client=bot.influx_client)
    await bot.add_cog(MQTTCog(bot, gateway_manager, influx_reader))
