#ifndef PROVE_NETWORK_H
#define PROVE_NETWORK_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_bytes.h"

/* ── Types ───────────────────────────────────────────────────── */

/* Protocol: TCP=0, UDP=1 (matches algebraic variant order) */
#define PROVE_PROTO_TCP 0
#define PROVE_PROTO_UDP 1

typedef struct Prove_Socket {
    Prove_Header header;
    int fd;          /* OS file descriptor (-1 = closed) */
    int protocol;    /* PROVE_PROTO_TCP or PROVE_PROTO_UDP */
} Prove_Socket;

typedef struct Prove_Address {
    Prove_Header header;
    Prove_String *host;
    int64_t port;
} Prove_Address;

/* ── socket channel ──────────────────────────────────────────── */

Prove_Result *prove_network_socket_inputs(Prove_Address *addr, int64_t proto);
void          prove_network_socket_outputs(Prove_Socket *sock);
bool          prove_network_socket_validates(Prove_Socket *sock);

/* ── server channel ──────────────────────────────────────────── */

Prove_Result *prove_network_server_inputs(Prove_Address *addr, int64_t proto);

/* ── accept channel ──────────────────────────────────────────── */

Prove_Result *prove_network_accept_inputs(Prove_Socket *listener);

/* ── message channel ─────────────────────────────────────────── */

Prove_Result *prove_network_message_inputs(Prove_Socket *sock, int64_t size);
Prove_Result *prove_network_message_outputs(Prove_Socket *sock, Prove_ByteArray *data);

/* ── address channel ─────────────────────────────────────────── */

Prove_Result  *prove_network_address_creates(Prove_String *source);
Prove_String  *prove_network_address_reads(Prove_Address *addr);
bool           prove_network_address_validates(Prove_String *source);
Prove_String  *prove_network_host_reads(Prove_Address *addr);
int64_t        prove_network_port_reads(Prove_Address *addr);

#endif /* PROVE_NETWORK_H */
