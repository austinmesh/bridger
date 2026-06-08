from bridger.config import MQTT_TOPIC


def should_ignore_pki_message(topic: str) -> bool:
    pki_topic = MQTT_TOPIC.removesuffix("/#") + "/PKI/"
    return topic.startswith(pki_topic)


def format_meshcore_path(path: list[str]) -> str:
    """Format MeshCore path hashes into human-readable form.

    Example: ["a1b2c3d4", "e5f6a7b8", "c9d0e1f2"] -> "A1 -> E5 -> C9"
    """
    if not path:
        return "Direct"
    return " -> ".join(h[:2].upper() for h in path)
