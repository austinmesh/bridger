"""
EMQX ExHook gRPC Server Implementation

Implements the gRPC server for EMQX ExHook that filters MQTT messages
based on client authentication.
"""

from concurrent import futures

import grpc

from bridger.exhook.config import config
from bridger.exhook.filter import MessageFilter
from bridger.exhook.proto import exhook_pb2, exhook_pb2_grpc
from bridger.log import logger


class BridgerExHookServicer(exhook_pb2_grpc.HookProviderServicer):
    """gRPC servicer implementing EMQX ExHook interface"""

    def __init__(self):
        self.filter = MessageFilter()
        logger.info(f"ExHook servicer initialized with allowed users: {config.allowed_users}")

    def OnProviderLoaded(self, request, context):
        """
        Called when the ExHook provider is loaded by EMQX
        Returns the list of hooks this service wants to handle
        """
        logger.info("ExHook provider loaded")
        logger.debug(f"Broker info: {request.broker.version} - {request.broker.sysdescr}")

        # Register for message.publish hook only
        hooks = [exhook_pb2.HookSpec(name="message.publish", topics=[])]  # Empty means all topics

        response = exhook_pb2.LoadedResponse(hooks=hooks)
        logger.info("Registered for message.publish hook")
        return response

    def OnProviderUnloaded(self, request, context):
        """Called when the ExHook provider is unloaded"""
        logger.info("ExHook provider unloaded")
        return exhook_pb2.EmptySuccess()

    def OnMessagePublish(self, request, context):
        """
        Handle message publish events - this is where we filter messages
        """
        message = request.message

        # Extract client information
        client_username = message.headers.get("username", "")
        topic = message.topic

        logger.debug(f"Processing message publish: topic='{topic}', user='{client_username}'")

        # Apply filtering logic
        allow_publish = self.filter.should_allow_publish(
            message_headers=dict(message.headers), client_username=client_username
        )

        # Create updated headers with allow_publish flag
        updated_headers = self.filter.create_filtered_headers(dict(message.headers), allow_publish)

        # Create new message with updated headers
        # Note: we need to use getattr for 'from' since it's a Python keyword
        filtered_message = exhook_pb2.Message(
            node=message.node,
            id=message.id,
            qos=message.qos,
            topic=message.topic,
            payload=message.payload,
            timestamp=message.timestamp,
            headers=updated_headers,
        )
        # Set the 'from' field using setattr since it's a Python keyword
        setattr(filtered_message, "from", getattr(message, "from"))

        # Return response that stops the chain and uses our filtered message
        response = exhook_pb2.ValuedResponse(
            type=exhook_pb2.ValuedResponse.ResponsedType.STOP_AND_RETURN, message=filtered_message
        )

        return response

    # Default implementations for other hooks (no-op)
    def OnClientConnect(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnClientConnack(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnClientConnected(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnClientDisconnected(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnClientAuthenticate(self, request, context):
        # Return continue to let EMQX handle authentication
        return exhook_pb2.ValuedResponse(type=exhook_pb2.ValuedResponse.ResponsedType.CONTINUE)

    def OnClientAuthorize(self, request, context):
        # Return continue to let EMQX handle authorization
        return exhook_pb2.ValuedResponse(type=exhook_pb2.ValuedResponse.ResponsedType.CONTINUE)

    def OnClientSubscribe(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnClientUnsubscribe(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionCreated(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionSubscribed(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionUnsubscribed(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionResumed(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionDiscarded(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionTakenover(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnSessionTerminated(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnMessageDelivered(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnMessageDropped(self, request, context):
        return exhook_pb2.EmptySuccess()

    def OnMessageAcked(self, request, context):
        return exhook_pb2.EmptySuccess()


class ExHookServer:
    """gRPC server for ExHook service"""

    def __init__(self):
        self.server = None
        self.servicer = BridgerExHookServicer()

    def start(self):
        """Start the gRPC server"""
        try:
            # Create gRPC server
            self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

            # Add servicer to server
            exhook_pb2_grpc.add_HookProviderServicer_to_server(self.servicer, self.server)

            # Bind to address
            address = config.get_grpc_address()
            self.server.add_insecure_port(address)

            # Start server
            self.server.start()
            logger.info(f"ExHook gRPC server started on {address}")

            return self.server

        except Exception as e:
            logger.error(f"Failed to start ExHook server: {e}")
            raise

    def stop(self, grace_period=5):
        """Stop the gRPC server"""
        if self.server:
            logger.info("Stopping ExHook gRPC server")
            self.server.stop(grace_period)
            self.server = None

    def wait_for_termination(self):
        """Wait for server termination"""
        if self.server:
            self.server.wait_for_termination()
