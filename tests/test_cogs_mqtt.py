import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord import Interaction, Member, Role, User

from bridger.cogs import mqtt as mqtt_cog
from bridger.cogs.mqtt import (
    GatewayPaginationView,
    MQTTCog,
    check_any_gateway_ownership,
    check_gateway_owner,
    extract_node_id,
    format_owner,
    is_bridger_admin,
    node_id_autocomplete,
)
from bridger.gateway import (
    GatewayAlreadyExistsError,
    GatewayBackendError,
    GatewayData,
    GatewayValidationError,
)

ADMIN_ROLE = "Bridger Admin"

# The string requests builds for an HTTPError embeds the full request URL.
EMQX_URL = "http://emqx.internal:18083/api/v5/authentication/password_based:built_in_database/users"
RAW_HTTP_ERROR = f"500 Server Error: Internal Server Error for url: {EMQX_URL}"


def _gateway():
    return GatewayData(node_id=int("1a2b3c4d", 16), owner_id=1234567890)


def make_role(name):
    role = MagicMock(spec=Role)
    # Must be assigned after construction: MagicMock(name=...) sets the mock's repr name.
    role.name = name
    return role


def make_interaction(*, user_id=1, guild=True, guild_roles=(), user_roles=(), member=True, node_id=None, responded=False):
    """Build a stand-in Interaction.

    discord.Interaction cannot be constructed without a full gateway payload, and the checks
    use isinstance(user, Member), so the user mock has to be spec'd.
    """
    user = MagicMock(spec=Member if member else User)
    user.id = user_id
    user.roles = list(user_roles)

    interaction = MagicMock(spec=Interaction)
    interaction.user = user
    interaction.guild = MagicMock(roles=list(guild_roles)) if guild else None
    interaction.namespace = SimpleNamespace(node_id=node_id)
    interaction.data = {}
    interaction.client = MagicMock()
    interaction.response.is_done.return_value = responded

    return interaction


@pytest.fixture(autouse=True)
async def clear_caches():
    # Module-level caches are shared across tests; TTL uses loop.call_later so this must be async.
    await mqtt_cog.node_cache.invalidate()
    await mqtt_cog.gateway_cache.invalidate()
    yield
    await mqtt_cog.node_cache.invalidate()
    await mqtt_cog.gateway_cache.invalidate()


@pytest.fixture
def admin_role():
    # BRIDGER_ADMIN_ROLE is read at import, so the module attribute is what must be patched.
    with patch("bridger.cogs.mqtt.BRIDGER_ADMIN_ROLE", ADMIN_ROLE):
        yield ADMIN_ROLE


class TestIsBridgerAdmin:
    def test_true_when_the_member_holds_the_role(self, admin_role):
        role = make_role(ADMIN_ROLE)
        interaction = make_interaction(guild_roles=[role], user_roles=[role])

        assert is_bridger_admin(interaction) is True

    def test_false_when_the_role_exists_but_the_member_lacks_it(self, admin_role):
        interaction = make_interaction(guild_roles=[make_role(ADMIN_ROLE)], user_roles=[])

        assert is_bridger_admin(interaction) is False

    def test_false_when_the_guild_has_no_such_role(self, admin_role):
        interaction = make_interaction(guild_roles=[make_role("Some Other Role")])

        assert is_bridger_admin(interaction) is False

    def test_false_in_a_dm_instead_of_raising(self, admin_role):
        # interaction.guild is None in a DM; this used to raise AttributeError.
        assert is_bridger_admin(make_interaction(guild=False)) is False

    def test_false_for_a_plain_user(self, admin_role):
        # A User has no .roles at all, only a Member does.
        assert is_bridger_admin(make_interaction(member=False)) is False


class TestExtractNodeId:
    def test_reads_the_namespace(self):
        assert extract_node_id(make_interaction(node_id="!cbaf0421")) == "!cbaf0421"

    def test_falls_back_to_flat_raw_options(self):
        interaction = make_interaction()
        interaction.data = {"options": [{"name": "node_id", "value": "cbaf0421"}]}

        assert extract_node_id(interaction) == "cbaf0421"

    def test_falls_back_to_nested_raw_options(self):
        interaction = make_interaction()
        interaction.data = {"options": [{"name": "sub", "options": [{"name": "node_id", "value": "cbaf0421"}]}]}

        assert extract_node_id(interaction) == "cbaf0421"

    def test_none_when_absent(self):
        assert extract_node_id(make_interaction()) is None


