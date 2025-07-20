"""
EMQX ExHook gRPC Service Daemon

Main entry point for the ExHook service that filters MQTT messages
based on client authentication.
"""

import signal
import sys

from bridger.exhook.config import config
from bridger.exhook.server import ExHookServer
from bridger.log import logger


def signal_handler(server: ExHookServer):
    """Handle shutdown signals gracefully"""

    def handler(signum, _):
        logger.info(f"Received signal {signum}, shutting down...")
        server.stop()
        sys.exit(0)

    return handler


def main():
    """Main entry point for ExHook daemon"""
    try:
        logger.info("Starting EMQX ExHook gRPC service")
        logger.info(f"Service: {config.service_name}")
        logger.info(f"Allowed users: {config.allowed_users}")
        logger.info(f"gRPC address: {config.get_grpc_address()}")

        # Create and start server
        server = ExHookServer()
        server.start()

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler(server))
        signal.signal(signal.SIGTERM, signal_handler(server))

        logger.info("ExHook service is ready to accept connections")

        # Wait for termination
        server.wait_for_termination()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"ExHook service error: {e}")
        sys.exit(1)
    finally:
        logger.info("ExHook service stopped")


if __name__ == "__main__":
    main()
