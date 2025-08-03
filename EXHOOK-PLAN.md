# EMQX ExHook gRPC Daemon Implementation Plan

## Overview

Implement a gRPC ExHook service for EMQX that filters MQTT messages to ensure only Bridger-originated packets are republished to mesh network subscribers while allowing all messages to be received for processing.

## Problem Statement

**Current Issue**:
- Virtual Bridger node publishes packets to MQTT
- These packets could be accidentally forwarded to other mesh devices via MQTT
- Need to prevent non-Bridger messages from being republished while allowing all messages to be received

**Solution**:
- EMQX ExHook gRPC service that intercepts `message.publish` events
- Filter messages based on client authentication/username
- Allow Bridger messages (`bridger` user) to set `allow_publish: true`
- Block other messages from republishing by setting `allow_publish: false`

## Architecture

### Components
1. **ExHook gRPC Server** - Python daemon implementing EMQX hooks
2. **Message Filter Logic** - Authentication-based filtering
3. **Configuration Management** - EMQX ExHook configuration
4. **Monitoring & Logging** - Service health and message filtering metrics

### Data Flow
```
MQTT Client Message → EMQX → ExHook gRPC Service → Filter Decision → EMQX → Subscribers
                                     ↓
                              Check client username
                                     ↓
                            bridger user: allow_publish=true
                            other users: allow_publish=false
```

## Implementation Plan

### Phase 1: Core gRPC Service Setup
1. **Project Structure**
   - Create `bridger/exhook/` package
   - Add gRPC dependencies to pyproject.toml
   - Set up protobuf generation workflow

2. **gRPC Infrastructure**
   - Copy `exhook.proto` from EMQX
   - Generate Python gRPC stubs
   - Create base gRPC server implementation

3. **Basic Hook Implementation**
   - Implement `HookProviderServicer`
   - Handle `OnProviderLoaded` for hook registration
   - Implement `OnMessagePublish` for message filtering

### Phase 2: Message Filtering Logic
1. **Authentication-Based Filtering**
   - Check message client username/clientid
   - Identify Bridger-originated messages
   - Apply appropriate `allow_publish` header

2. **Filter Rules**
   - Allow: Messages from `bridger` user (virtual node)
   - Allow: Messages from configured Bridger usernames
   - Block: All other messages from republishing
   - Log: All filtering decisions for monitoring

3. **Configuration Management**
   - Environment variables for allowed usernames
   - gRPC server configuration (host, port)
   - EMQX ExHook endpoint configuration

### Phase 3: Integration & Deployment
1. **EMQX Configuration**
   - Configure ExHook plugin in EMQX
   - Set gRPC endpoint for the service
   - Test hook registration and activation

2. **Service Deployment**
   - Create daemon entry point
   - Add service management (systemd, docker)
   - Health check and monitoring endpoints

3. **Testing & Validation**
   - Unit tests for filtering logic
   - Integration tests with EMQX
   - End-to-end testing with virtual node

### Phase 4: Production Features
1. **Monitoring & Observability**
   - Metrics collection (filtered vs allowed messages)
   - Structured logging for debugging
   - Health check endpoints

2. **Error Handling & Resilience**
   - gRPC connection handling
   - Fallback behavior on service failure
   - Circuit breaker patterns

3. **Security & Performance**
   - TLS support for gRPC
   - Rate limiting and performance optimization
   - Security hardening

## Technical Requirements

### Dependencies
- `grpcio` - gRPC Python library
- `grpcio-tools` - Protocol buffer compiler
- `protobuf` - Protocol buffer runtime
- Existing Bridger dependencies (logging, config)

### Configuration
```env
# ExHook gRPC Service
EXHOOK_GRPC_HOST=0.0.0.0
EXHOOK_GRPC_PORT=9000
EXHOOK_ALLOWED_USERS=bridger,virtual_bridger

# EMQX Configuration
EMQX_EXHOOK_URL=http://bridger-exhook:9000
```

### File Structure
```
bridger/exhook/
├── __init__.py
├── __main__.py              # Main daemon entry point
├── server.py                # gRPC server implementation
├── filter.py                # Message filtering logic
├── config.py                # Configuration management
├── proto/
│   ├── exhook.proto        # EMQX ExHook protocol definition
│   └── exhook_pb2.py       # Generated gRPC stubs
└── health.py               # Health check endpoints
```

## Key Implementation Details

### Message Filtering Logic
```python
def filter_message(self, message, client_info):
    """
    Determine if message should be allowed to publish

    Args:
        message: MQTT message from ExHook
        client_info: Client authentication info

    Returns:
        bool: True if message should be published, False otherwise
    """
    allowed_users = self.config.get_allowed_users()
    client_username = client_info.get('username', '')

    # Allow Bridger-originated messages
    if client_username in allowed_users:
        return True

    # Block all other messages from republishing
    return False
```

### gRPC Hook Implementation
```python
def OnMessagePublish(self, request, context):
    """Handle message publish events with filtering"""
    message = request.message
    client_info = request.client_info

    # Apply filtering logic
    allow_publish = self.filter_message(message, client_info)

    # Create response with allow_publish header
    headers = {"allow_publish": str(allow_publish).lower()}
    filtered_message = Message(
        **message.__dict__,
        headers=headers
    )

    # Return stop-and-return response with modified message
    return ValuedResponse(
        type=ValuedResponse.ResponsedType.STOP_AND_RETURN,
        message=filtered_message
    )
```

## Testing Strategy

### Unit Tests
- Message filtering logic with various client scenarios
- gRPC service method implementations
- Configuration parsing and validation

### Integration Tests
- EMQX ExHook registration and communication
- End-to-end message filtering with real EMQX instance
- Virtual node integration testing

### Performance Tests
- Message throughput under filtering load
- gRPC service latency measurements
- Memory and CPU usage profiling

## Deployment Considerations

### EMQX Configuration
```hocon
exhook {
  servers = [
    {
      name = "bridger_filter"
      url = "http://bridger-exhook:9000"
      request_timeout = "5s"
      failed_action = "ignore"
    }
  ]
}
```

### Docker Deployment
- Separate container for ExHook service
- Network connectivity to EMQX instance
- Configuration via environment variables
- Health check and restart policies

## Success Criteria

1. **Functional**
   - ✅ Bridger messages are published to mesh subscribers
   - ✅ Non-Bridger messages are blocked from republishing
   - ✅ All messages are still received for processing

2. **Performance**
   - ✅ Minimal latency impact on message processing
   - ✅ High message throughput support
   - ✅ Low resource utilization

3. **Reliability**
   - ✅ Service resilience and fault tolerance
   - ✅ Comprehensive monitoring and alerting
   - ✅ Graceful degradation on failures

## Future Enhancements

- **Advanced Filtering**: Topic-based filtering rules
- **Dynamic Configuration**: Runtime configuration updates
- **Analytics**: Message filtering analytics and reporting
- **Multi-tenant**: Support for multiple Bridger instances
- **Security**: Enhanced authentication and authorization