class TestCheckGatewayOwner:
    @pytest.fixture
    def manager(self):
        with patch("bridger.cogs.mqtt.GatewayManagerEMQX") as cls:
            cls.return_value.list_gateways.return_value = [GatewayData(node_id=0xCBAF0421, owner_id=42)]
            yield cls.return_value

    async def test_true_for_the_owner_even_when_discord_has_not_cached_them(self, manager):
        # The regression: ownership used to be decided by comparing get_user() to the caller,
        # and get_user is cache-only, so an uncached owner was denied their own gateway.
        interaction = make_interaction(user_id=42, node_id="!cbaf0421")
        interaction.client.get_user.return_value = None

        assert await check_gateway_owner(interaction) is True

    async def test_false_for_a_non_owner(self, manager):
        assert await check_gateway_owner(make_interaction(user_id=99, node_id="cbaf0421")) is False

    async def test_false_when_the_gateway_is_unknown(self, manager):
        assert await check_gateway_owner(make_interaction(user_id=42, node_id="deadbeef")) is False

    async def test_false_without_a_node_id_instead_of_raising(self, manager):
        # Raising a bare ValueError from a check escapes the command tree as an unhandled
        # task, and the user only sees "the application did not respond".
        assert await check_gateway_owner(make_interaction(user_id=42)) is False

    async def test_false_for_an_unparseable_node_id(self, manager):
        assert await check_gateway_owner(make_interaction(user_id=42, node_id="nothex!!")) is False

    async def test_false_when_emqx_fails(self, manager):
        manager.list_gateways.side_effect = RuntimeError("emqx down")

        assert await check_gateway_owner(make_interaction(user_id=42, node_id="cbaf0421")) is False

    async def test_concurrent_checks_hit_emqx_once(self, manager):
        def slow_list():
            time.sleep(0.05)
            return [GatewayData(node_id=0xCBAF0421, owner_id=42)]

        manager.list_gateways.side_effect = slow_list
        interactions = [make_interaction(user_id=42, node_id="cbaf0421") for _ in range(10)]

        results = await asyncio.gather(*(check_gateway_owner(i) for i in interactions))

        assert all(results)
        assert manager.list_gateways.call_count == 1


class TestCheckAnyGatewayOwnership:
    async def test_true_when_the_user_owns_something(self):
        with patch("bridger.cogs.mqtt.GatewayManagerEMQX") as cls:
            cls.return_value.list_gateways.return_value = [GatewayData(node_id=1, owner_id=42)]

            assert await check_any_gateway_ownership(make_interaction(user_id=42)) is True

    async def test_false_when_they_own_nothing(self):
        with patch("bridger.cogs.mqtt.GatewayManagerEMQX") as cls:
            cls.return_value.list_gateways.return_value = [GatewayData(node_id=1, owner_id=42)]

            assert await check_any_gateway_ownership(make_interaction(user_id=99)) is False

    async def test_false_when_emqx_fails(self):
        with patch("bridger.cogs.mqtt.GatewayManagerEMQX") as cls:
            cls.return_value.list_gateways.side_effect = RuntimeError("emqx down")

            assert await check_any_gateway_ownership(make_interaction(user_id=42)) is False


class TestNodeIdAutocomplete:
    @staticmethod
    def _interaction(nodes, delay=0.0):
        interaction = make_interaction()

        def get_all_node_ids():
            if delay:
                time.sleep(delay)
            return nodes

        reader = MagicMock()
        reader.get_all_node_ids.side_effect = get_all_node_ids
        interaction._reader = reader
        return interaction, reader

    async def test_filters_by_value_and_by_name(self):
        nodes = [
            {"value": "cbaf0421", "name": "CBAF (cbaf0421) - Hilltop"},
            {"value": "deadbeef", "name": "DEAD (deadbeef) - Basement"},
        ]
        interaction, reader = self._interaction(nodes)

        with patch("bridger.cogs.mqtt.InfluxReader", return_value=reader):
            by_value = await node_id_autocomplete(interaction, "!cbaf")
            by_name = await node_id_autocomplete(interaction, "basement")

        assert [c.value for c in by_value] == ["cbaf0421"]
        assert [c.value for c in by_name] == ["deadbeef"]

    async def test_caps_at_the_discord_limit(self):
        nodes = [{"value": f"{i:08x}", "name": f"node {i}"} for i in range(100)]
        interaction, reader = self._interaction(nodes)

        with patch("bridger.cogs.mqtt.InfluxReader", return_value=reader):
            assert len(await node_id_autocomplete(interaction, "")) == 25

    async def test_repeated_keystrokes_query_influx_once(self):
        # This runs per keystroke against a ~3s deadline; it used to issue a 30-day Flux query
        # every time, synchronously, on the event loop.
        nodes = [{"value": "cbaf0421", "name": "CBAF"}]
        interaction, reader = self._interaction(nodes, delay=0.02)

        with patch("bridger.cogs.mqtt.InfluxReader", return_value=reader):
            await asyncio.gather(*(node_id_autocomplete(interaction, "cba"[:i]) for i in range(1, 4)))

        assert reader.get_all_node_ids.call_count == 1

    async def test_returns_empty_on_failure(self):
        reader = MagicMock()
        reader.get_all_node_ids.side_effect = RuntimeError("influx down")
        interaction = make_interaction()

        with patch("bridger.cogs.mqtt.InfluxReader", return_value=reader):
            assert await node_id_autocomplete(interaction, "cbaf") == []

    async def test_tolerates_a_node_without_a_name(self):
        # Discord rejects a choice with a null name, so it falls back to the node id.
        interaction, reader = self._interaction([{"value": "cbaf0421", "name": None}])

        with patch("bridger.cogs.mqtt.InfluxReader", return_value=reader):
            choices = await node_id_autocomplete(interaction, "cbaf")

        assert [(c.name, c.value) for c in choices] == [("cbaf0421", "cbaf0421")]


