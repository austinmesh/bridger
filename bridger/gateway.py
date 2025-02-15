import os
import re
import secrets
import string
from dataclasses import dataclass
from typing import Generator, Union

from discord import Member, User
from requests import HTTPError

from bridger.emqx import EMQXClient
from bridger.log import logger
from bridger.mqtt import MQTT_TOPIC

EMQX_API_KEY = os.getenv("EMQX_API_KEY")
EMQX_SECRET_KEY = os.getenv("EMQX_SECRET_KEY")
EMQX_URL = os.getenv("EMQX_URL")
PASSWORD_LENGTH = 10

emqx = EMQXClient(EMQX_URL, EMQX_API_KEY, EMQX_SECRET_KEY)


@dataclass
class GatewayData:
    node_hex_id: str
    owner_id: int

    @property
    def node_id(self) -> int:
        return int(self.node_hex_id_without_bang, 16)

    @property
    def color(self) -> str:
        return self.node_hex_id_without_bang[-6:]

    @property
    def node_hex_id_with_bang(self) -> str:
        if self.node_hex_id.startswith("!"):
            return self.node_hex_id
        return f"!{self.node_hex_id}"

    @property
    def node_hex_id_without_bang(self) -> str:
        return self.node_hex_id.lstrip("!")

    @property
    def user_string(self) -> str:
        return f"{self.owner_id}-{self.node_hex_id_without_bang}"


class GatewayError(Exception):
    def __init__(self, message: str, gateway: GatewayData):
        super().__init__(message)
        self.gateway = gateway


class GatewayManagerEMQX:
    authentication_id = "password_based:built_in_database"

    def __init__(self, emqx: EMQXClient):
        self.emqx = emqx

    @staticmethod
    def prepare_gateway_id(gateway_id: str) -> tuple[str, str]:
        # Prepend ! to gateway_id if it doesn't have it
        if not gateway_id.startswith("!"):
            gateway_id = f"!{gateway_id}"

        gateway_id_without_bang = gateway_id[1:]

        # Check if gateway_id is a 8 character hex number
        if len(gateway_id_without_bang) != 8:
            raise ValueError("Gateway ID must be 8 characters long")

        try:
            node_id = int(gateway_id_without_bang, 16)
        except ValueError:
            raise ValueError("Gateway ID must be a hex number")

        logger.debug(f"Gateway ID: {gateway_id_without_bang}")
        logger.debug(f"Node ID: {node_id}")

        return gateway_id, gateway_id_without_bang, node_id

    @staticmethod
    def generate_password() -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for i in range(PASSWORD_LENGTH))

    def list_gateways(self) -> Generator[GatewayData, None, None]:
        emqx_users = self.emqx.list_users(self.authentication_id)

        # Filter for users that match only our regex pattern
        user_regex = r"^([0-9]+)-([0-9a-fA-F]{8})$"
        emqx_users = [user for user in emqx_users["data"] if re.match(user_regex, user["user_id"])]
        gateways = []

        for user in emqx_users:
            node_hex_id = user["user_id"].split("-")[1]
            owner_id = int(user["user_id"].split("-")[0])
            gateways.append(GatewayData(node_hex_id=node_hex_id, owner_id=owner_id))

        return gateways

    def create_gateway_user(self, gateway_id: str, discord_user: Union[User, Member]) -> tuple[GatewayData, str]:
        gateway_id, gateway_id_without_bang, node_id = self.prepare_gateway_id(gateway_id)
        password = self.generate_password()

        topic_prefix = MQTT_TOPIC.removesuffix("/#")
        mqtt_rules = [{"action": "all", "topic": f"{topic_prefix}/LongFast/{gateway_id}", "permission": "allow"}]
        gateway = GatewayData(node_hex_id=gateway_id, owner_id=discord_user.id)
        rules = {"rules": mqtt_rules, "username": gateway.user_string}

        try:
            self.emqx.create_user(self.authentication_id, gateway.user_string, password)
            self.emqx.create_user_authorization_rules_built_in_database(gateway.user_string, rules)
        except HTTPError as e:
            if e.response.status_code == 400:
                raise GatewayError(f"Error creating gateway: {e}", gateway)
            else:
                raise GatewayError(f"Gateway already exists: {e}", gateway)
        return gateway, password

    def delete_gateway_user(self, gateway_id: str) -> bool:
        try:
            gateway = self.get_gateway(gateway_id)
            self.emqx.delete_user(self.authentication_id, gateway.user_string)
            self.emqx.delete_user_authorization_rules_built_in_database(gateway.user_string)
        except Exception:
            return False

        return True

    def get_gateway(self, gateway_id: str) -> GatewayData:
        gateway_id, gateway_id_without_bang, node_id = self.prepare_gateway_id(gateway_id)
        # Filter for gateways from list_gateways that match the gateway_id
        gateways = self.list_gateways()
        for gateway in gateways:
            if gateway.node_hex_id_without_bang == gateway_id_without_bang:
                return gateway

        raise ValueError("Gateway not found")

    def reset_gateway_password(self, gateway_id: str, discord_user: Union[User, Member]) -> tuple[GatewayData, str]:
        gateway_id, gateway_id_without_bang, node_id = self.prepare_gateway_id(gateway_id)
        gateway = GatewayData(node_hex_id=gateway_id, owner_id=discord_user.id)

        try:
            password = self.generate_password()
            self.emqx.update_user_password(self.authentication_id, gateway.user_string, password)
        except Exception:
            raise ValueError("Failed to reset password")

        return gateway, password
