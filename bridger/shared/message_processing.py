"""
Shared Message Processing Utilities

Common utilities for processing and filtering Meshtastic messages
that can be used by both the Discord bot and virtual node daemon.
"""

import os
import re
from typing import Any, Dict, List, Optional


class MessageMatchers:
    """Message pattern matching utilities"""

    @staticmethod
    def get_test_message_matchers() -> List[Optional[re.Pattern]]:
        """Get regex patterns for test message matching"""
        return [
            (
                re.compile(r"^.*$", flags=re.IGNORECASE)
                if os.getenv("TEST_MESSAGE_MATCH_ALL", "false").lower() == "true"
                else None
            ),
            re.compile(r"^\!\b.+$", flags=re.IGNORECASE),
        ]

    @staticmethod
    def matches_test_patterns(text: str, patterns: List[Optional[re.Pattern]] = None) -> bool:
        """Check if text matches any of the test message patterns"""
        if patterns is None:
            patterns = MessageMatchers.get_test_message_matchers()

        return any(pattern and pattern.match(text) for pattern in patterns if pattern)


class NodeFormatter:
    """Node name formatting utilities"""

    @staticmethod
    def format_node_name(node_id: int, node_info: Optional[Dict[str, Any]] = None) -> str:
        """Format a consistent node name based on available info"""
        if not node_info:
            return f"**{node_id}**"

        short = node_info.get("short_name")
        long = node_info.get("long_name")

        if short and long:
            return f"**{short}** - {long}"
        else:
            return f"**{node_id}**"


class TopicManager:
    """MQTT topic management utilities"""

    @staticmethod
    def get_channel_topic(base_topic: str, channel: str) -> str:
        """Get the full topic for a specific channel"""
        base = base_topic.removesuffix("/#")
        return f"{base}/{channel}/#"

    @staticmethod
    def get_node_direct_topic(base_topic: str, channel: str, node_hex_id: str) -> str:
        """Get the topic for direct messages to a specific node"""
        base = base_topic.removesuffix("/#")
        if not node_hex_id.startswith("!"):
            node_hex_id = f"!{node_hex_id}"
        return f"{base}/{channel}/{node_hex_id}"

    @staticmethod
    def get_multiple_topics(base_topic: str, channel: str, additional_nodes: Optional[List[str]] = None) -> List[str]:
        """Get multiple topics for subscribing to both channel and direct messages"""
        topics = [TopicManager.get_channel_topic(base_topic, channel)]

        if additional_nodes:
            for node_hex_id in additional_nodes:
                topics.append(TopicManager.get_node_direct_topic(base_topic, channel, node_hex_id))

        return topics