class TestFormatOwner:
    def test_uses_the_cached_name(self):
        owner = MagicMock()
        owner.name = "someuser"  # assigned after construction, not via the constructor kwarg
        bot = MagicMock()
        bot.get_user.return_value = owner

        assert format_owner(bot, 42) == "someuser"

    def test_falls_back_to_a_mention(self):
        bot = MagicMock()
        bot.get_user.return_value = None

        assert format_owner(bot, 42) == "<@42>"


class TestGatewayPaginationView:
    @pytest.mark.parametrize(("count", "expected"), [(0, 0), (1, 0), (25, 0), (26, 1), (50, 1), (51, 2)])
    def test_max_page(self, count, expected):
        gateways = [GatewayData(node_id=i, owner_id=i) for i in range(count)]

        assert GatewayPaginationView(gateways, MagicMock()).max_page == expected


class TestDescribeGatewayError:
    def test_already_exists_names_the_node(self):
        message = MQTTCog._describe_gateway_error(GatewayAlreadyExistsError("whatever", _gateway()))

        assert "1a2b3c4d" in message
        assert "already exists" in message.lower()

    def test_validation_error_does_not_leak_the_exception_text(self):
        error = GatewayValidationError(f"Error creating gateway: {RAW_HTTP_ERROR}", _gateway(), status_code=400)

        message = MQTTCog._describe_gateway_error(error)

        assert "1a2b3c4d" in message
        assert "emqx.internal" not in message
        assert "/api/v5/" not in message

    def test_backend_error_reports_the_status_but_not_the_url(self):
        error = GatewayBackendError(f"Error talking to EMQX: {RAW_HTTP_ERROR}", _gateway(), status_code=500)

        message = MQTTCog._describe_gateway_error(error)

        assert "1a2b3c4d" in message
        assert "HTTP 500" in message
        assert "emqx.internal" not in message
        assert "/api/v5/" not in message

    def test_backend_error_without_a_status_omits_it(self):
        error = GatewayBackendError("Could not reach EMQX: connection refused", _gateway())

        message = MQTTCog._describe_gateway_error(error)

        assert "1a2b3c4d" in message
        assert "HTTP" not in message

    def test_each_error_type_gets_its_own_message(self):
        gateway = _gateway()

        already = MQTTCog._describe_gateway_error(GatewayAlreadyExistsError("x", gateway, status_code=409))
        invalid = MQTTCog._describe_gateway_error(GatewayValidationError("bad id", gateway, status_code=400))
        backend = MQTTCog._describe_gateway_error(GatewayBackendError("emqx down", gateway, status_code=500))

        assert already == "Gateway already exists: 1a2b3c4d"
        assert "Invalid gateway request" in invalid
        # A backend failure must not claim the gateway already exists, which is what it used to.
        assert "already exists" not in backend
        assert "HTTP 500" in backend


