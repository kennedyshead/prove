---
title: Network - Prove Standard Library
description: TCP socket communication in the Prove standard library — clients, servers, and accept loops with streams.
keywords: Prove Network, sockets, TCP, networking, streams, accept loop
---

# Network

**Module:** `Network` — TCP socket communication.

`Network` provides blocking IO verbs for TCP connections. Servers pair naturally with the
[`streams`](../async) verb for accept loops.

---

## Types

| Type | Kind | Description |
|------|------|-------------|
| `Socket` | binary | An open network socket (wraps an OS file descriptor) |

---

## Channels

### socket

Open, close, and check connections.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `socket(host String, port Integer) Result<Socket, Error>!` | Open a TCP connection to a remote host |
| `outputs` | `socket(connection Socket)` | Close a connection |
| `validates` | `socket(connection Socket)` | True if a connection is still open |

### server

Bind and start listening on a port.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `server(host String, port Integer) Result<Socket, Error>!` | Bind and listen on a TCP port |

### accept

Accept incoming connections on a listening socket.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `accept(listener Socket) Result<Socket, Error>!` | Accept the next incoming TCP connection |

### message

Read and write data.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `message(connection Socket, size Integer) Result<ByteArray, Error>!` | Read up to `size` bytes from a socket |
| `outputs` | `message(connection Socket, data ByteArray) Result<Unit, Error>!` | Write bytes to a socket |

---

## Import syntax

Import only what your module uses. Verbs are declared per channel:

```prove
// Client: connect and exchange messages
Network inputs socket message, outputs socket message
Network types Socket
Bytes creates hex, reads hex
Bytes types ByteArray

// Server: bind, accept, and echo
Network inputs server accept message, outputs socket message
Network types Socket
Bytes reads hex
Bytes types ByteArray
Log detached info
```

`Network types Socket` is required whenever you hold a `Socket` value. `Bytes` is needed
to construct and inspect `ByteArray` data — `creates hex` decodes a hex string into bytes,
`reads hex` encodes bytes back to a hex string.

---

## Client

A TCP client connects to a host, sends a request, and reads the response. Bytes are passed
as `ByteArray` — use `creates hex` to decode a hex string into bytes to send, and
`reads hex` to encode the response back to a printable string.

```prove
module Main
  narrative: """Demonstrates Network module: TCP client connecting to a server."""
  System outputs console
  Network inputs socket message, outputs socket message
  Network types Socket
  Bytes creates hex, reads hex
  Bytes types ByteArray

main() Result<Unit, Error>!
from
    connection as Socket = socket("127.0.0.1", 9000)!
    console("connected to 127.0.0.1:9000")
    data as ByteArray = hex("68656c6c6f")
    message(connection, data)!
    response as ByteArray = message(connection, 1024)!
    reply as String = hex(response)
    console(f"server replied: {reply}")
    socket(connection)
```

`hex("68656c6c6f")` calls `creates hex` — hex-decoding the string `"hello"` into its
byte representation. `hex(response)` calls `reads hex` — encoding the received bytes as
a printable hex string.

---

## Server with `streams`

A TCP server uses the [`streams`](../async) verb for a
blocking accept loop. The first parameter is an algebraic type; each iteration dispatches
on its variant. The loop continues until the `Exit` arm is matched.

```prove
module Main
  narrative: """Demonstrates Network module: TCP echo server using streams."""
  System outputs console
  Network inputs server accept message, outputs socket message
  Network types Socket
  Bytes reads hex
  Bytes types ByteArray
  Log detached info

  type Connection is Accept(listener Socket)
    | Exit

/// Accept and echo connections in a blocking loop.
streams serve(conn Connection)!
from
    Exit => conn
    Accept(listener) =>
        client as Socket = accept(listener)!
        data as ByteArray = message(client, 1024)!
        info(f"received: {hex(data)}")&
        message(client, data)!
        info("echoed response")&
        socket(client)

main() Result<Unit, Error>!
from
    listener as Socket = server("0.0.0.0", 9000)!
    console("echo server on :9000")
    serve(Accept(listener))
```

The `streams` loop here:

1. Calls `accept(listener)` to get the next client connection
2. Reads up to 1024 bytes
3. Fires a `detached` log call via `&` — non-blocking, does not stall the loop
4. Echoes the data back to the client
5. Closes the client connection with `outputs socket`
6. Returns to the top of the loop for the next `Accept`

The `Exit` arm is never reached in normal server operation but is required — the compiler
enforces exhaustive match coverage on `streams` bodies
([E371](../diagnostics.md#e371-non-exhaustive-match-blocking-io-in-async-body)).

The `!` on `streams serve(conn Connection)!` marks the function as failable; any `!`
call inside the body that fails propagates out, terminating the loop.

---

## Error handling

All network operations are failable (`!`). Use `!` at each call site to propagate, or
match explicitly to handle individual failure cases:

```prove
Network inputs socket, outputs socket
Network types Socket

inputs safe_connect(host String, port Integer) Option<Socket>
from
    match socket(host, port)
        Ok(conn) => Some(conn)
        Err(_)   => None
```
