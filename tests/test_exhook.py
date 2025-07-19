"""
Tests for EMQX ExHook functionality
"""

import os
from unittest.mock import patch

import pytest

from bridger.exhook.config import ExHookConfig
from bridger.exhook.filter import MessageFilter
from bridger.exhook.proto import exhook_pb2
from bridger.exhook.server import BridgerExHookServicer


class TestExHookConfig:
    """Test ExHook configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        config = ExHookConfig()
        assert config.grpc_host == "0.0.0.0"
        assert config.grpc_port == 9000
        assert config.allowed_users == ["bridger"]
        assert config.service_name == "bridger_filter"

    def test_env_config(self):
        """Test configuration from environment variables"""
        with patch.dict(
            os.environ,
            {
                "EXHOOK_GRPC_HOST": "127.0.0.1",
                "EXHOOK_GRPC_PORT": "8080",
                "EXHOOK_ALLOWED_USERS": "bridger,virtual_bridger,test_user",
                "EXHOOK_SERVICE_NAME": "test_service",
            },
        ):
            config = ExHookConfig()
            assert config.grpc_host == "127.0.0.1"
            assert config.grpc_port == 8080
            assert config.allowed_users == ["bridger", "virtual_bridger", "test_user"]
            assert config.service_name == "test_service"

    def test_is_user_allowed(self):
        """Test user allowlist checking"""
        config = ExHookConfig()
        assert config.is_user_allowed("bridger") is True
        assert config.is_user_allowed("other_user") is False
        assert config.is_user_allowed("") is False

    def test_get_grpc_address(self):
        """Test gRPC address formatting"""
        config = ExHookConfig()
        assert config.get_grpc_address() == "0.0.0.0:9000"


class TestMessageFilter:
    """Test message filtering logic"""

    def test_filter_allowed_user(self):
        """Test filtering allows messages from allowed users"""
        filter_instance = MessageFilter()

        headers = {"username": "bridger", "protocol": "mqtt"}
        result = filter_instance.should_allow_publish(headers)

        assert result is True

    def test_filter_blocked_user(self):
        """Test filtering blocks messages from non-allowed users"""
        filter_instance = MessageFilter()

        headers = {"username": "random_user", "protocol": "mqtt"}
        result = filter_instance.should_allow_publish(headers)

        assert result is False

    def test_filter_no_username(self):
        """Test filtering when no username is provided"""
        filter_instance = MessageFilter()

        headers = {"protocol": "mqtt"}
        result = filter_instance.should_allow_publish(headers)

        assert result is False

    def test_filter_explicit_username(self):
        """Test filtering with explicitly provided username"""
        filter_instance = MessageFilter()

        headers = {"protocol": "mqtt"}
        result = filter_instance.should_allow_publish(headers, client_username="bridger")

        assert result is True

    def test_create_filtered_headers_allow(self):
        """Test creating headers with allow_publish=true"""
        filter_instance = MessageFilter()

        original = {"username": "bridger", "protocol": "mqtt"}
        result = filter_instance.create_filtered_headers(original, allow_publish=True)

        expected = {"username": "bridger", "protocol": "mqtt", "allow_publish": "true"}
        assert result == expected

    def test_create_filtered_headers_block(self):
        """Test creating headers with allow_publish=false"""
        filter_instance = MessageFilter()

        original = {"username": "other", "protocol": "mqtt"}
        result = filter_instance.create_filtered_headers(original, allow_publish=False)

        expected = {"username": "other", "protocol": "mqtt", "allow_publish": "false"}
        assert result == expected


class TestBridgerExHookServicer:
    """Test ExHook gRPC servicer"""

    def test_provider_loaded(self):
        """Test OnProviderLoaded response"""
        servicer = BridgerExHookServicer()

        # Create a mock request
        broker_info = exhook_pb2.BrokerInfo(version="5.9.0", sysdescr="EMQX Test")
        meta = exhook_pb2.RequestMeta(node="emqx@127.0.0.1")
        request = exhook_pb2.ProviderLoadedRequest(broker=broker_info, meta=meta)

        response = servicer.OnProviderLoaded(request, None)

        # Check response
        assert len(response.hooks) == 1
        assert response.hooks[0].name == "message.publish"
        assert response.hooks[0].topics == []

    def test_provider_unloaded(self):
        """Test OnProviderUnloaded response"""
        servicer = BridgerExHookServicer()

        meta = exhook_pb2.RequestMeta(node="emqx@127.0.0.1")
        request = exhook_pb2.ProviderUnloadedRequest(meta=meta)

        response = servicer.OnProviderUnloaded(request, None)

        assert isinstance(response, exhook_pb2.EmptySuccess)

    def test_message_publish_allowed_user(self):
        """Test OnMessagePublish allows messages from allowed users"""
        servicer = BridgerExHookServicer()

        # Create message from allowed user
        message = exhook_pb2.Message(
            node="emqx@127.0.0.1",
            id="msg_123",
            qos=1,
            topic="test/topic",
            payload=b"test message",
            timestamp=1234567890,
            headers={"username": "bridger", "protocol": "mqtt"},
        )
        setattr(message, "from", "bridger_client")

        meta = exhook_pb2.RequestMeta(node="emqx@127.0.0.1")
        request = exhook_pb2.MessagePublishRequest(message=message, meta=meta)

        response = servicer.OnMessagePublish(request, None)

        # Check response
        assert response.type == exhook_pb2.ValuedResponse.ResponsedType.STOP_AND_RETURN
        assert response.message.headers["allow_publish"] == "true"
        assert response.message.topic == "test/topic"

    def test_message_publish_blocked_user(self):
        """Test OnMessagePublish blocks messages from non-allowed users"""
        servicer = BridgerExHookServicer()

        # Create message from non-allowed user
        message = exhook_pb2.Message(
            node="emqx@127.0.0.1",
            id="msg_456",
            qos=1,
            topic="test/topic",
            payload=b"test message",
            timestamp=1234567890,
            headers={"username": "random_user", "protocol": "mqtt"},
        )
        setattr(message, "from", "random_client")

        meta = exhook_pb2.RequestMeta(node="emqx@127.0.0.1")
        request = exhook_pb2.MessagePublishRequest(message=message, meta=meta)

        response = servicer.OnMessagePublish(request, None)

        # Check response
        assert response.type == exhook_pb2.ValuedResponse.ResponsedType.STOP_AND_RETURN
        assert response.message.headers["allow_publish"] == "false"
        assert response.message.topic == "test/topic"

    def test_message_publish_preserves_message_data(self):
        """Test OnMessagePublish preserves all message data"""
        servicer = BridgerExHookServicer()

        original_payload = b"important test data"
        message = exhook_pb2.Message(
            node="emqx@test.com",
            id="preserve_test",
            qos=2,
            topic="important/data",
            payload=original_payload,
            timestamp=9876543210,
            headers={"username": "bridger", "protocol": "mqtt", "custom": "value"},
        )
        setattr(message, "from", "important_client")

        meta = exhook_pb2.RequestMeta(node="emqx@test.com")
        request = exhook_pb2.MessagePublishRequest(message=message, meta=meta)

        response = servicer.OnMessagePublish(request, None)

        # Check all original data is preserved
        result_msg = response.message
        assert result_msg.node == "emqx@test.com"
        assert result_msg.id == "preserve_test"
        assert result_msg.qos == 2
        assert result_msg.topic == "important/data"
        assert result_msg.payload == original_payload
        assert result_msg.timestamp == 9876543210
        assert getattr(result_msg, "from") == "important_client"

        # Check headers are updated properly
        assert result_msg.headers["username"] == "bridger"
        assert result_msg.headers["protocol"] == "mqtt"
        assert result_msg.headers["custom"] == "value"
        assert result_msg.headers["allow_publish"] == "true"

    def test_client_authenticate_continues(self):
        """Test OnClientAuthenticate returns CONTINUE"""
        servicer = BridgerExHookServicer()

        client_info = exhook_pb2.ClientInfo(clientid="test_client", username="test_user")
        meta = exhook_pb2.RequestMeta(node="emqx@127.0.0.1")
        request = exhook_pb2.ClientAuthenticateRequest(clientinfo=client_info, result=True, meta=meta)

        response = servicer.OnClientAuthenticate(request, None)

        assert response.type == exhook_pb2.ValuedResponse.ResponsedType.CONTINUE

    def test_client_authorize_continues(self):
        """Test OnClientAuthorize returns CONTINUE"""
        servicer = BridgerExHookServicer()

        client_info = exhook_pb2.ClientInfo(clientid="test_client", username="test_user")
        meta = exhook_pb2.RequestMeta(node="emqx@127.0.0.1")
        request = exhook_pb2.ClientAuthorizeRequest(
            clientinfo=client_info,
            type=exhook_pb2.ClientAuthorizeRequest.AuthorizeReqType.PUBLISH,
            topic="test/topic",
            result=True,
            meta=meta,
        )

        response = servicer.OnClientAuthorize(request, None)

        assert response.type == exhook_pb2.ValuedResponse.ResponsedType.CONTINUE
