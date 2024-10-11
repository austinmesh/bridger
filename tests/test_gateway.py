from unittest.mock import MagicMock

import pytest
from discord import User
from requests import HTTPError

from bridger.gateway import GatewayData, GatewayError, GatewayManagerEMQX

# Sample data for mocking
state_mock = MagicMock()
user_data = {"id": 1234567890, "username": "test_user", "discriminator": "1234", "avatar": "test_avatar"}
mock_discord_user = User(data=user_data, state=state_mock)
mock_gateway_data = {"user_id": "1234567890-1a2b3c4d"}


# Fixture for EMQXClient mock
@pytest.fixture
def emqx_mock():
    mock = MagicMock()
    mock.list_users.return_value = {"data": [mock_gateway_data]}
    return mock


# Fixture for GatewayManagerEMQX
@pytest.fixture
def gateway_manager(emqx_mock):
    return GatewayManagerEMQX(emqx=emqx_mock)


# Test prepare_gateway_id
def test_prepare_gateway_id():
    gateway_id, gateway_id_without_bang, node_id = GatewayManagerEMQX.prepare_gateway_id("1a2b3c4d")
    assert gateway_id == "!1a2b3c4d"
    assert gateway_id_without_bang == "1a2b3c4d"
    assert node_id == int("1a2b3c4d", 16)

    with pytest.raises(ValueError):
        GatewayManagerEMQX.prepare_gateway_id("123")  # Less than 8 chars


# Test generate_password
def test_generate_password(gateway_manager):
    password = gateway_manager.generate_password()
    assert len(password) == 10
    assert all(c.isalnum() for c in password)  # Password is alphanumeric


# Test list_gateways
def test_list_gateways(gateway_manager):
    gateways = list(gateway_manager.list_gateways())
    assert len(gateways) == 1
    assert isinstance(gateways[0], GatewayData)
    assert gateways[0].owner_id == 1234567890
    assert gateways[0].node_hex_id == "1a2b3c4d"


# Test create_gateway_user
def test_create_gateway_user(gateway_manager, emqx_mock):
    # Mock the create_user and create_user_authorization_rules_built_in_database methods
    emqx_mock.create_user.return_value = None
    emqx_mock.create_user_authorization_rules_built_in_database.return_value = None

    # Execute the method under test
    gateway, password = gateway_manager.create_gateway_user("1a2b3c4d", mock_discord_user)

    # Assertions
    assert isinstance(gateway, GatewayData)
    assert gateway.node_hex_id == "!1a2b3c4d"
    assert gateway.owner_id == mock_discord_user.id
    assert len(password) == 10

    # Verify that create_user was called with the correct parameters
    emqx_mock.create_user.assert_called_once_with(gateway_manager.authentication_id, gateway.user_string, password)

    # Verify that create_user_authorization_rules_built_in_database was called
    emqx_mock.create_user_authorization_rules_built_in_database.assert_called_once_with(
        gateway.user_string,
        {
            "rules": [{"action": "all", "topic": "egr/home/2/e/LongFast/!1a2b3c4d", "permission": "allow"}],
            "username": gateway.user_string,
        },
    )


# Test create_gateway_user when user already exists
def test_create_gateway_user_already_exists(gateway_manager, emqx_mock):
    emqx_mock.create_user.side_effect = HTTPError("User already exists", response=MagicMock(status_code=400))

    with pytest.raises(GatewayError):
        gateway_manager.create_gateway_user("1a2b3c4d", mock_discord_user)


# Test delete_gateway_user
def test_delete_gateway_user(gateway_manager, emqx_mock):
    emqx_mock.delete_user.return_value = None
    emqx_mock.delete_user_authorization_rules_built_in_database.return_value = None

    success = gateway_manager.delete_gateway_user("1a2b3c4d", mock_discord_user)

    assert success is True
    emqx_mock.delete_user.assert_called_once_with(gateway_manager.authentication_id, "1234567890-1a2b3c4d")
    emqx_mock.delete_user_authorization_rules_built_in_database.assert_called_once()


# Test delete_gateway_user when deletion fails
def test_delete_gateway_user_fail(gateway_manager, emqx_mock):
    emqx_mock.delete_user.side_effect = Exception("Deletion failed")

    success = gateway_manager.delete_gateway_user("1a2b3c4d", mock_discord_user)

    assert success is False
    emqx_mock.delete_user.assert_called_once()


# Test get_gateway
def test_get_gateway(gateway_manager):
    gateway = gateway_manager.get_gateway("1a2b3c4d")
    assert isinstance(gateway, GatewayData)
    assert gateway.node_hex_id == "1a2b3c4d"


# Test reset_gateway_password
def test_reset_gateway_password(gateway_manager, emqx_mock):
    emqx_mock.update_user_password.return_value = None
    gateway, password = gateway_manager.reset_gateway_password("1a2b3c4d", mock_discord_user)

    assert isinstance(gateway, GatewayData)
    assert gateway.owner_id == mock_discord_user.id
    assert len(password) == 10
    emqx_mock.update_user_password.assert_called_once_with(gateway_manager.authentication_id, gateway.user_string, password)
