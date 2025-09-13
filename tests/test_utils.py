from unittest.mock import patch

from bridger.utils import should_ignore_pki_message


class TestShouldIgnorePkiMessage:

    @patch("bridger.utils.MQTT_TOPIC", "msh/US/2/e/LongFast/#")
    def test_should_ignore_pki_message_true(self):
        pki_topic = "msh/US/2/e/LongFast/PKI/some/subtopic"
        assert should_ignore_pki_message(pki_topic) is True

    @patch("bridger.utils.MQTT_TOPIC", "msh/US/2/e/LongFast/#")
    def test_should_ignore_pki_message_false_regular_topic(self):
        regular_topic = "msh/US/2/e/LongFast/MQTT/some/subtopic"
        assert should_ignore_pki_message(regular_topic) is False

    @patch("bridger.utils.MQTT_TOPIC", "msh/US/2/e/LongFast/#")
    def test_should_ignore_pki_message_false_different_path(self):
        different_topic = "msh/US/2/e/DifferentChannel/PKI/subtopic"
        assert should_ignore_pki_message(different_topic) is False

    @patch("bridger.utils.MQTT_TOPIC", "msh/US/2/e/LongFast/#")
    def test_should_ignore_pki_message_false_partial_match(self):
        partial_topic = "msh/US/2/e/LongFast/PKI"
        assert should_ignore_pki_message(partial_topic) is False

    @patch("bridger.utils.MQTT_TOPIC", "simple/topic/#")
    def test_should_ignore_pki_message_simple_topic(self):
        pki_topic = "simple/topic/PKI/test"
        regular_topic = "simple/topic/regular/test"

        assert should_ignore_pki_message(pki_topic) is True
        assert should_ignore_pki_message(regular_topic) is False

    @patch("bridger.utils.MQTT_TOPIC", "no/wildcard")
    def test_should_ignore_pki_message_no_wildcard(self):
        pki_topic = "no/wildcard/PKI/test"
        regular_topic = "no/wildcard/regular/test"

        assert should_ignore_pki_message(pki_topic) is True
        assert should_ignore_pki_message(regular_topic) is False
