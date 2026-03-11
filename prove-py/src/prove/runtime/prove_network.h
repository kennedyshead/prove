#ifndef PROVE_NETWORK_H
#define PROVE_NETWORK_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_bytes.h"

/* ── Types ───────────────────────────────────────────────────── */

typedef struct Prove_Socket {
    Prove_Header header;
    int fd;          /* OS file descriptor (-1 = closed) */
} Prove_Socket;

/* ── socket channel ──────────────────────────────────────────── */

Prove_Result *prove_network_socket_inputs(Prove_String *host, int64_t port);
void          prove_network_socket_outputs(Prove_Socket *sock);
bool          prove_network_socket_validates(Prove_Socket *sock);

/* ── server channel ──────────────────────────────────────────── */

Prove_Result *prove_network_server_inputs(Prove_String *host, int64_t port);

/* ── accept channel ──────────────────────────────────────────── */

Prove_Result *prove_network_accept_inputs(Prove_Socket *listener);

/* ── message channel ─────────────────────────────────────────── */

Prove_Result *prove_network_message_inputs(Prove_Socket *sock, int64_t size);
Prove_Result *prove_network_message_outputs(Prove_Socket *sock, Prove_ByteArray *data);

#endif /* PROVE_NETWORK_H */
