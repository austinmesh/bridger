"""
Virtual Node Configuration

Configuration settings specific to the virtual Meshtastic node
"""

import os

# Virtual Node Identity
VIRTUAL_NODE_ID = int(os.getenv("VIRTUAL_NODE_ID", "0x42524447"), 0)  # "BRDG" in hex
VIRTUAL_NODE_SHORT_NAME = os.getenv("VIRTUAL_NODE_SHORT_NAME", "BRDG")
VIRTUAL_NODE_LONG_NAME = os.getenv("VIRTUAL_NODE_LONG_NAME", "Bridger")
VIRTUAL_NODE_HW_MODEL = int(os.getenv("VIRTUAL_NODE_HW_MODEL", "255"))  # PRIVATE_HW
VIRTUAL_NODE_ROLE = int(os.getenv("VIRTUAL_NODE_ROLE", "3"))  # ROUTER role

# Network Configuration
VIRTUAL_NODE_CHANNEL = os.getenv("VIRTUAL_NODE_CHANNEL", "LongFast")
VIRTUAL_NODE_BROADCAST_INTERVAL_HOURS = int(os.getenv("VIRTUAL_NODE_BROADCAST_INTERVAL_HOURS", "2"))


# Topics
def get_virtual_node_topics(base_topic: str) -> dict:
    """Generate MQTT topics for virtual node communication"""
    base = base_topic.removesuffix("/#")
    node_hex = f"!{VIRTUAL_NODE_ID:08x}"

    return {
        "publish": f"{base}/{VIRTUAL_NODE_CHANNEL}/{node_hex}",
        "subscribe_direct": f"{base}/{VIRTUAL_NODE_CHANNEL}/{node_hex}",
        "subscribe_broadcast": f"{base}/{VIRTUAL_NODE_CHANNEL}/#",
    }
