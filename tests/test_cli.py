from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ConnectionError
from tenacity import wait_none

from bridger.cli import create_user_command, delete_user_command, generate_apikey_command, list_users_command, main
from bridger.gateway import GatewayError


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr(create_user_command.retry, "wait", wait_none())


class TestCreateUserCommand:
    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_create_user_success(self, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_gateway = MagicMock()
        mock_gateway.user_string = "test_user"
        mock_manager.create_gateway_user.return_value = (mock_gateway, "test_password")

        args = MagicMock()
        args.gateway_id = "12345678"
        args.user_id = "987654321"

        create_user_command(args)

        mock_manager.create_gateway_user.assert_called_once()
        call = mock_manager.create_gateway_user.call_args
        assert call.args[0] == "12345678"
        user_arg = call.args[1]
        assert user_arg.id == 987654321
        assert isinstance(user_arg.id, int)
        mock_console.print.assert_called()

    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_create_user_gateway_error(self, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_gateway = MagicMock()
        mock_manager.create_gateway_user.side_effect = GatewayError("Test error", mock_gateway)

        args = MagicMock()
        args.gateway_id = "12345678"
        args.user_id = "987654321"

        create_user_command(args)

        mock_console.print.assert_called_with("Error creating gateway user: Test error", style="bold red")

    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_create_user_connection_error_retry(self, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_manager.create_gateway_user.side_effect = [
            ConnectionError("Connection failed"),
            ConnectionError("Connection failed"),
            (MagicMock(user_string="test_user"), "test_password"),
        ]

        args = MagicMock()
        args.gateway_id = "12345678"
        args.user_id = "987654321"

        create_user_command(args)

        assert mock_manager.create_gateway_user.call_count == 3

    def test_create_user_invalid_user_id_raises(self):
        args = MagicMock()
        args.gateway_id = "12345678"
        args.user_id = "not-a-number"

        with pytest.raises(ValueError):
            create_user_command(args)


class TestDeleteUserCommand:
    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_delete_user_success(self, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_manager.delete_gateway_user.return_value = True

        args = MagicMock()
        args.gateway_id = "12345678"

        delete_user_command(args)

        mock_manager.delete_gateway_user.assert_called_once_with("12345678")
        mock_console.print.assert_called_with("Gateway user deleted successfully!", style="bold green")

    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    @patch("bridger.cli.exit")
    def test_delete_user_failure(self, mock_exit, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_manager.delete_gateway_user.return_value = False

        args = MagicMock()
        args.gateway_id = "12345678"

        delete_user_command(args)

        mock_console.print.assert_called_with("Failed to delete gateway user", style="bold red")
        mock_exit.assert_called_once_with(1)

    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    @patch("bridger.cli.exit")
    def test_delete_user_exception(self, mock_exit, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_manager.delete_gateway_user.side_effect = Exception("Test error")

        args = MagicMock()
        args.gateway_id = "12345678"

        delete_user_command(args)

        mock_console.print.assert_called_with("Error deleting gateway user: Test error", style="bold red")
        mock_exit.assert_called_once_with(1)


class TestListUsersCommand:
    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_list_users_with_gateways(self, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_gateway = MagicMock()
        mock_gateway.user_string = "test_user"
        mock_gateway.node_hex_id_without_bang = "abcd1234"
        mock_manager.list_gateways.return_value = [mock_gateway]

        args = MagicMock()

        list_users_command(args)

        mock_manager.list_gateways.assert_called_once()
        mock_console.print.assert_called()

    @patch("bridger.cli.Table")
    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_list_users_multiple_gateways(self, mock_console, mock_manager_class, mock_table_class):
        mock_manager = mock_manager_class.return_value
        gateways = [MagicMock(user_string=f"user{i}", node_hex_id_without_bang=f"aaaa111{i}") for i in range(3)]
        mock_manager.list_gateways.return_value = gateways
        mock_table = mock_table_class.return_value

        args = MagicMock()

        list_users_command(args)

        assert mock_table.add_row.call_count == 3
        mock_table.add_row.assert_any_call("user0", "!aaaa1110")
        mock_table.add_row.assert_any_call("user2", "!aaaa1112")

    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    def test_list_users_no_gateways(self, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_manager.list_gateways.return_value = []

        args = MagicMock()

        list_users_command(args)

        mock_console.print.assert_called_with("No gateway users found", style="yellow")

    @patch("bridger.cli.GatewayManagerEMQX")
    @patch("bridger.cli.console")
    @patch("bridger.cli.exit")
    def test_list_users_exception(self, mock_exit, mock_console, mock_manager_class):
        mock_manager = mock_manager_class.return_value
        mock_manager.list_gateways.side_effect = Exception("Test error")

        args = MagicMock()

        list_users_command(args)

        mock_console.print.assert_called_with("Error listing gateway users: Test error", style="bold red")
        mock_exit.assert_called_once_with(1)


class TestGenerateAPIKeyCommand:
    def test_generate_apikey_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bootstrap = tmp_path / "boot" / "api_key.bootstrap"
        args = MagicMock()
        args.bootstrap_file = str(bootstrap)
        args.force = False

        with patch("bridger.cli.console"):
            generate_apikey_command(args)

        assert bootstrap.exists()
        api_part, secret_part, role_part = bootstrap.read_text().strip().split(":")
        assert api_part.startswith("bridger-")
        assert len(api_part) == len("bridger-") + 16
        assert len(secret_part) == 64
        assert role_part == "administrator"

    def test_generate_apikey_creates_parent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bootstrap = tmp_path / "a" / "b" / "c" / "api.bootstrap"
        args = MagicMock()
        args.bootstrap_file = str(bootstrap)
        args.force = False

        with patch("bridger.cli.console"):
            generate_apikey_command(args)

        assert bootstrap.exists()
        assert bootstrap.parent.is_dir()

    def test_generate_apikey_bootstrap_exists_no_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bootstrap = tmp_path / "existing.bootstrap"
        bootstrap.write_text("original\n")
        args = MagicMock()
        args.bootstrap_file = str(bootstrap)
        args.force = False

        with patch("bridger.cli.console") as mock_console:
            generate_apikey_command(args)

        assert bootstrap.read_text() == "original\n"
        mock_console.print.assert_called_with(
            f"Bootstrap file already exists at {bootstrap}. Use -f to force overwrite.",
            style="bold red",
        )

    def test_generate_apikey_env_all_keys_exist_no_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("EMQX_API_KEY=existing\nEMQX_SECRET_KEY=existing\nINFLUXDB_V2_TOKEN=existing\n")
        bootstrap = tmp_path / "boot" / "api_key.bootstrap"
        args = MagicMock()
        args.bootstrap_file = str(bootstrap)
        args.force = False

        with patch("bridger.cli.console") as mock_console:
            generate_apikey_command(args)

        assert not bootstrap.exists()
        mock_console.print.assert_any_call("Some keys already exist in .env file:", style="bold red")
        mock_console.print.assert_any_call("  - EMQX_API_KEY", style="red")
        mock_console.print.assert_any_call("  - EMQX_SECRET_KEY", style="red")
        mock_console.print.assert_any_call("  - INFLUXDB_V2_TOKEN", style="red")
        mock_console.print.assert_any_call("Use -f to force overwrite.", style="bold red")

    def test_generate_apikey_env_partial_match_no_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("EMQX_SECRET_KEY=existing\n")
        bootstrap = tmp_path / "boot" / "api_key.bootstrap"
        args = MagicMock()
        args.bootstrap_file = str(bootstrap)
        args.force = False

        with patch("bridger.cli.console") as mock_console:
            generate_apikey_command(args)

        assert not bootstrap.exists()
        mock_console.print.assert_any_call("  - EMQX_SECRET_KEY", style="red")
        for call in mock_console.print.call_args_list:
            if call.args:
                assert call.args[0] != "  - EMQX_API_KEY"
                assert call.args[0] != "  - INFLUXDB_V2_TOKEN"

    def test_generate_apikey_force_overwrites_bootstrap_and_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bootstrap = tmp_path / "existing.bootstrap"
        bootstrap.write_text("original\n")
        (tmp_path / ".env").write_text("EMQX_API_KEY=existing\n")
        args = MagicMock()
        args.bootstrap_file = str(bootstrap)
        args.force = True

        with patch("bridger.cli.console"):
            generate_apikey_command(args)

        content = bootstrap.read_text()
        assert content != "original\n"
        assert content.startswith("bridger-")
        assert content.endswith(":administrator\n")


class TestMainFunction:
    def test_main_no_command(self):
        with patch("sys.argv", ["bridger"]):
            with patch("bridger.cli.exit", side_effect=SystemExit) as mock_exit:
                with patch("bridger.cli.argparse.ArgumentParser.print_help") as mock_help:
                    with pytest.raises(SystemExit):
                        main()
                    mock_help.assert_called_once()
                    mock_exit.assert_called_once_with(1)

    def test_main_unknown_command(self):
        with patch("sys.argv", ["bridger", "not-a-command"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    @patch("bridger.cli.create_user_command")
    def test_main_create_user_command(self, mock_create_user):
        test_args = ["bridger", "create-user", "12345678", "987654321"]
        with patch("sys.argv", test_args):
            main()
            mock_create_user.assert_called_once()
            parsed = mock_create_user.call_args.args[0]
            assert parsed.gateway_id == "12345678"
            assert parsed.user_id == "987654321"

    @patch("bridger.cli.delete_user_command")
    def test_main_delete_user_command(self, mock_delete_user):
        test_args = ["bridger", "delete-user", "12345678"]
        with patch("sys.argv", test_args):
            main()
            mock_delete_user.assert_called_once()
            assert mock_delete_user.call_args.args[0].gateway_id == "12345678"

    @patch("bridger.cli.list_users_command")
    def test_main_list_users_command(self, mock_list_users):
        test_args = ["bridger", "list-users"]
        with patch("sys.argv", test_args):
            main()
            mock_list_users.assert_called_once()

    @patch("bridger.cli.generate_apikey_command")
    def test_main_generate_apikey_command(self, mock_generate_apikey):
        test_args = ["bridger", "generate-apikey"]
        with patch("sys.argv", test_args):
            main()
            mock_generate_apikey.assert_called_once()
            parsed = mock_generate_apikey.call_args.args[0]
            assert parsed.bootstrap_file is None
            assert parsed.force is False

    @patch("bridger.cli.generate_apikey_command")
    def test_main_generate_apikey_with_flags(self, mock_generate_apikey):
        test_args = ["bridger", "generate-apikey", "-b", "/tmp/boot", "-f"]
        with patch("sys.argv", test_args):
            main()
            parsed = mock_generate_apikey.call_args.args[0]
            assert parsed.bootstrap_file == "/tmp/boot"
            assert parsed.force is True
