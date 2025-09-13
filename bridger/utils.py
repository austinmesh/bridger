from bridger.config import MQTT_TOPIC


def should_ignore_pki_message(topic: str) -> bool:
    pki_topic = MQTT_TOPIC.removesuffix("/#") + "/PKI/"
    return topic.startswith(pki_topic)
