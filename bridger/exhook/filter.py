"""
Message Filtering Logic

Implements filtering logic for MQTT messages based on client authentication
to control which messages are allowed to be republished.
"""

from typing import Optional

from bridger.exhook.config import config
from bridger.log import logger


class MessageFilter:
    """Handles message filtering decisions for ExHook"""

    def __init__(self):
        self.config = config

    def should_allow_publish(self, message_headers: dict, client_username: Optional[str] = None) -> bool:
        """
        Determine if a message should be allowed to publish to subscribers

        Args:
            message_headers: Headers from the MQTT message
            client_username: Username of the client sending the message

        Returns:
            bool: True if message should be published, False otherwise
        """
        # Get username from message headers if not provided
        if client_username is None:
            client_username = message_headers.get("username", "")

        # Check if username is in allowed list
        is_allowed = self.config.is_user_allowed(client_username)

        # Log the filtering decision
        action = "ALLOW" if is_allowed else "BLOCK"
        logger.info(f"Message filter: {action} publish for user '{client_username}'")

        # Debug logging
        logger.debug(f"Message headers: {message_headers}")
        logger.debug(f"Allowed users: {self.config.allowed_users}")

        return is_allowed

    def create_filtered_headers(self, original_headers: dict, allow_publish: bool) -> dict:
        """
        Create new headers with allow_publish flag set

        Args:
            original_headers: Original message headers
            allow_publish: Whether to allow publishing

        Returns:
            dict: Updated headers with allow_publish flag
        """
        # Copy original headers
        new_headers = dict(original_headers)

        # Set the allow_publish header
        new_headers["allow_publish"] = "true" if allow_publish else "false"

        return new_headers
