# Network Stdlib Module

## Overview

New `Network` module for network communication. TCP and UDP support.
Uses IO verbs for blocking operations, async verbs for non-blocking.

## Types

```prove
module Network
  /// An open network socket
  type Socket is
    handle Integer:[64]
    protocol Protocol

  /// Network protocol
  type Protocol is
    | TCP
    | UDP

  /// Network address (host and port)
  type Address is
    host String
    port Integer where 1..65535
```

## Verb Channels

### socket

```prove
/// Open a connection
inputs socket(address Address, protocol Protocol) Socket

/// Close a connection
outputs socket(socket Socket)

/// Check if a connection is open
validates socket(socket Socket)
```

### server

```prove
/// Bind and listen on an address
inputs server(address Address, protocol Protocol) Socket

/// Accept incoming connections (loop until exit)
streams server(socket Socket) Socket
from
    Error => _
    Connected(s) => handle(s)
```

### message

```prove
/// Read data from socket
inputs message(socket Socket, size Integer) ByteArray

/// Write data to socket
outputs message(socket Socket, data ByteArray)

/// Stream incoming messages (loop until exit)
streams message(socket Socket) ByteArray
from
    Closed => _
    Received(bytes) => process(bytes)
```

### address

```prove
/// Parse an address string ("host:port")
creates address(source String) Address

/// Format address as string
reads address(address Address) String

/// Check if an address is valid
validates address(address Address)
```

## Design Rationale

- `streams` verb for accept loops and message loops — natural fit
- `Protocol` as algebraic type — dispatch via `match`
- IO verbs for blocking socket operations
- Pairs naturally with async verbs (`listens`) for non-blocking servers
- Address parsing/validation via standard channel pattern
- Depends on `streams` verb (see io-improvement.md) and optionally `listens` (see async-plan.md)

## Finishing Requirements

- Ensure all relevant documentation is up to date.
