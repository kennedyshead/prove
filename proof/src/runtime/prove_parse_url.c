#include "prove_parse.h"
#include "prove_bytes.h"
#include "prove_text.h"
#include <string.h>
#include <stdlib.h>

/* ── URL parsing ────────────────────────────────────────────── */

static Prove_Url *_url_alloc(void) {
    Prove_Url *u = prove_alloc(sizeof(Prove_Url));
    u->port = -1;
    u->query = NULL;
    u->fragment = NULL;
    return u;
}

Prove_Url *prove_parse_url(Prove_String *raw) {
    const char *s = raw->data;
    int64_t len = raw->length;

    /* Find scheme: look for "://" */
    const char *scheme_end = strstr(s, "://");
    if (!scheme_end || scheme_end == s) {
        /* Invalid URL — return with empty fields */
        Prove_Url *u = _url_alloc();
        u->scheme = prove_string_from_cstr("");
        u->host = prove_string_from_cstr("");
        u->path = prove_string_from_cstr("");
        return u;
    }

    Prove_Url *u = _url_alloc();
    u->scheme = prove_string_new(s, (int64_t)(scheme_end - s));

    const char *authority = scheme_end + 3;
    const char *end = s + len;

    /* Find end of authority (first / ? or #) */
    const char *auth_end = authority;
    while (auth_end < end && *auth_end != '/' && *auth_end != '?' && *auth_end != '#') {
        auth_end++;
    }

    /* Parse host and optional port from authority */
    const char *colon = NULL;
    for (const char *p = authority; p < auth_end; p++) {
        if (*p == ':') colon = p;
    }
    if (colon) {
        u->host = prove_string_new(authority, (int64_t)(colon - authority));
        long port = strtol(colon + 1, NULL, 10);
        if (port > 0 && port <= 65535) {
            u->port = (int64_t)port;
        }
    } else {
        u->host = prove_string_new(authority, (int64_t)(auth_end - authority));
    }

    /* Parse path */
    const char *path_start = auth_end;
    const char *path_end = path_start;
    while (path_end < end && *path_end != '?' && *path_end != '#') {
        path_end++;
    }
    if (path_end > path_start) {
        u->path = prove_string_new(path_start, (int64_t)(path_end - path_start));
    } else {
        u->path = prove_string_from_cstr("/");
    }

    /* Parse query */
    if (path_end < end && *path_end == '?') {
        const char *q_start = path_end + 1;
        const char *q_end = q_start;
        while (q_end < end && *q_end != '#') q_end++;
        u->query = prove_string_new(q_start, (int64_t)(q_end - q_start));
        path_end = q_end;
    }

    /* Parse fragment */
    if (path_end < end && *path_end == '#') {
        const char *f_start = path_end + 1;
        u->fragment = prove_string_new(f_start, (int64_t)(end - f_start));
    }

    return u;
}

Prove_Url *prove_parse_url_create(Prove_String *scheme, Prove_String *host,
                                   Prove_String *path) {
    Prove_Url *u = _url_alloc();
    u->scheme = scheme;
    u->host = host;
    u->path = path;
    return u;
}

bool prove_parse_url_validates(Prove_String *raw) {
    const char *s = raw->data;
    int64_t len = raw->length;
    if (len < 4) return false; /* minimum: "x://" */

    /* Must have :// */
    const char *sep = strstr(s, "://");
    if (!sep || sep == s) return false;

    /* Must have at least one char after :// */
    if (sep + 3 >= s + len) return false;

    return true;
}

Prove_Url *prove_parse_url_transform(Prove_Url *source, Prove_Table *params) {
    Prove_Url *u = _url_alloc();
    u->scheme = source->scheme;
    u->host = source->host;
    u->port = source->port;
    u->path = source->path;
    u->fragment = source->fragment;

    /* Build query string from existing + new params */
    Prove_List *keys = prove_table_keys(params);
    int64_t nkeys = prove_list_len(keys);
    if (nkeys == 0) {
        u->query = source->query;
        return u;
    }

    /* Build query with O(n) Builder instead of O(n²) concat */
    Prove_Builder *b = prove_text_builder();

    /* Keep existing query */
    if (source->query && source->query->length > 0) {
        b = prove_text_write(b, source->query);
    }

    for (int64_t i = 0; i < nkeys; i++) {
        Prove_String *key = (Prove_String *)prove_list_get(keys, i);
        Prove_Option opt = prove_table_get(key, params);
        if (opt.tag == 0) continue;
        Prove_Value *val = (Prove_Value *)opt.value;

        Prove_String *val_str;
        if (val->tag == PROVE_VALUE_TEXT) {
            val_str = val->text;
        } else if (val->tag == PROVE_VALUE_NUMBER) {
            val_str = prove_string_from_int(val->number);
        } else {
            val_str = prove_string_from_cstr("");
        }

        if (prove_text_builder_length(b) > 0) {
            b = prove_text_write_char(b, '&');
        }
        b = prove_text_write(b, key);
        b = prove_text_write_char(b, '=');
        b = prove_text_write(b, val_str);
    }

    u->query = prove_text_build(b);
    free(b);

    return u;
}