class TestParseTimeString:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1640995200", 1640995200),
            ("2022-01-01T00:00:00Z", 1640995200),
            ("2022-01-01T00:00:00+00:00", 1640995200),
            ("2022-01-01T00:00:00", 1640995200),  # naive input is assumed UTC
            ("2022-01-01", 1640995200),
            ("  2022-01-01  ", 1640995200),
        ],
    )
    def test_absolute_formats(self, value, expected):
        assert mqtt_cog.parse_time_string(value) == expected

    @pytest.mark.parametrize(
        ("value", "offset"),
        [("+1h", 3600), ("+30m", 1800), ("+2d", 172800), ("1w", 604800), ("-1h", -3600)],
    )
    def test_relative_formats(self, value, offset, monkeypatch):
        monkeypatch.setattr(mqtt_cog.time, "time", lambda: 1_000_000)

        assert mqtt_cog.parse_time_string(value) == 1_000_000 + offset

    @pytest.mark.parametrize("value", ["", "   ", "garbage", "5x", "2022-13-45", "not-a-time"])
    def test_unparseable_returns_none(self, value):
        assert mqtt_cog.parse_time_string(value) is None


class TestReply:
    @pytest.fixture
    def cog(self):
        from discord.ext import commands

        from bridger.cogs.mqtt import MQTTCog

        return MQTTCog(MagicMock(spec=commands.Bot), MagicMock(), MagicMock())

    async def test_uses_send_message_before_deferring(self, cog):
        interaction = make_interaction()
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        await cog.reply(interaction, "hello")

        interaction.response.send_message.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()

    async def test_uses_followup_after_deferring(self, cog):
        # send_message raises InteractionResponded once the command has deferred.
        interaction = make_interaction(responded=True)
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        await cog.reply(interaction, "hello")

        interaction.followup.send.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()

    async def test_followup_does_not_pass_delete_after(self, cog):
        # delete_after is not a Webhook.send parameter.
        interaction = make_interaction(responded=True)
        interaction.followup.send = AsyncMock()

        await cog.reply(interaction, "hello")

        assert "delete_after" not in interaction.followup.send.call_args.kwargs


@pytest.fixture
def cog():
    from discord.ext import commands

    from bridger.cogs.mqtt import MQTTCog

    bot = MagicMock(spec=commands.Bot)
    bot.get_user.return_value = None
    bot.influx_client = MagicMock()  # set by BridgerBot.setup_hook, not part of the Bot spec
    return MQTTCog(bot, MagicMock(), MagicMock())


def deferred_interaction(**kwargs):
    interaction = make_interaction(**kwargs)
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _sent_call(interaction):
    """Whichever reply path was actually taken."""
    for mock in (interaction.followup.send, interaction.response.send_message):
        if mock.await_args:
            return mock.await_args
    raise AssertionError("nothing was sent")


def sent_content(interaction):
    return _sent_call(interaction)[0][0]


def sent_kwargs(interaction):
    return _sent_call(interaction)[1]


