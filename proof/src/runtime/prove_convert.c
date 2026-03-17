#include "prove_convert.h"
#include <errno.h>
#include <limits.h>

/* ── String → Integer ────────────────────────────────────────── */

Prove_Result prove_convert_integer_str(Prove_String *s) {
    if (!s || s->length == 0) {
        return prove_result_err(prove_string_from_cstr("empty string"));
    }

    /* Null-terminate for strtol */
    char buf[64];
    int64_t len = s->length < 63 ? s->length : 63;
    memcpy(buf, s->data, (size_t)len);
    buf[len] = '\0';

    char *endptr;
    errno = 0;
    long long val = strtoll(buf, &endptr, 10);

    if (errno == ERANGE) {
        return prove_result_err(prove_string_from_cstr("integer overflow"));
    }
    if (endptr == buf || *endptr != '\0') {
        return prove_result_err(prove_string_from_cstr("invalid integer"));
    }

    return prove_result_ok_int((int64_t)val);
}

/* ── Float → Integer ─────────────────────────────────────────── */

int64_t prove_convert_integer_float(double x) {
    return (int64_t)x;
}

/* ── String → Float ──────────────────────────────────────────── */

Prove_Result prove_convert_float_str(Prove_String *s) {
    if (!s || s->length == 0) {
        return prove_result_err(prove_string_from_cstr("empty string"));
    }

    char buf[128];
    int64_t len = s->length < 127 ? s->length : 127;
    memcpy(buf, s->data, (size_t)len);
    buf[len] = '\0';

    char *endptr;
    errno = 0;
    double val = strtod(buf, &endptr);

    if (errno == ERANGE) {
        return prove_result_err(prove_string_from_cstr("float overflow"));
    }
    if (endptr == buf || *endptr != '\0') {
        return prove_result_err(prove_string_from_cstr("invalid float"));
    }

    return prove_result_ok_double(val);
}

/* ── Integer → Float ─────────────────────────────────────────── */

double prove_convert_float_int(int64_t n) {
    return (double)n;
}

/* ── To String ───────────────────────────────────────────────── */

Prove_String *prove_convert_string_int(int64_t n) {
    return prove_string_from_int(n);
}

Prove_String *prove_convert_string_float(double x) {
    return prove_string_from_double(x);
}

Prove_String *prove_convert_string_bool(bool b) {
    return prove_string_from_bool(b);
}

/* ── Character ↔ Integer ─────────────────────────────────────── */

int64_t prove_convert_code(char c) {
    return (int64_t)(unsigned char)c;
}

char prove_convert_character(int64_t n) {
    if (n < 0 || n > 127) {
        prove_panic("Convert.character: code point out of ASCII range");
    }
    return (char)n;
}
