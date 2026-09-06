from bridger.cogs.mqtt import MQTTCog
from bridger.gateway import (
    GatewayAlreadyExistsError,
    GatewayBackendError,
    GatewayData,
    GatewayValidationError,
)

# The string requests builds for an HTTPError embeds the full request URL.
EMQX_URL = "http://emqx.internal:18083/api/v5/authentication/password_based:built_in_database/users"
RAW_HTTP_ERROR = f"500 Server Error: Internal Server Error for url: {EMQX_URL}"


def _gateway():
    return GatewayData(node_id=int("1a2b3c4d", 16), owner_id=1234567890)


class TestDescribeGatewayError:
    def test_already_exists_names_the_node(self):
        message = MQTTCog._describe_gateway_error(GatewayAlreadyExistsError("whatever", _gateway()))

        assert "1a2b3c4d" in message
        assert "already exists" in message.lower()

    def test_validation_error_does_not_leak_the_exception_text(self):
        error = GatewayValidationError(f"Error creating gateway: {RAW_HTTP_ERROR}", _gateway(), status_code=400)

        message = MQTTCog._describe_gateway_error(error)

        assert "1a2b3c4d" in message
        assert "emqx.internal" not in message
        assert "/api/v5/" not in message

    def test_backend_error_reports_the_status_but_not_the_url(self):
        error = GatewayBackendError(f"Error talking to EMQX: {RAW_HTTP_ERROR}", _gateway(), status_code=500)

        message = MQTTCog._describe_gateway_error(error)

        assert "1a2b3c4d" in message
        assert "HTTP 500" in message
        assert "emqx.internal" not in message
        assert "/api/v5/" not in message

    def test_backend_error_without_a_status_omits_it(self):
        error = GatewayBackendError("Could not reach EMQX: connection refused", _gateway())

        message = MQTTCog._describe_gateway_error(error)

        assert "1a2b3c4d" in message
        assert "HTTP" not in message
