import os
import re
import secrets
import string
from dataclasses import dataclass
from typing import Optional, Union

from discord import Member, User
from requests import HTTPError

from bridger.config import MQTT_TOPIC
from bridger.dataclasses import NodeMixin
from bridger.emqx import EMQXClient
from bridger.log import logger

EMQX_API_KEY = os.getenv("EMQX_API_KEY")
EMQX_SECRET_KEY = os.getenv("EMQX_SECRET_KEY")
EMQX_URL = os.getenv("EMQX_URL")
PASSWORD_LENGTH = 10

emqx = EMQXClient(EMQX_URL, EMQX_API_KEY, EMQX_SECRET_KEY)


@dataclass
class GatewayData(NodeMixin):
    node_id: int
    owner_id: int

    @property
    def user_string(self) -> str:
        return f"{self.owner_id}-{self.node_hex_id_without_bang}"


class GatewayError(Exception):
    def __init__(self, message: str, gateway: GatewayData, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.gateway = gateway
        self.status_code = status_code


class GatewayAlreadyExistsError(GatewayError):
    """The gateway is already registered in EMQX."""


class GatewayValidationError(GatewayError):
    """EMQX rejected the request as malformed."""


class GatewayBackendError(GatewayError):
    """EMQX failed for a reason that is not the caller's fault."""


class GatewayManagerEMQX:
    authentication_id = "password_based:built_in_database"

    def __init__(self, emqx: EMQXClient):
        self.emqx = emqx

    @staticmethod
    def prepare_gateway_id(gateway_id: str) -> tuple[str, str, int]:
        # Prepend ! to gateway_id if it doesn't have it
        if not gateway_id.startswith("!"):
            gateway_id = f"!{gateway_id}"

        gateway_id_without_bang = gateway_id[1:]

        # Check if gateway_id is a 8 character hex number
        if len(gateway_id_without_bang) != 8:
            raise ValueError("Gateway ID must be 8 characters long")

        try:
            node_id = int(gateway_id_without_bang, 16)
        except ValueError as e:
            raise ValueError("Gateway ID must be a hex number") from e

        logger.debug(f"Gateway ID: {gateway_id_without_bang}")
        logger.debug(f"Node ID: {node_id}")

        return gateway_id, gateway_id_without_bang, node_id

    @staticmethod
    def generate_password() -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for i in range(PASSWORD_LENGTH))

    def list_gateways(self) -> list[GatewayData]:
        emqx_users = self.emqx.list_users(self.authentication_id)

        # Filter for users that match only our regex pattern
        user_regex = r"^([0-9]+)-([0-9a-fA-F]{8})$"
        emqx_users = [user for user in emqx_users["data"] if re.match(user_regex, user["user_id"])]
        gateways = []

        for user in emqx_users:
            node_hex_id = user["user_id"].split("-")[1]
            owner_id = int(user["user_id"].split("-")[0])
            node_id = int(node_hex_id, 16)
            gateways.append(GatewayData(node_id=node_id, owner_id=owner_id))

        return gateways

    @staticmethod
    def create_gateway_rules_dict(gateway_id: str, username: str) -> dict:
        topic_prefix = MQTT_TOPIC.removesuffix("/#")
        mqtt_rules = [{"action": "all", "topic": f"{topic_prefix}/+/{gateway_id}", "permission": "allow"}]
        return {"rules": mqtt_rules, "username": username}

    @staticmethod
    def _map_http_error(error: HTTPError, gateway: GatewayData) -> GatewayError:
        """Turn an EMQX HTTPError into the specific GatewayError it represents.

        Everything that was not a 400 used to be reported as "gateway already exists", so an
        expired API key or a broker outage told the user their gateway was registered.
        """
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        code = None

        if response is not None:
            try:
                body = response.json()
            except Exception:
                body = None
            # A MagicMock response returns a truthy mock from .get(), so insist on a real dict.
            code = body.get("code") if isinstance(body, dict) else None

        if status_code == 409 or (status_code == 400 and code == "ALREADY_EXISTS"):
            return GatewayAlreadyExistsError(f"Gateway already exists: {error}", gateway, status_code=status_code)

        if status_code == 400:
            return GatewayValidationError(f"Error creating gateway: {error}", gateway, status_code=status_code)

        return GatewayBackendError(f"Error talking to EMQX: {error}", gateway, status_code=status_code)

    def create_gateway_user(self, gateway_id: str, discord_user: Union[User, Member]) -> tuple[GatewayData, str]:
        gateway_id, gateway_id_without_bang, node_id = self.prepare_gateway_id(gateway_id)
        password = self.generate_password()

        gateway = GatewayData(node_id=node_id, owner_id=discord_user.id)
        rules = self.create_gateway_rules_dict(gateway_id, gateway.user_string)

        try:
            self.emqx.create_user(self.authentication_id, gateway.user_string, password)
        except HTTPError as e:
            raise self._map_http_error(e, gateway) from e

        # Roll the user back if the rules do not land. Otherwise the account exists with no
        # ACL rules, the caller never receives the password, and every retry from here on
        # reports "already exists".
        try:
            self.emqx.create_user_authorization_rules_built_in_database(gateway.user_string, rules)
        except Exception as e:
            try:
                self.emqx.delete_user(self.authentication_id, gateway.user_string)
                logger.warning(f"Rolled back EMQX user {gateway.user_string} after its rules failed to apply")
            except Exception:
                logger.exception(f"Orphaned EMQX user {gateway.user_string}: rules failed and rollback failed too")

            status_code = getattr(getattr(e, "response", None), "status_code", None)
            raise GatewayBackendError(f"Failed to create authorization rules: {e}", gateway, status_code=status_code) from e

        return gateway, password

    def update_gateway_user_rules(self, gateway_id: str) -> bool:
        try:
            gateway_id, gateway_id_without_bang, node_id = self.prepare_gateway_id(gateway_id)
            gateway = self.get_gateway(gateway_id)
            self.emqx.delete_user_authorization_rules_built_in_database(gateway.user_string)
            rules = self.create_gateway_rules_dict(gateway_id, gateway.user_string)
            self.emqx.create_user_authorization_rules_built_in_database(gateway.user_string, rules)
            return True
        except Exception as e:
            logger.error(f"Failed to update gateway rules for {gateway_id}: {e}")
            return False

    def delete_gateway_user(self, gateway_id: str) -> bool:
        try:
            gateway = self.get_gateway(gateway_id)
            # Drop the rules before the user. The other order leaves the rules behind whenever
            # the second call fails, and the user is already gone by then so there is nothing
            # left to look them up by.
            self.emqx.delete_user_authorization_rules_built_in_database(gateway.user_string)
            self.emqx.delete_user(self.authentication_id, gateway.user_string)
        except Exception:
            logger.exception(f"Failed to delete gateway user for {gateway_id}")
            return False

        return True

    def get_gateway(self, gateway_id: str) -> GatewayData:
        gateway_id, gateway_id_without_bang, node_id = self.prepare_gateway_id(gateway_id)
        # Filter for gateways from list_gateways that match the gateway_id
        gateways = self.list_gateways()
        for gateway in gateways:
            if gateway.node_id == node_id:
                return gateway

        raise ValueError("Gateway not found")

    def reset_gateway_password(self, gateway_id: str) -> tuple[GatewayData, str]:
        # Resolve the real owner rather than assuming it is the caller. Building the username
        # from discord_user.id only worked because this is gated on the owner check; an admin
        # reset would have targeted a user string that does not exist.
        gateway = self.get_gateway(gateway_id)

        try:
            password = self.generate_password()
            self.emqx.update_user_password(self.authentication_id, gateway.user_string, password)
        except Exception as e:
            raise ValueError("Failed to reset password") from e

        return gateway, password
