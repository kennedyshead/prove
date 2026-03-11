#include "prove_network.h"
#include <string.h>
#include <stdlib.h>
#include <errno.h>

#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
  typedef int socklen_t;
  #define CLOSE_SOCKET closesocket
  static int _wsa_init_done = 0;
  static void _ensure_wsa(void) {
      if (!_wsa_init_done) {
          WSADATA wsa;
          WSAStartup(MAKEWORD(2, 2), &wsa);
          _wsa_init_done = 1;
      }
  }
#else
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <netdb.h>
  #include <unistd.h>
  #include <fcntl.h>
  #define CLOSE_SOCKET close
  static void _ensure_wsa(void) {}
#endif

/* ── Helpers ───────────────────────────────────────────────── */

static Prove_Socket *_alloc_socket(int fd) {
    Prove_Socket *s = prove_alloc(sizeof(Prove_Socket));
    s->fd = fd;
    return s;
}

static Prove_Result *_socket_error(const char *context) {
    const char *msg = strerror(errno);
    int ctx_len = (int)strlen(context);
    int msg_len = (int)strlen(msg);
    int total = ctx_len + 2 + msg_len;
    char *buf = prove_alloc(total + 1);
    memcpy(buf, context, ctx_len);
    buf[ctx_len] = ':';
    buf[ctx_len + 1] = ' ';
    memcpy(buf + ctx_len + 2, msg, msg_len);
    buf[total] = '\0';
    Prove_String *err_str = prove_string_from_cstr(buf);
    return prove_result_err(err_str);
}

static int _resolve_and_fill(Prove_String *host, int64_t port,
                             struct sockaddr_in *sa) {
    memset(sa, 0, sizeof(*sa));
    sa->sin_family = AF_INET;
    sa->sin_port = htons((uint16_t)port);

    char host_buf[256];
    int64_t len = host->length;
    if (len >= (int64_t)sizeof(host_buf)) len = (int64_t)sizeof(host_buf) - 1;
    memcpy(host_buf, host->data, len);
    host_buf[len] = '\0';

    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    int gai = getaddrinfo(host_buf, NULL, &hints, &res);
    if (gai != 0) return -1;

    memcpy(&sa->sin_addr,
           &((struct sockaddr_in *)res->ai_addr)->sin_addr,
           sizeof(sa->sin_addr));
    freeaddrinfo(res);
    return 0;
}

/* ── socket channel ──────────────────────────────────────────── */

Prove_Result *prove_network_socket_inputs(Prove_String *host, int64_t port) {
    _ensure_wsa();
    if (!host) return _socket_error("connect");

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return _socket_error("socket");

    struct sockaddr_in sa;
    if (_resolve_and_fill(host, port, &sa) < 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("resolve");
    }

    if (connect(fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("connect");
    }

    return prove_result_ok(_alloc_socket(fd));
}

void prove_network_socket_outputs(Prove_Socket *sock) {
    if (sock && sock->fd >= 0) {
        CLOSE_SOCKET(sock->fd);
        sock->fd = -1;
    }
}

bool prove_network_socket_validates(Prove_Socket *sock) {
    return sock != NULL && sock->fd >= 0;
}

/* ── server channel ──────────────────────────────────────────── */

Prove_Result *prove_network_server_inputs(Prove_String *host, int64_t port) {
    _ensure_wsa();
    if (!host) return _socket_error("bind");

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return _socket_error("socket");

    /* Allow address reuse */
    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, (const char *)&opt, sizeof(opt));

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons((uint16_t)port);
    sa.sin_addr.s_addr = INADDR_ANY;

    if (bind(fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("bind");
    }

    if (listen(fd, 128) < 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("listen");
    }

    return prove_result_ok(_alloc_socket(fd));
}

/* ── accept channel ──────────────────────────────────────────── */

Prove_Result *prove_network_accept_inputs(Prove_Socket *listener) {
    if (!listener || listener->fd < 0) return _socket_error("accept");

    struct sockaddr_in sa;
    socklen_t sa_len = sizeof(sa);
    int fd = accept(listener->fd, (struct sockaddr *)&sa, &sa_len);
    if (fd < 0) return _socket_error("accept");

    return prove_result_ok(_alloc_socket(fd));
}

/* ── message channel ─────────────────────────────────────────── */

Prove_Result *prove_network_message_inputs(Prove_Socket *sock, int64_t size) {
    if (!sock || sock->fd < 0) return _socket_error("recv");
    if (size <= 0) size = 4096;

    uint8_t *buf = prove_alloc(size);
    ssize_t n = recv(sock->fd, (char *)buf, (size_t)size, 0);
    if (n < 0) return _socket_error("recv");

    Prove_ByteArray *ba = prove_alloc(sizeof(Prove_ByteArray) + n);
    ba->length = n;
    if (n > 0) memcpy(ba->data, buf, n);

    return prove_result_ok(ba);
}

Prove_Result *prove_network_message_outputs(Prove_Socket *sock, Prove_ByteArray *data) {
    if (!sock || sock->fd < 0) return _socket_error("send");
    if (!data || data->length == 0) return prove_result_ok(NULL);

    ssize_t sent = send(sock->fd, (const char *)data->data, (size_t)data->length, 0);
    if (sent < 0) return _socket_error("send");

    return prove_result_ok(NULL);
}
