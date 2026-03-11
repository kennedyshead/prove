---
title: Network - Prove Standard Library
description: TCP socket communication in the Prove standard library.
keywords: Prove Network, sockets, TCP, networking
---

# Network

**Module:** `Network` — TCP socket communication.

Network uses IO verbs for blocking socket operations. Pairs naturally with
async verbs (`listens`, `attached`) for non-blocking servers.

### Types

| Type | Kind | Description |
|------|------|-------------|
| `Socket` | binary | An open network socket (wraps OS file descriptor) |

### socket

Connect, close, and check sockets.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `socket(host String, port Integer) Result<Socket, Error>!` | Open a TCP connection to a remote host and port |
| `outputs` | `socket(connection Socket)` | Close a connection |
| `validates` | `socket(connection Socket)` | Check if a connection is open |

### server

Bind and listen on a port.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `server(host String, port Integer) Result<Socket, Error>!` | Bind and listen on a TCP port |

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

```prove
Network inputs socket server accept message, outputs socket message,
  validates socket, types Socket
Bytes types ByteArray

type Connection is Accept(listener Socket)
  | Exit

/// Accept and echo connections in a blocking loop.
streams echo_server(conn Connection)!
from
    Exit => conn
    Accept(listener) =>
        client as Socket = accept(listener)!
        data as ByteArray = message(client, 1024)!
        message(client, data)!
        socket(client)
```