/* ── URL field accessors ────────────────────────────────────── */

Prove_String *prove_parse_url_host_reads(Prove_Url *url) {
    if (!url || !url->host) return prove_string_from_cstr("");
    return url->host;
}

int64_t prove_parse_url_port_reads(Prove_Url *url) {
    if (!url) return -1;
    return url->port;
}

/* ── Base64 ─────────────────────────────────────────────────── */

static const char _b64_enc[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static const int8_t _b64_dec[256] = {
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
    52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-2,-1,-1,
    -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
    15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
    -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
    41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
    -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
};

Prove_String *prove_parse_base64_encode(Prove_ByteArray *data) {
    int64_t in_len = data->length;
    int64_t out_len = 4 * ((in_len + 2) / 3);
    char *buf = malloc((size_t)out_len + 1);
    if (!buf) prove_panic("out of memory");

    int64_t i = 0, j = 0;
    while (i < in_len) {
        int64_t block_start = i;
        uint32_t a = (uint32_t)data->data[i++];
        uint32_t b = (i < in_len) ? (uint32_t)data->data[i++] : 0;
        uint32_t c = (i < in_len) ? (uint32_t)data->data[i++] : 0;
        int count = (int)(i - block_start);
        uint32_t triple = (a << 16) | (b << 8) | c;

        buf[j++] = _b64_enc[(triple >> 18) & 0x3F];
        buf[j++] = _b64_enc[(triple >> 12) & 0x3F];
        buf[j++] = (count >= 2) ? _b64_enc[(triple >> 6) & 0x3F] : '=';
        buf[j++] = (count >= 3) ? _b64_enc[triple & 0x3F] : '=';
    }
    buf[j] = '\0';
    Prove_String *result = prove_string_new(buf, j);
    free(buf);
    return result;
}

Prove_ByteArray *prove_parse_base64_decode(Prove_String *encoded) {
    const char *s = encoded->data;
    int64_t len = encoded->length;

    /* Skip trailing whitespace/padding for length calc */
    int64_t data_len = len;
    while (data_len > 0 && (s[data_len-1] == '=' || s[data_len-1] == '\n' || s[data_len-1] == '\r')) {
        data_len--;
    }

    int64_t out_len = (data_len * 3) / 4;
    Prove_ByteArray *result = prove_alloc(sizeof(Prove_ByteArray) + out_len);
    result->length = 0;

    int64_t i = 0, j = 0;
    while (i < len) {
        int8_t a = _b64_dec[(uint8_t)s[i++]];
        int8_t b = (i < len) ? _b64_dec[(uint8_t)s[i++]] : -1;
        int8_t c = (i < len) ? _b64_dec[(uint8_t)s[i++]] : -2;
        int8_t d = (i < len) ? _b64_dec[(uint8_t)s[i++]] : -2;

        if (a < 0 || b < 0) break;

        result->data[j++] = (uint8_t)((a << 2) | (b >> 4));
        if (c >= 0) result->data[j++] = (uint8_t)((b << 4) | (c >> 2));
        if (d >= 0) result->data[j++] = (uint8_t)((c << 6) | d);
    }

    result->length = j;
    return result;
}

bool prove_parse_base64_validates(Prove_String *encoded) {
    const char *s = encoded->data;
    int64_t len = encoded->length;
    if (len == 0) return false;
    if (len % 4 != 0) return false;

    for (int64_t i = 0; i < len; i++) {
        char c = s[i];
        if (c == '=') {
            /* Padding only at end */
            if (i < len - 2) return false;
        } else if (_b64_dec[(uint8_t)c] < 0) {
            return false;
        }
    }
    return true;
}
