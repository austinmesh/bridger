"""
Tests for shared message processing utilities
"""

import os
import re
from unittest.mock import patch

import pytest

from bridger.shared.message_processing import MessageMatchers, NodeFormatter, TopicManager


class TestMessageMatchers:
    """Test message matching utilities"""

    def test_get_test_message_matchers_default(self):
        """Test default test message matchers"""
        with patch.dict(os.environ, {}, clear=True):
            matchers = MessageMatchers.get_test_message_matchers()

            assert len(matchers) == 2
            assert matchers[0] is None  # Match all disabled by default
            assert isinstance(matchers[1], re.Pattern)

    def test_get_test_message_matchers_match_all_enabled(self):
        """Test test message matchers with match all enabled"""
        with patch.dict(os.environ, {"TEST_MESSAGE_MATCH_ALL": "true"}):
            matchers = MessageMatchers.get_test_message_matchers()

            assert len(matchers) == 2
            assert isinstance(matchers[0], re.Pattern)  # Match all enabled
            assert isinstance(matchers[1], re.Pattern)

    def test_matches_test_patterns_bang_message(self):
        """Test matching messages that start with !"""
        result = MessageMatchers.matches_test_patterns("!test command")
        assert result is True

    def test_matches_test_patterns_regular_message(self):
        """Test non-matching regular messages"""
        result = MessageMatchers.matches_test_patterns("regular message")
        assert result is False

    def test_matches_test_patterns_with_custom_patterns(self):
        """Test matching with custom patterns"""
        custom_patterns = [re.compile(r"^custom.*")]

        assert MessageMatchers.matches_test_patterns("custom message", custom_patterns) is True
        assert MessageMatchers.matches_test_patterns("other message", custom_patterns) is False

    def test_matches_test_patterns_with_match_all(self):
        """Test matching with match all enabled"""
        with patch.dict(os.environ, {"TEST_MESSAGE_MATCH_ALL": "true"}):
            matchers = MessageMatchers.get_test_message_matchers()

            assert MessageMatchers.matches_test_patterns("any message", matchers) is True
            assert MessageMatchers.matches_test_patterns("!command", matchers) is True


class TestNodeFormatter:
    """Test node name formatting utilities"""

    def test_format_node_name_no_info(self):
        """Test formatting when no node info is provided"""
        result = NodeFormatter.format_node_name(12345)
        assert result == "**12345**"

    def test_format_node_name_empty_info(self):
        """Test formatting with empty node info"""
        result = NodeFormatter.format_node_name(12345, {})
        assert result == "**12345**"

    def test_format_node_name_with_short_and_long(self):
        """Test formatting with both short and long names"""
        node_info = {"short_name": "TEST", "long_name": "Test Node"}
        result = NodeFormatter.format_node_name(12345, node_info)
        assert result == "**TEST** - Test Node"

    def test_format_node_name_with_only_short(self):
        """Test formatting with only short name"""
        node_info = {"short_name": "TEST"}
        result = NodeFormatter.format_node_name(12345, node_info)
        assert result == "**12345**"

    def test_format_node_name_with_only_long(self):
        """Test formatting with only long name"""
        node_info = {"long_name": "Test Node"}
        result = NodeFormatter.format_node_name(12345, node_info)
        assert result == "**12345**"


class TestTopicManager:
    """Test MQTT topic management utilities"""

    def test_get_channel_topic(self):
        """Test getting channel topic"""
        base_topic = "egr/home/2/e/#"
        channel = "LongFast"
        result = TopicManager.get_channel_topic(base_topic, channel)
        assert result == "egr/home/2/e/LongFast/#"

    def test_get_channel_topic_no_wildcard(self):
        """Test getting channel topic with base that doesn't end in wildcard"""
        base_topic = "egr/home/2/e"
        channel = "LongFast"
        result = TopicManager.get_channel_topic(base_topic, channel)
        assert result == "egr/home/2/e/LongFast/#"

    def test_get_node_direct_topic_with_bang(self):
        """Test getting direct node topic with ! prefix"""
        base_topic = "egr/home/2/e/#"
        channel = "LongFast"
        node_hex_id = "!42524447"
        result = TopicManager.get_node_direct_topic(base_topic, channel, node_hex_id)
        assert result == "egr/home/2/e/LongFast/!42524447"

    def test_get_node_direct_topic_without_bang(self):
        """Test getting direct node topic without ! prefix"""
        base_topic = "egr/home/2/e/#"
        channel = "LongFast"
        node_hex_id = "42524447"
        result = TopicManager.get_node_direct_topic(base_topic, channel, node_hex_id)
        assert result == "egr/home/2/e/LongFast/!42524447"

    def test_get_multiple_topics_no_additional_nodes(self):
        """Test getting multiple topics with no additional nodes"""
        base_topic = "egr/home/2/e/#"
        channel = "LongFast"
        topics = TopicManager.get_multiple_topics(base_topic, channel)

        assert len(topics) == 1
        assert topics[0] == "egr/home/2/e/LongFast/#"

    def test_get_multiple_topics_with_additional_nodes(self):
        """Test getting multiple topics with additional nodes"""
        base_topic = "egr/home/2/e/#"
        channel = "LongFast"
        additional_nodes = ["42524447", "!12345678"]
        topics = TopicManager.get_multiple_topics(base_topic, channel, additional_nodes)

        assert len(topics) == 3
        assert topics[0] == "egr/home/2/e/LongFast/#"
        assert topics[1] == "egr/home/2/e/LongFast/!42524447"
        assert topics[2] == "egr/home/2/e/LongFast/!12345678"
