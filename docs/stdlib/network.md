---
title: Network - Prove Standard Library
description: TCP and UDP socket communication in the Prove standard library.
keywords: Prove Network, sockets, TCP, UDP, networking
---

# Network

**Module:** `Network` — TCP and UDP socket communication.

Network uses IO verbs for blocking socket operations. Pairs naturally with
async verbs (`listens`, `attached`) for non-blocking servers.

### Types

| Type | Kind | Description |
|------|------|-------------|
| `Socket` | binary | An open network socket (wraps OS file descriptor) |
| `Protocol` | algebraic | `Tcp` or `Udp` |
| `Address` | binary | Network address (host and port) |

### socket

Connect, close, and check sockets.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `socket(address Address, protocol Protocol) Result<Socket, Error>!` | Open a connection to a remote address |
| `outputs` | `socket(connection Socket)` | Close a connection |
| `validates` | `socket(connection Socket)` | Check if a connection is open |

### server

Bind and listen on an address.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `server(address Address, protocol Protocol) Result<Socket, Error>!` | Bind and listen on an address |

### accept

Accept incoming connections.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `accept(listener Socket) Result<Socket, Error>!` | Accept an incoming connection on a listening socket |

### message

Read and write data on a socket.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `message(connection Socket, size Integer) Result<ByteArray, Error>!` | Read data from a socket |
| `outputs` | `message(connection Socket, data ByteArray) Result<Unit, Error>!` | Write data to a socket |

### address

Parse, format, and validate network addresses.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `address(source String) Result<Address, Error>!` | Parse an address string (`"host:port"`) |
| `reads` | `address(location Address) String` | Format address as `"host:port"` |
| `validates` | `address(source String)` | Check if an address string is valid |
| `reads` | `host(location Address) String` | Read the host component |
| `reads` | `port(location Address) Integer` | Read the port component |

```prove
Network inputs socket server accept message, outputs socket message,
  validates socket address, creates address, reads address host port,
  types Socket Protocol Address
Bytes types ByteArray

outputs echo_server(port Integer)!
from
    addr as Address = Network.address(f"0.0.0.0:{port}")!
    listener as Socket = Network.server(addr, Tcp)!
    client as Socket = Network.accept(listener)!
    data as ByteArray = Network.message(client, 1024)!
    Network.message(client, data)!
    Network.socket(client)
    Network.socket(listener)
```
