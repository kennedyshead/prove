#ifndef PROVE_HTTP_H
#define PROVE_HTTP_H

#include "prove_runtime.h"
#include "prove_string.h"

/* ── HTTP types ─────────────────────────────────────────────── */

typedef struct {
    int fd;
    int port;
} Prove_Server;

typedef struct {
    Prove_String *method;
    Prove_String *path;
    Prove_String *body;
} Prove_Request;

typedef struct {
    int64_t status;
    Prove_String *body;
} Prove_Response;

/* ── Server lifecycle ───────────────────────────────────────── */

Prove_Server prove_http_new_server(void);
int prove_http_listen(Prove_Server *server, int64_t port);

/* ── Response constructors ──────────────────────────────────── */

static inline Prove_Response prove_http_ok(Prove_String *body) {
    return (Prove_Response){ .status = 200, .body = body };
}

static inline Prove_Response prove_http_created(Prove_String *body) {
    return (Prove_Response){ .status = 201, .body = body };
}

static inline Prove_Response prove_http_not_found(void) {
    return (Prove_Response){
        .status = 404,
        .body = prove_string_from_cstr("not found"),
    };
}

static inline Prove_Response prove_http_bad_request(Prove_String *msg) {
    return (Prove_Response){ .status = 400, .body = msg };
}

/* ── Request handling ───────────────────────────────────────── */

/* Type of user-defined handler: takes a request, returns a response. */
typedef Prove_Response (*Prove_HttpHandler)(Prove_Request req);

/* Accept loop: blocks, calls handler for each incoming request. */
void prove_http_serve(Prove_Server *server, Prove_HttpHandler handler);

/* Free a request's owned strings. */
void prove_http_free_request(Prove_Request *req);

#endif /* PROVE_HTTP_H */
