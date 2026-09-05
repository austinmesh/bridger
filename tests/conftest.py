import sys

import pytest


@pytest.fixture(autouse=True)
def patch_mqtt_topic(monkeypatch):
    test_topic = "fake/2/e/#"
    monkeypatch.setenv("MQTT_TOPIC", test_topic)
    monkeypatch.setattr("bridger.config.MQTT_TOPIC", test_topic)

    # We need to patch each copy of MQTT_TOPIC in the bridger modules since they are actually copied when imported.
    for module_name, module in sys.modules.items():
        if module_name.startswith("bridger.") and hasattr(module, "MQTT_TOPIC"):
            monkeypatch.setattr(f"{module_name}.MQTT_TOPIC", test_topic)


@pytest.fixture(autouse=True)
def restore_handler_map():
    """Undo handler registrations made during a test.

    HANDLER_MAP is a module-level defaultdict that the @handler decorator appends to, so a
    test that registers a handler leaks it into every test that runs afterwards.
    """
    from bridger.mesh.handler_registry import HANDLER_MAP

    # The values are shared list objects that handler() mutates in place, so each one has to
    # be copied rather than just the outer mapping.
    saved = {message_type: list(handlers) for message_type, handlers in HANDLER_MAP.items()}

    yield HANDLER_MAP

    # Mutate in place rather than rebinding: bridger.mesh imported this object by reference.
    HANDLER_MAP.clear()
    HANDLER_MAP.update(saved)
