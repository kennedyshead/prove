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

static Prove_Socket *_alloc_socket(int fd, int proto) {
    Prove_Socket *s = prove_alloc(sizeof(Prove_Socket));
    s->fd = fd;
    s->protocol = proto;
    return s;
}

static Prove_Address *_alloc_address(Prove_String *host, int64_t port) {
    Prove_Address *a = prove_alloc(sizeof(Prove_Address));
    a->host = host;
    a->port = port;
    return a;
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

static int _proto_to_sock_type(int proto) {
    return proto == PROVE_PROTO_UDP ? SOCK_DGRAM : SOCK_STREAM;
}

/* ── socket channel ──────────────────────────────────────────── */

Prove_Result *prove_network_socket_inputs(Prove_Address *addr, int64_t proto) {
    _ensure_wsa();
    if (!addr || !addr->host) return _socket_error("connect");

    int sock_type = _proto_to_sock_type((int)proto);
    int fd = socket(AF_INET, sock_type, 0);
    if (fd < 0) return _socket_error("socket");

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons((uint16_t)addr->port);

    /* Resolve hostname */
    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = sock_type;

    char host_buf[256];
    int64_t len = addr->host->length;
    if (len >= (int64_t)sizeof(host_buf)) len = (int64_t)sizeof(host_buf) - 1;
    memcpy(host_buf, addr->host->data, len);
    host_buf[len] = '\0';

    int gai = getaddrinfo(host_buf, NULL, &hints, &res);
    if (gai != 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("resolve");
    }
    memcpy(&sa.sin_addr,
           &((struct sockaddr_in *)res->ai_addr)->sin_addr,
           sizeof(sa.sin_addr));
    freeaddrinfo(res);

    if (connect(fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("connect");
    }

    return prove_result_ok(_alloc_socket(fd, (int)proto));
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

Prove_Result *prove_network_server_inputs(Prove_Address *addr, int64_t proto) {
    _ensure_wsa();
    if (!addr || !addr->host) return _socket_error("bind");

    int sock_type = _proto_to_sock_type((int)proto);
    int fd = socket(AF_INET, sock_type, 0);
    if (fd < 0) return _socket_error("socket");

    /* Allow address reuse */
    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, (const char *)&opt, sizeof(opt));

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons((uint16_t)addr->port);
    sa.sin_addr.s_addr = INADDR_ANY;

    if (bind(fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) {
        CLOSE_SOCKET(fd);
        return _socket_error("bind");
    }

    if (sock_type == SOCK_STREAM) {
        if (listen(fd, 128) < 0) {
            CLOSE_SOCKET(fd);
            return _socket_error("listen");
        }
    }

    return prove_result_ok(_alloc_socket(fd, (int)proto));
}

/* ── accept channel ──────────────────────────────────────────── */

Prove_Result *prove_network_accept_inputs(Prove_Socket *listener) {
    if (!listener || listener->fd < 0) return _socket_error("accept");

    struct sockaddr_in sa;
    socklen_t sa_len = sizeof(sa);
    int fd = accept(listener->fd, (struct sockaddr *)&sa, &sa_len);
    if (fd < 0) return _socket_error("accept");

    return prove_result_ok(_alloc_socket(fd, listener->protocol));
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

/* ── address channel ─────────────────────────────────────────── */

Prove_Result *prove_network_address_creates(Prove_String *source) {
    if (!source || source->length == 0) {
        return prove_result_err(prove_string_from_cstr("empty address string"));
    }

    /* Find the last ':' separator */
    int64_t colon = -1;
    for (int64_t i = source->length - 1; i >= 0; i--) {
        if (source->data[i] == ':') {
            colon = i;
            break;
        }
    }
    if (colon < 0) {
        return prove_result_err(prove_string_from_cstr("address must be host:port"));
    }

    /* Extract host */
    Prove_String *host = prove_string_slice(source, 0, colon);

    /* Parse port */
    char port_buf[16];
    int64_t port_len = source->length - colon - 1;
    if (port_len <= 0 || port_len >= (int64_t)sizeof(port_buf)) {
        return prove_result_err(prove_string_from_cstr("invalid port"));
    }
    memcpy(port_buf, source->data + colon + 1, port_len);
    port_buf[port_len] = '\0';
    char *endp;
    long port = strtol(port_buf, &endp, 10);
    if (*endp != '\0' || port < 1 || port > 65535) {
        return prove_result_err(prove_string_from_cstr("port must be 1-65535"));
    }

    return prove_result_ok(_alloc_address(host, (int64_t)port));
}

Prove_String *prove_network_address_reads(Prove_Address *addr) {
    if (!addr || !addr->host) return prove_string_from_cstr("");

    char port_str[16];
    int port_len = snprintf(port_str, sizeof(port_str), "%lld", (long long)addr->port);

    int64_t total = addr->host->length + 1 + port_len;
    Prove_String *s = prove_alloc(sizeof(Prove_String) + total);
    s->length = total;
    memcpy(s->data, addr->host->data, addr->host->length);
    s->data[addr->host->length] = ':';
    memcpy(s->data + addr->host->length + 1, port_str, port_len);

    return s;
}

bool prove_network_address_validates(Prove_String *source) {
    if (!source || source->length == 0) return false;

    int64_t colon = -1;
    for (int64_t i = source->length - 1; i >= 0; i--) {
        if (source->data[i] == ':') {
            colon = i;
            break;
        }
    }
    if (colon < 0 || colon == 0) return false;

    int64_t port_len = source->length - colon - 1;
    if (port_len <= 0 || port_len > 5) return false;

    char port_buf[16];
    memcpy(port_buf, source->data + colon + 1, port_len);
    port_buf[port_len] = '\0';
    char *endp;
    long port = strtol(port_buf, &endp, 10);
    return *endp == '\0' && port >= 1 && port <= 65535;
}

Prove_String *prove_network_host_reads(Prove_Address *addr) {
    if (!addr || !addr->host) return prove_string_from_cstr("");
    return addr->host;
}

int64_t prove_network_port_reads(Prove_Address *addr) {
    if (!addr) return 0;
    return addr->port;
}
