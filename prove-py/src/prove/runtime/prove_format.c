#include "prove_format.h"
#include <inttypes.h>

/* ── Padding ─────────────────────────────────────────────────── */

Prove_String *prove_format_pad_left(Prove_String *s, int64_t width, char fill) {
    if (!s) s = prove_string_from_cstr("");
    if (s->length >= width) {
        /* Return a copy */
        return prove_string_new(s->data, s->length);
    }
    int64_t pad = width - s->length;
    int64_t total = width;
    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)total + 1);
    result->length = total;
    memset(result->data, fill, (size_t)pad);
    memcpy(result->data + pad, s->data, (size_t)s->length);
    result->data[total] = '\0';
    return result;
}

Prove_String *prove_format_pad_right(Prove_String *s, int64_t width, char fill) {
    if (!s) s = prove_string_from_cstr("");
    if (s->length >= width) {
        return prove_string_new(s->data, s->length);
    }
    int64_t pad = width - s->length;
    int64_t total = width;
    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)total + 1);
    result->length = total;
    memcpy(result->data, s->data, (size_t)s->length);
    memset(result->data + s->length, fill, (size_t)pad);
    result->data[total] = '\0';
    return result;
}

Prove_String *prove_format_center(Prove_String *s, int64_t width, char fill) {
    if (!s) s = prove_string_from_cstr("");
    if (s->length >= width) {
        return prove_string_new(s->data, s->length);
    }
    int64_t total_pad = width - s->length;
    int64_t left_pad = total_pad / 2;
    int64_t right_pad = total_pad - left_pad;
    int64_t total = width;
    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)total + 1);
    result->length = total;
    memset(result->data, fill, (size_t)left_pad);
    memcpy(result->data + left_pad, s->data, (size_t)s->length);
    memset(result->data + left_pad + s->length, fill, (size_t)right_pad);
    result->data[total] = '\0';
    return result;
}

/* ── Number formatting ───────────────────────────────────────── */

Prove_String *prove_format_hex(int64_t n) {
    char buf[32];
    int len;
    if (n < 0) {
        /* Avoid UB: -(INT64_MIN) overflows in signed; cast to unsigned first */
        uint64_t abs_val = (uint64_t)0 - (uint64_t)n;
        len = snprintf(buf, sizeof(buf), "-%" PRIx64, abs_val);
    } else {
        len = snprintf(buf, sizeof(buf), "%" PRIx64, (uint64_t)n);
    }
    return prove_string_new(buf, len);
}

Prove_String *prove_format_binary(int64_t n) {
    char buf[72];
    int pos = 0;
    uint64_t val;

    if (n < 0) {
        buf[pos++] = '-';
        val = (uint64_t)0 - (uint64_t)n;
    } else if (n == 0) {
        return prove_string_from_cstr("0");
    } else {
        val = (uint64_t)n;
    }

    /* Find highest set bit */
    char digits[64];
    int dlen = 0;
    while (val > 0) {
        digits[dlen++] = '0' + (char)(val & 1);
        val >>= 1;
    }

    /* Reverse */
    for (int i = dlen - 1; i >= 0; i--) {
        buf[pos++] = digits[i];
    }
    buf[pos] = '\0';
    return prove_string_new(buf, pos);
}

Prove_String *prove_format_octal(int64_t n) {
    char buf[32];
    int len;
    if (n < 0) {
        uint64_t abs_val = (uint64_t)0 - (uint64_t)n;
        len = snprintf(buf, sizeof(buf), "-%" PRIo64, abs_val);
    } else {
        len = snprintf(buf, sizeof(buf), "%" PRIo64, (uint64_t)n);
    }
    return prove_string_new(buf, len);
}

Prove_String *prove_format_decimal(double x, int64_t places) {
    char buf[64];
    if (places < 0) places = 0;
    if (places > 20) places = 20;
    int len = snprintf(buf, sizeof(buf), "%.*f", (int)places, x);
    return prove_string_new(buf, len);
}
