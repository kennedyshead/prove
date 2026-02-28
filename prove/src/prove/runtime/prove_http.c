#include "prove_http.h"

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>

#define PROVE_HTTP_BUFSIZE 4096

Prove_Server prove_http_new_server(void) {
    return (Prove_Server){ .fd = -1, .port = 0 };
}

int prove_http_listen(Prove_Server *server, int64_t port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;

    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons((uint16_t)port);

    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        return -1;
    }

    if (listen(fd, 128) < 0) {
        close(fd);
        return -1;
    }

    server->fd = fd;
    server->port = (int)port;
    return 0;
}

/* ── Minimal HTTP/1.0 request parser ─────────────────────────── */

static Prove_Request _parse_request(const char *buf, ssize_t len) {
    Prove_Request req;
    req.method = prove_string_from_cstr("GET");
    req.path = prove_string_from_cstr("/");
    req.body = prove_string_from_cstr("");

    /* Parse request line: "METHOD /path HTTP/1.x\r\n" */
    const char *end = buf + len;
    const char *p = buf;

    /* Method */
    const char *sp = memchr(p, ' ', (size_t)(end - p));
    if (!sp) return req;
    prove_release(req.method);
    char method_buf[16] = {0};
    size_t mlen = (size_t)(sp - p);
    if (mlen >= sizeof(method_buf)) mlen = sizeof(method_buf) - 1;
    memcpy(method_buf, p, mlen);
    req.method = prove_string_from_cstr(method_buf);
    p = sp + 1;

    /* Path */
    sp = memchr(p, ' ', (size_t)(end - p));
    if (!sp) sp = memchr(p, '\r', (size_t)(end - p));
    if (!sp) sp = end;
    prove_release(req.path);
    char path_buf[1024] = {0};
    size_t plen = (size_t)(sp - p);
    if (plen >= sizeof(path_buf)) plen = sizeof(path_buf) - 1;
    memcpy(path_buf, p, plen);
    req.path = prove_string_from_cstr(path_buf);

    /* Body: after \r\n\r\n */
    const char *body_start = strstr(buf, "\r\n\r\n");
    if (body_start) {
        body_start += 4;
        if (body_start < end) {
            prove_release(req.body);
            size_t blen = (size_t)(end - body_start);
            char *body_buf = (char *)malloc(blen + 1);
            memcpy(body_buf, body_start, blen);
            body_buf[blen] = '\0';
            req.body = prove_string_from_cstr(body_buf);
            free(body_buf);
        }
    }

    return req;
}

/* ── Response serialization ──────────────────────────────────── */

static void _send_response(int client_fd, Prove_Response resp) {
    const char *status_text = "OK";
    if (resp.status == 201) status_text = "Created";
    else if (resp.status == 400) status_text = "Bad Request";
    else if (resp.status == 404) status_text = "Not Found";
    else if (resp.status == 500) status_text = "Internal Server Error";

    const char *body = resp.body ? resp.body->data : "";
    size_t body_len = resp.body ? (size_t)resp.body->length : 0;

    char header[512];
    int hlen = snprintf(header, sizeof(header),
        "HTTP/1.0 %d %s\r\n"
        "Content-Type: text/plain\r\n"
        "Content-Length: %zu\r\n"
        "Connection: close\r\n"
        "\r\n",
        (int)resp.status, status_text, body_len);

    write(client_fd, header, (size_t)hlen);
    if (body_len > 0) {
        write(client_fd, body, body_len);
    }
}

/* ── Accept loop ─────────────────────────────────────────────── */

void prove_http_serve(Prove_Server *server, Prove_HttpHandler handler) {
    if (server->fd < 0) {
        prove_panic("server not listening");
    }

    for (;;) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int client_fd = accept(server->fd,
            (struct sockaddr *)&client_addr, &client_len);
        if (client_fd < 0) continue;

        char buf[PROVE_HTTP_BUFSIZE];
        ssize_t n = read(client_fd, buf, sizeof(buf) - 1);
        if (n > 0) {
            buf[n] = '\0';
            Prove_Request req = _parse_request(buf, n);
            Prove_Response resp = handler(req);
            _send_response(client_fd, resp);
            prove_http_free_request(&req);
            if (resp.body) prove_release(resp.body);
        }

        close(client_fd);
    }
}

void prove_http_free_request(Prove_Request *req) {
    if (req->method) prove_release(req->method);
    if (req->path) prove_release(req->path);
    if (req->body) prove_release(req->body);
    req->method = NULL;
    req->path = NULL;
    req->body = NULL;
}
