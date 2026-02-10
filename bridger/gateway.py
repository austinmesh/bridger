import os
import re
import secrets
import string
from dataclasses import dataclass
from typing import Generator, Union

from discord import Member, User
from requests import HTTPError

from bridger.config import MESHCORE_MQTT_TOPIC, MQTT_TOPIC
from bridger.emqx import EMQXClient
from bridger.log import logger

EMQX_API_KEY = os.getenv("EMQX_API_KEY")
EMQX_SECRET_KEY = os.getenv("EMQX_SECRET_KEY")
EMQX_URL = os.getenv("EMQX_URL")
PASSWORD_LENGTH = 10

# Node ID length constants
MESHTASTIC_NODE_ID_LENGTH = 8
MESHCORE_NODE_ID_LENGTH = 64

emqx = EMQXClient(EMQX_URL, EMQX_API_KEY, EMQX_SECRET_KEY)


@dataclass
class GatewayData:
    """Gateway data supporting both Meshtastic (8-char) and MeshCore (64-char) node IDs."""

    node_hex_id: str  # The hex ID without leading !
    owner_id: int
    node_type: str  # "meshtastic" or "meshcore"

    @property
    def node_hex_id_without_bang(self) -> str:
        return self.node_hex_id

    @property
    def node_hex_id_with_bang(self) -> str:
        return f"!{self.node_hex_id}"

    @property
    def user_string(self) -> str:
        return f"{self.owner_id}-{self.node_hex_id}"


class GatewayError(Exception):
    def __init__(self, message: str, gateway: GatewayData):
        super().__init__(message)
        self.gateway = gateway


