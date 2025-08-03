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
