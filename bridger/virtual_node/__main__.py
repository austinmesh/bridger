"""
Virtual Meshtastic Node Daemon

This daemon creates a virtual Meshtastic node that:
- Periodically broadcasts NodeInfo packets to advertise itself
- Listens for direct messages and responds appropriately
- Coordinates with Discord bot via MQTT topics
"""

import os
import threading
import time

import schedule
from paho.mqtt.client import CallbackAPIVersion

from bridger.config import MQTT_BROKER, MQTT_PASS, MQTT_PORT, MQTT_USER
from bridger.log import logger

from .config import VIRTUAL_NODE_BROADCAST_INTERVAL_HOURS, VIRTUAL_NODE_ID, VIRTUAL_NODE_LONG_NAME, VIRTUAL_NODE_SHORT_NAME
from .mqtt_client import VirtualNodeMQTT


def run_scheduler():
    """Run the scheduler in a separate thread"""
    while True:
        schedule.run_pending()
        time.sleep(1)


def main():
    """Main entry point for virtual node daemon"""
    try:
        # Create virtual node MQTT client
        client = VirtualNodeMQTT(CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.reconnect_delay_set(min_delay=5, max_delay=120)

        # Schedule periodic NodeInfo broadcasts
        schedule.every(VIRTUAL_NODE_BROADCAST_INTERVAL_HOURS).hours.do(client.send_nodeinfo)

        # Send initial NodeInfo packet immediately
        client.send_nodeinfo()

        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        logger.info(f"Virtual node {VIRTUAL_NODE_SHORT_NAME} (ID: {VIRTUAL_NODE_ID:08x}) started")
        logger.info(f"Broadcasting NodeInfo every {VIRTUAL_NODE_BROADCAST_INTERVAL_HOURS} hours")

        # Start MQTT loop
        client.loop_forever(retry_first_connection=True)

    except KeyboardInterrupt:
        logger.info("Shutting down virtual node daemon")
        client.disconnect()
        client.loop_stop()
        client = None
    except Exception as e:
        logger.error(f"Virtual node daemon error: {e}")


if __name__ == "__main__":
    main()
