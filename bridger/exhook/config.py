"""
ExHook Service Configuration

Configuration settings for the EMQX ExHook gRPC service
"""

import os
from typing import List


class ExHookConfig:
    """Configuration for ExHook gRPC service"""

    def __init__(self):
        # gRPC Server Configuration
        self.grpc_host = os.getenv("EXHOOK_GRPC_HOST", "0.0.0.0")
        self.grpc_port = int(os.getenv("EXHOOK_GRPC_PORT", "9000"))

        # Message Filtering Configuration
        self.allowed_users = self._parse_allowed_users()

        # Service Configuration
        self.service_name = os.getenv("EXHOOK_SERVICE_NAME", "bridger_filter")
        self.log_level = os.getenv("EXHOOK_LOG_LEVEL", "INFO")

    def _parse_allowed_users(self) -> List[str]:
        """Parse allowed usernames from environment variable"""
        allowed_users_str = os.getenv("EXHOOK_ALLOWED_USERS", "bridger")
        return [user.strip() for user in allowed_users_str.split(",") if user.strip()]

    def is_user_allowed(self, username: str) -> bool:
        """Check if a username is allowed to publish"""
        return username in self.allowed_users

    def get_grpc_address(self) -> str:
        """Get the full gRPC server address"""
        return f"{self.grpc_host}:{self.grpc_port}"


# Global configuration instance
config = ExHookConfig()
