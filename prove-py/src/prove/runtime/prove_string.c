#include "prove_string.h"
#include <stdio.h>
#include <string.h>
#include <inttypes.h>

Prove_String *prove_string_new(const char *src, int64_t len) {
    Prove_String *s = (Prove_String *)prove_alloc(sizeof(Prove_String) + (size_t)len + 1);
    s->length = len;
    if (src && len > 0) {
        memcpy(s->data, src, (size_t)len);
    }
    s->data[len] = '\0';
    return s;
}

Prove_String *prove_string_from_cstr(const char *src) {
    if (!src) return prove_string_new("", 0);
    int64_t len = (int64_t)strlen(src);
    return prove_string_new(src, len);
}

Prove_String *prove_string_concat(Prove_String *a, Prove_String *b) {
    if (!a) return b;
    if (!b) return a;
    int64_t new_len = a->length + b->length;
    Prove_String *s = (Prove_String *)prove_alloc(sizeof(Prove_String) + (size_t)new_len + 1);
    s->length = new_len;
    memcpy(s->data, a->data, (size_t)a->length);
    memcpy(s->data + a->length, b->data, (size_t)b->length);
    s->data[new_len] = '\0';
    return s;
}

bool prove_string_eq(Prove_String *a, Prove_String *b) {
    if (a == b) return true;
    if (!a || !b) return false;
    if (a->length != b->length) return false;
    return memcmp(a->data, b->data, (size_t)a->length) == 0;
}

int64_t prove_string_len(Prove_String *s) {
    return s ? s->length : 0;
}

Prove_String *prove_string_from_int(int64_t val) {
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%" PRId64, val);
    return prove_string_new(buf, (int64_t)n);
}

Prove_String *prove_string_from_double(double val) {
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "%g", val);
    return prove_string_new(buf, (int64_t)n);
}

Prove_String *prove_string_from_bool(bool val) {
    return val ? prove_string_from_cstr("true") : prove_string_from_cstr("false");
}

Prove_String *prove_string_from_char(char val) {
    char buf[2] = {val, '\0'};
    return prove_string_new(buf, 1);
}

void prove_println(Prove_String *s) {
    if (s) {
        fwrite(s->data, 1, (size_t)s->length, stdout);
    }
    fputc('\n', stdout);
}

void prove_print(Prove_String *s) {
    if (s) {
        fwrite(s->data, 1, (size_t)s->length, stdout);
    }
}

Prove_String *prove_readln(void) {
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) {
        return prove_string_new("", 0);
    }
    /* Strip trailing newline */
    size_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') {
        buf[--len] = '\0';
    }
    if (len > 0 && buf[len - 1] == '\r') {
        buf[--len] = '\0';
    }
    return prove_string_new(buf, (int64_t)len);
}