class GatewayManagerEMQX:
    authentication_id = "password_based:built_in_database"

    def __init__(self, emqx: EMQXClient):
        self.emqx = emqx

    @staticmethod
    def prepare_gateway_id(gateway_id: str) -> tuple[str, str, str]:
        """Prepare and validate a gateway ID.

        Returns:
            tuple: (gateway_id_with_bang, gateway_id_without_bang, node_type)
        """
        # Remove leading ! if present
        gateway_id_without_bang = gateway_id.lstrip("!")
        gateway_id_with_bang = f"!{gateway_id_without_bang}"

        # Determine node type based on length
        if len(gateway_id_without_bang) == MESHTASTIC_NODE_ID_LENGTH:
            node_type = "meshtastic"
        elif len(gateway_id_without_bang) == MESHCORE_NODE_ID_LENGTH:
            node_type = "meshcore"
        else:
            raise ValueError(
                f"Gateway ID must be {MESHTASTIC_NODE_ID_LENGTH} characters (Meshtastic) "
                f"or {MESHCORE_NODE_ID_LENGTH} characters (MeshCore)"
            )

        # Validate it's valid hex
        try:
            int(gateway_id_without_bang, 16)
        except ValueError:
            raise ValueError("Gateway ID must be a valid hex string")

        logger.debug(f"Gateway ID: {gateway_id_without_bang}")
        logger.debug(f"Node type: {node_type}")

        return gateway_id_with_bang, gateway_id_without_bang, node_type

    @staticmethod
    def generate_password() -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for i in range(PASSWORD_LENGTH))

    def list_gateways(self) -> Generator[GatewayData, None, None]:
        emqx_users = self.emqx.list_users(self.authentication_id)

        # Regex patterns for both Meshtastic (8-char) and MeshCore (64-char) hex IDs
        meshtastic_regex = r"^([0-9]+)-([0-9a-fA-F]{8})$"
        meshcore_regex = r"^([0-9]+)-([0-9a-fA-F]{64})$"

        gateways = []

        for user in emqx_users["data"]:
            user_id = user["user_id"]

            # Try Meshtastic pattern first
            meshtastic_match = re.match(meshtastic_regex, user_id)
            if meshtastic_match:
                owner_id = int(meshtastic_match.group(1))
                node_hex_id = meshtastic_match.group(2)
                gateways.append(GatewayData(node_hex_id=node_hex_id, owner_id=owner_id, node_type="meshtastic"))
                continue

            # Try MeshCore pattern
            meshcore_match = re.match(meshcore_regex, user_id)
            if meshcore_match:
                owner_id = int(meshcore_match.group(1))
                node_hex_id = meshcore_match.group(2)
                gateways.append(GatewayData(node_hex_id=node_hex_id, owner_id=owner_id, node_type="meshcore"))

        return gateways

    @staticmethod
    def create_gateway_rules_dict(gateway_id: str, username: str, node_type: str) -> dict:
        """Create MQTT authorization rules based on node type.

        Meshtastic topics: {base_topic}/+/{gateway_id} (with ! prefix)
        MeshCore topics (no ! prefix):
            - {base_topic}/info
            - {base_topic}/stats/core
            - {base_topic}/stats/radio
            - {base_topic}/stats/packets
            - {base_topic}/packets
        """
        if node_type == "meshtastic":
            topic_prefix = MQTT_TOPIC.removesuffix("/#")
            mqtt_rules = [{"action": "all", "topic": f"{topic_prefix}/+/{gateway_id}", "permission": "allow"}]
        elif node_type == "meshcore":
            topic_prefix = MESHCORE_MQTT_TOPIC.removesuffix("/#")
            # MeshCore topics don't use the ! prefix
            gateway_id_clean = gateway_id.lstrip("!")
            base_topic = f"{topic_prefix}/{gateway_id_clean}"
            mqtt_rules = [
                {"action": "all", "topic": f"{base_topic}/info", "permission": "allow"},
                {"action": "all", "topic": f"{base_topic}/stats/core", "permission": "allow"},
                {"action": "all", "topic": f"{base_topic}/stats/radio", "permission": "allow"},
                {"action": "all", "topic": f"{base_topic}/stats/packets", "permission": "allow"},
                {"action": "all", "topic": f"{base_topic}/packets", "permission": "allow"},
            ]
        else:
            raise ValueError(f"Unknown node type: {node_type}")

        return {"rules": mqtt_rules, "username": username}

    def create_gateway_user(self, gateway_id: str, discord_user: Union[User, Member]) -> tuple[GatewayData, str]:
        gateway_id_with_bang, gateway_id_without_bang, node_type = self.prepare_gateway_id(gateway_id)
        password = self.generate_password()

        gateway = GatewayData(node_hex_id=gateway_id_without_bang, owner_id=discord_user.id, node_type=node_type)
        rules = self.create_gateway_rules_dict(gateway_id_with_bang, gateway.user_string, node_type)

        try:
            self.emqx.create_user(self.authentication_id, gateway.user_string, password)
            self.emqx.create_user_authorization_rules_built_in_database(gateway.user_string, rules)
        except HTTPError as e:
            if e.response.status_code == 400:
                raise GatewayError(f"Error creating gateway: {e}", gateway)
            else:
                raise GatewayError(f"Gateway already exists: {e}", gateway)
        return gateway, password

    def update_gateway_user_rules(self, gateway_id: str) -> bool:
        try:
            gateway = self.get_gateway(gateway_id)
            self.emqx.delete_user_authorization_rules_built_in_database(gateway.user_string)
            rules = self.create_gateway_rules_dict(gateway.node_hex_id_with_bang, gateway.user_string, gateway.node_type)
            self.emqx.create_user_authorization_rules_built_in_database(gateway.user_string, rules)
            return True
        except Exception as e:
            logger.error(f"Failed to update gateway rules for {gateway_id}: {e}")
            return False

    def delete_gateway_user(self, gateway_id: str) -> bool:
        try:
            gateway = self.get_gateway(gateway_id)
            self.emqx.delete_user(self.authentication_id, gateway.user_string)
            self.emqx.delete_user_authorization_rules_built_in_database(gateway.user_string)
        except Exception:
            return False

        return True

    def get_gateway(self, gateway_id: str) -> GatewayData:
        _gateway_id_with_bang, gateway_id_without_bang, _node_type = self.prepare_gateway_id(gateway_id)
        # Filter for gateways from list_gateways that match the gateway_id
        gateways = self.list_gateways()
        for gateway in gateways:
            if gateway.node_hex_id.lower() == gateway_id_without_bang.lower():
                return gateway

        raise ValueError("Gateway not found")

    def reset_gateway_password(self, gateway_id: str, discord_user: Union[User, Member]) -> tuple[GatewayData, str]:
        _gateway_id_with_bang, gateway_id_without_bang, node_type = self.prepare_gateway_id(gateway_id)
        gateway = GatewayData(node_hex_id=gateway_id_without_bang, owner_id=discord_user.id, node_type=node_type)

        try:
            password = self.generate_password()
            self.emqx.update_user_password(self.authentication_id, gateway.user_string, password)
        except Exception:
            raise ValueError("Failed to reset password")

        return gateway, password
