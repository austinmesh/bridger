from unittest.mock import MagicMock, patch

import pytest

from bridger.bot import BridgerBot, create_bot, get_owner_id, main


class TestGetOwnerId:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("123", 123),
            ("  123  ", 123),
            ("", None),
            ("   ", None),
            ("abc", None),
            ("12.5", None),
        ],
    )
    def test_parsing(self, monkeypatch, raw, expected):
        monkeypatch.setenv("DISCORD_BOT_OWNER_ID", raw)
        assert get_owner_id() == expected

    def test_unset(self, monkeypatch):
        # An empty value raises ValueError rather than TypeError, which the old handler missed.
        monkeypatch.delenv("DISCORD_BOT_OWNER_ID", raising=False)
        assert get_owner_id() is None


class TestCreateBot:
    def test_registers_extensions_and_command(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_OWNER_ID", "42")
        bot = create_bot()

        assert isinstance(bot, BridgerBot)
        assert bot.owner_id == 42
        assert bot.initial_extensions == ["bridger.cogs.mqtt", "bridger.cogs.testmsg"]
        assert bot.get_command("sync-commands") is not None

    def test_builds_without_an_owner_id(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_OWNER_ID", "")
        assert create_bot().owner_id is None


class TestMain:
    def test_returns_error_without_a_token(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        assert main() == 1

    def test_runs_the_bot_with_a_token(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
        with patch("bridger.bot.create_bot") as create:
            bot = MagicMock()
            create.return_value = bot

            assert main() == 0
            bot.run.assert_called_once_with("token")
