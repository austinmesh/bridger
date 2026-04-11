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
def patch_meshcore_mqtt_topic(monkeypatch):
    test_topic = "fake/meshcore/#"
    monkeypatch.setenv("MESHCORE_MQTT_TOPIC", test_topic)
    monkeypatch.setattr("bridger.config.MESHCORE_MQTT_TOPIC", test_topic)

    # We need to patch each copy of MESHCORE_MQTT_TOPIC in the bridger modules since they are actually copied when imported.
    for module_name, module in sys.modules.items():
        if module_name.startswith("bridger.") and hasattr(module, "MESHCORE_MQTT_TOPIC"):
            monkeypatch.setattr(f"{module_name}.MESHCORE_MQTT_TOPIC", test_topic)


@pytest.fixture(autouse=True)
def patch_meshcore_iata(monkeypatch):
    test_iata = "AUS"
    monkeypatch.setenv("MESHCORE_IATA", test_iata)
    monkeypatch.setattr("bridger.config.MESHCORE_IATA", test_iata)

    for module_name, module in sys.modules.items():
        if module_name.startswith("bridger.") and hasattr(module, "MESHCORE_IATA"):
            monkeypatch.setattr(f"{module_name}.MESHCORE_IATA", test_iata)
