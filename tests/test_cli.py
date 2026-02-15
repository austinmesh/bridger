import os
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ConnectionError

from bridger.cli import create_user_command, delete_user_command, generate_apikey_command, list_users_command, main
from bridger.gateway import GatewayError


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
    @patch("bridger.cli.secrets.token_hex")
    @patch("bridger.cli.secrets.token_urlsafe")
    @patch("bridger.cli.console")
    def test_generate_apikey_success(self, mock_console, mock_token_urlsafe, mock_token_hex):
        mock_token_hex.side_effect = ["abcd1234", "secretkey123456"]
        mock_token_urlsafe.return_value = "influxtoken123"

        args = MagicMock()
        args.bootstrap_file = None
        args.force = False

        with patch("bridger.cli.Path") as mock_path_class:
            mock_bootstrap_path = mock_path_class.return_value
            mock_bootstrap_path.exists.return_value = False
            mock_env_path = mock_path_class.return_value
            mock_env_path.exists.return_value = False

            with patch("builtins.open", create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file

                generate_apikey_command(args)

                mock_file.write.assert_called_with("bridger-abcd1234:secretkey123456:administrator\n")
                mock_console.print.assert_called()

    @patch("bridger.cli.console")
    def test_generate_apikey_bootstrap_exists_no_force(self, mock_console):
        args = MagicMock()
        args.bootstrap_file = None
        args.force = False

        with patch("bridger.cli.Path") as mock_path_class:
            mock_bootstrap_path = MagicMock()
            mock_bootstrap_path.__str__ = MagicMock(return_value="/opt/emqx/etc/api_key.bootstrap")
            mock_bootstrap_path.exists.return_value = True
            mock_path_class.return_value = mock_bootstrap_path

            generate_apikey_command(args)

            mock_console.print.assert_called_with(
                "Bootstrap file already exists at /opt/emqx/etc/api_key.bootstrap. Use -f to force overwrite.",
                style="bold red",
            )

    @patch("bridger.cli.console")
    def test_generate_apikey_env_keys_exist_no_force(self, mock_console):
        args = MagicMock()
        args.bootstrap_file = None
        args.force = False

        with patch("bridger.cli.Path") as mock_path_class:
            mock_bootstrap_path = mock_path_class.return_value
            mock_bootstrap_path.exists.return_value = False
            mock_env_path = mock_path_class.return_value
            mock_env_path.exists.return_value = True

            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = "EMQX_API_KEY=existing"

                generate_apikey_command(args)

                mock_console.print.assert_called()


class TestMainFunction:
    def test_main_no_command(self):
        with patch("sys.argv", ["bridger"]):
            # Mock exit to raise SystemExit to prevent continued execution
            with patch("bridger.cli.exit", side_effect=SystemExit) as mock_exit:
                with patch("bridger.cli.argparse.ArgumentParser.print_help") as mock_help:
                    with pytest.raises(SystemExit):
                        main()
                    mock_help.assert_called_once()
                    mock_exit.assert_called_once_with(1)

    @patch("bridger.cli.create_user_command")
    def test_main_create_user_command(self, mock_create_user):
        test_args = ["bridger", "create-user", "12345678", "987654321"]
        with patch("sys.argv", test_args):
            main()
            mock_create_user.assert_called_once()

    @patch("bridger.cli.delete_user_command")
    def test_main_delete_user_command(self, mock_delete_user):
        test_args = ["bridger", "delete-user", "12345678"]
        with patch("sys.argv", test_args):
            main()
            mock_delete_user.assert_called_once()

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


class TestEnvironmentVariables:
    def test_environment_variables_loaded(self):
        with patch.dict(
            os.environ,
            {"EMQX_API_KEY": "test_api_key", "EMQX_SECRET_KEY": "test_secret_key", "EMQX_URL": "http://test.emqx.com"},
        ):
            # Reimport the module to trigger environment variable loading
            import importlib

            import bridger.cli

            importlib.reload(bridger.cli)

            assert bridger.cli.EMQX_API_KEY == "test_api_key"
            assert bridger.cli.EMQX_SECRET_KEY == "test_secret_key"
            assert bridger.cli.EMQX_URL == "http://test.emqx.com"
