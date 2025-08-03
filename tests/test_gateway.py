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
    assert gateways[0].node_id == int("1a2b3c4d", 16)


# Test create_gateway_user
def test_create_gateway_user(gateway_manager, emqx_mock):
    # Mock the create_user and create_user_authorization_rules_built_in_database methods
    emqx_mock.create_user.return_value = None
    emqx_mock.create_user_authorization_rules_built_in_database.return_value = None

    # Execute the method under test
    gateway, password = gateway_manager.create_gateway_user("1a2b3c4d", mock_discord_user)

    # Assertions
    assert isinstance(gateway, GatewayData)
    assert gateway.node_hex_id_with_bang == "!1a2b3c4d"
    assert gateway.owner_id == mock_discord_user.id
    assert len(password) == 10

    # Verify that create_user was called with the correct parameters
    emqx_mock.create_user.assert_called_once_with(gateway_manager.authentication_id, gateway.user_string, password)

    # Verify that create_user_authorization_rules_built_in_database was called
    emqx_mock.create_user_authorization_rules_built_in_database.assert_called_once_with(
        gateway.user_string,
        {
            "rules": [{"action": "all", "topic": "fake/2/e/+/!1a2b3c4d", "permission": "allow"}],
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

    success = gateway_manager.delete_gateway_user("1a2b3c4d")

    assert success is True
    emqx_mock.delete_user.assert_called_once_with(gateway_manager.authentication_id, "1234567890-1a2b3c4d")
    emqx_mock.delete_user_authorization_rules_built_in_database.assert_called_once()


# Test delete_gateway_user when deletion fails
def test_delete_gateway_user_fail(gateway_manager, emqx_mock):
    emqx_mock.delete_user.side_effect = Exception("Deletion failed")

    success = gateway_manager.delete_gateway_user("1a2b3c4d")

    assert success is False
    emqx_mock.delete_user.assert_called_once()


# Test get_gateway
def test_get_gateway(gateway_manager):
    gateway = gateway_manager.get_gateway("1a2b3c4d")
    assert isinstance(gateway, GatewayData)
    assert gateway.node_hex_id_without_bang == "1a2b3c4d"


# Test reset_gateway_password
def test_reset_gateway_password(gateway_manager, emqx_mock):
    emqx_mock.update_user_password.return_value = None
    gateway, password = gateway_manager.reset_gateway_password("1a2b3c4d", mock_discord_user)

    assert isinstance(gateway, GatewayData)
    assert gateway.owner_id == mock_discord_user.id
    assert len(password) == 10
    emqx_mock.update_user_password.assert_called_once_with(gateway_manager.authentication_id, gateway.user_string, password)


class TestGatewayDataNodeMixin:
    """Test GatewayData's inherited NodeMixin functionality"""

    def test_gateway_data_hex_id_with_bang_basic(self):
        """Test GatewayData hex ID conversion from node_id"""
        gateway = GatewayData(node_id=int("1a2b3c4d", 16), owner_id=12345)
        assert gateway.node_hex_id_with_bang == "!1a2b3c4d"
        assert gateway.node_hex_id_without_bang == "1a2b3c4d"

    def test_gateway_data_node_id_property(self):
        """Test GatewayData node_id property storage"""
        gateway = GatewayData(node_id=439041101, owner_id=12345)
        assert gateway.node_id == 439041101
        assert gateway.node_id == int("1a2b3c4d", 16)

    def test_gateway_data_color_property(self):
        """Test GatewayData color property extraction"""
        gateway = GatewayData(node_id=int("1a2b3c4d", 16), owner_id=12345)
        assert gateway.color == "2b3c4d"  # Last 6 characters

    def test_gateway_data_user_string_property(self):
        """Test GatewayData user_string property"""
        gateway = GatewayData(node_id=int("1a2b3c4d", 16), owner_id=12345)
        assert gateway.user_string == "12345-1a2b3c4d"

    def test_gateway_data_small_node_id(self):
        """Test GatewayData with small node ID requiring zero padding"""
        gateway = GatewayData(node_id=255, owner_id=12345)  # 0xff
        assert gateway.node_hex_id_with_bang == "!000000ff"
        assert gateway.node_hex_id_without_bang == "000000ff"
        assert gateway.color == "0000ff"

    def test_gateway_data_large_node_id(self):
        """Test GatewayData with large node ID"""
        gateway = GatewayData(node_id=4294967295, owner_id=12345)  # 0xffffffff
        assert gateway.node_hex_id_with_bang == "!ffffffff"
        assert gateway.node_hex_id_without_bang == "ffffffff"
        assert gateway.color == "ffffff"


# Test create_gateway_rules_dict static method
def test_create_gateway_rules_dict():
    """Test the static method that creates MQTT authorization rules dictionary"""
    gateway_id = "!1a2b3c4d"
    username = "12345-1a2b3c4d"

    rules_dict = GatewayManagerEMQX.create_gateway_rules_dict(gateway_id, username)

    expected_dict = {
        "rules": [{"action": "all", "topic": "fake/2/e/+/!1a2b3c4d", "permission": "allow"}],
        "username": "12345-1a2b3c4d",
    }

    assert rules_dict == expected_dict


def test_create_gateway_rules_dict_without_bang():
    """Test create_gateway_rules_dict with gateway_id without leading !"""
    gateway_id = "1a2b3c4d"
    username = "12345-1a2b3c4d"

    rules_dict = GatewayManagerEMQX.create_gateway_rules_dict(gateway_id, username)

    expected_dict = {
        "rules": [{"action": "all", "topic": "fake/2/e/+/1a2b3c4d", "permission": "allow"}],
        "username": "12345-1a2b3c4d",
    }

    assert rules_dict == expected_dict


# Test update_gateway_user_rules method
def test_update_gateway_user_rules_success(gateway_manager, emqx_mock):
    """Test successful update of gateway user rules"""
    # Mock the EMQX API calls
    emqx_mock.delete_user_authorization_rules_built_in_database.return_value = None
    emqx_mock.create_user_authorization_rules_built_in_database.return_value = None

    # Execute the method under test
    success = gateway_manager.update_gateway_user_rules("1a2b3c4d")

    # Assertions
    assert success is True

    # Verify that delete_user_authorization_rules_built_in_database was called
    emqx_mock.delete_user_authorization_rules_built_in_database.assert_called_once_with("1234567890-1a2b3c4d")

    # Verify that create_user_authorization_rules_built_in_database was called with correct rules
    expected_rules = {
        "rules": [{"action": "all", "topic": "fake/2/e/+/!1a2b3c4d", "permission": "allow"}],
        "username": "1234567890-1a2b3c4d",
    }
    emqx_mock.create_user_authorization_rules_built_in_database.assert_called_once_with(
        "1234567890-1a2b3c4d", expected_rules
    )  # noqa: E501


def test_update_gateway_user_rules_with_bang(gateway_manager, emqx_mock):
    """Test update_gateway_user_rules with gateway_id that has leading !"""
    # Mock the EMQX API calls
    emqx_mock.delete_user_authorization_rules_built_in_database.return_value = None
    emqx_mock.create_user_authorization_rules_built_in_database.return_value = None

    # Execute the method under test
    success = gateway_manager.update_gateway_user_rules("!1a2b3c4d")

    # Assertions
    assert success is True

    # Verify that the correct rules were created (should be the same regardless of input format)
    expected_rules = {
        "rules": [{"action": "all", "topic": "fake/2/e/+/!1a2b3c4d", "permission": "allow"}],
        "username": "1234567890-1a2b3c4d",
    }
    emqx_mock.create_user_authorization_rules_built_in_database.assert_called_once_with(
        "1234567890-1a2b3c4d", expected_rules
    )  # noqa: E501


def test_update_gateway_user_rules_gateway_not_found(gateway_manager, emqx_mock):
    """Test update_gateway_user_rules when gateway doesn't exist"""
    # Mock list_users to return empty data to simulate gateway not found
    emqx_mock.list_users.return_value = {"data": []}

    # Execute the method under test
    success = gateway_manager.update_gateway_user_rules("nonexistent")

    # Assertions
    assert success is False

    # Verify that EMQX API methods were not called since gateway wasn't found
    emqx_mock.delete_user_authorization_rules_built_in_database.assert_not_called()
    emqx_mock.create_user_authorization_rules_built_in_database.assert_not_called()


def test_update_gateway_user_rules_emqx_error(gateway_manager, emqx_mock):
    """Test update_gateway_user_rules when EMQX API calls fail"""
    # Mock delete_user_authorization_rules_built_in_database to raise an exception
    emqx_mock.delete_user_authorization_rules_built_in_database.side_effect = Exception("EMQX API error")

    # Execute the method under test
    success = gateway_manager.update_gateway_user_rules("1a2b3c4d")

    # Assertions
    assert success is False

    # Verify that delete was attempted
    emqx_mock.delete_user_authorization_rules_built_in_database.assert_called_once_with("1234567890-1a2b3c4d")

    # Verify that create was not called due to the exception
    emqx_mock.create_user_authorization_rules_built_in_database.assert_not_called()