class TestListAccountsCommand:
    async def test_an_admin_sees_every_gateway(self, cog, admin_role):
        role = make_role(ADMIN_ROLE)
        interaction = deferred_interaction(user_id=1, guild_roles=[role], user_roles=[role])
        cog.gateway_manager.list_gateways.return_value = [
            GatewayData(node_id=1, owner_id=1),
            GatewayData(node_id=2, owner_id=999),
        ]

        await cog.list_accounts.callback(cog, interaction)

        assert "There are 2 gateways in the system." in sent_content(interaction)

    async def test_a_regular_user_sees_only_their_own(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.list_gateways.return_value = [
            GatewayData(node_id=1, owner_id=1),
            GatewayData(node_id=2, owner_id=999),
        ]

        await cog.list_accounts.callback(cog, interaction)

        assert "There are 1 of your own gateways" in sent_content(interaction)

    async def test_message_when_the_user_owns_nothing(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.list_gateways.return_value = [GatewayData(node_id=2, owner_id=999)]

        await cog.list_accounts.callback(cog, interaction)

        assert "You don't own any provisioned gateways." in sent_content(interaction)

    async def test_paginates_beyond_25(self, cog, admin_role):
        role = make_role(ADMIN_ROLE)
        interaction = deferred_interaction(user_id=1, guild_roles=[role], user_roles=[role])
        cog.gateway_manager.list_gateways.return_value = [GatewayData(node_id=i, owner_id=1) for i in range(30)]

        await cog.list_accounts.callback(cog, interaction)

        assert "view" in sent_kwargs(interaction)


class TestRequestAccountCommand:
    async def test_returns_the_credentials_and_invalidates_the_cache(self, cog):
        interaction = deferred_interaction(user_id=1)
        gateway = GatewayData(node_id=0xCBAF0421, owner_id=1)
        cog.gateway_manager.create_gateway_user.return_value = (gateway, "hunter2xyz")

        # Prime the cache so the invalidation is observable.
        await mqtt_cog.gateway_cache.get_or_load(mqtt_cog.GATEWAY_CACHE_KEY, lambda: ["stale"])

        await cog.request_account.callback(cog, interaction, "cbaf0421")

        content = sent_content(interaction)
        assert "cbaf0421" in content
        assert "hunter2xyz" in content
        assert await mqtt_cog.gateway_cache._cache.get(mqtt_cog.GATEWAY_CACHE_KEY) is None


class TestDeleteAccountCommand:
    async def test_reports_success(self, cog):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.delete_gateway_user.return_value = True

        await cog.delete_account.callback(cog, interaction, "cbaf0421")

        assert "Gateway deleted" in sent_content(interaction)

    async def test_reports_a_missing_gateway(self, cog):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.delete_gateway_user.return_value = False

        await cog.delete_account.callback(cog, interaction, "cbaf0421")

        assert "Gateway not found" in sent_content(interaction)


class TestIsAliveCommand:
    async def test_reports_silence(self, cog):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.get_gateway.return_value = GatewayData(node_id=0xCBAF0421, owner_id=1)
        cog.influx_reader.get_recent_packets.return_value = []

        await cog.is_alive.callback(cog, interaction, "cbaf0421")

        assert "haven't received any packets" in sent_content(interaction)

    async def test_reports_the_most_recent_packet(self, cog):
        from datetime import UTC, datetime

        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.get_gateway.return_value = GatewayData(node_id=0xCBAF0421, owner_id=1)

        record = MagicMock()
        record.values = {"_time": datetime(2024, 1, 1, tzinfo=UTC)}
        table = MagicMock()
        table.records = [record]
        cog.influx_reader.get_recent_packets.return_value = [table]

        await cog.is_alive.callback(cog, interaction, "cbaf0421")

        assert "is alive" in sent_content(interaction)


class TestAddAnnotationCommand:
    async def test_rejects_a_bad_start_time(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)

        await cog.add_annotation.callback(cog, interaction, "cbaf0421", "reposition", "moved", start_time="nonsense")

        assert "Invalid start_time format" in sent_content(interaction)

    async def test_rejects_an_end_before_the_start(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)

        await cog.add_annotation.callback(
            cog, interaction, "cbaf0421", "reposition", "moved", start_time="2024-01-02", end_time="2024-01-01"
        )

        assert "End time must be after start time." in sent_content(interaction)

    async def test_rejects_a_global_annotation_from_a_non_admin(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)

        await cog.add_annotation.callback(cog, interaction, "cbaf0421", "reposition", "moved", global_annotation=True)

        assert "Only Bridger Admins" in sent_content(interaction)

    async def test_rejects_annotating_someone_elses_node(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)

        with patch("bridger.cogs.mqtt.GatewayManagerEMQX") as cls:
            cls.return_value.get_gateway.return_value = GatewayData(node_id=0xCBAF0421, owner_id=999)

            await cog.add_annotation.callback(cog, interaction, "cbaf0421", "reposition", "moved")

        assert "only add annotations for nodes you own" in sent_content(interaction)

    async def test_writes_the_annotation_for_the_owner(self, cog, admin_role):
        interaction = deferred_interaction(user_id=1)

        with (
            patch("bridger.cogs.mqtt.GatewayManagerEMQX") as cls,
            patch("bridger.cogs.mqtt.InfluxWriter") as writer_cls,
        ):
            cls.return_value.get_gateway.return_value = GatewayData(node_id=0xCBAF0421, owner_id=1)

            await cog.add_annotation.callback(cog, interaction, "cbaf0421", "reposition", "moved")

        writer_cls.return_value.write_annotation.assert_called_once()
        assert "Annotation added for node" in sent_content(interaction)


class TestUpdateAllGatewayRulesCommand:
    async def test_summarises_successes_and_failures(self, cog):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.list_gateways.return_value = [
            GatewayData(node_id=1, owner_id=1),
            GatewayData(node_id=2, owner_id=1),
        ]
        cog.gateway_manager.update_gateway_user_rules.side_effect = [True, False]

        await cog.update_all_gateway_rules.callback(cog, interaction)

        content = sent_content(interaction)
        assert "**Successful updates:** 1" in content
        assert "**Failed updates:** 1" in content

    async def test_handles_having_no_gateways(self, cog):
        interaction = deferred_interaction(user_id=1)
        cog.gateway_manager.list_gateways.return_value = []

        await cog.update_all_gateway_rules.callback(cog, interaction)

        assert "No gateways found to update." in sent_content(interaction)
