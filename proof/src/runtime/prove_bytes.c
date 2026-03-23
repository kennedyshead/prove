#include "prove_bytes.h"

/* ── Helpers ─────────────────────────────────────────────────── */

static Prove_ByteArray *_alloc_bytes(int64_t length) {
    size_t sz = sizeof(Prove_ByteArray) + (size_t)length;
    Prove_ByteArray *ba = prove_alloc(sz);
    ba->length = length;
    return ba;
}

/* ── constructors ────────────────────────────────────────────── */

Prove_ByteArray *prove_bytes_from_string(Prove_String *s) {
#ifndef PROVE_RELEASE
    int64_t len = s ? s->length : 0;
#else
    int64_t len = s->length;
#endif
    Prove_ByteArray *ba = _alloc_bytes(len);
    if (len > 0) memcpy(ba->data, s->data, (size_t)len);
    return ba;
}

/* ── byte channel ────────────────────────────────────────────── */

Prove_ByteArray *prove_bytes_create(Prove_List *values) {
#ifndef PROVE_RELEASE
    int64_t len = values ? values->length : 0;
#else
    int64_t len = values->length;
#endif
    Prove_ByteArray *ba = _alloc_bytes(len);
    for (int64_t i = 0; i < len; i++) {
        int64_t val = (int64_t)(intptr_t)prove_list_get(values, i);
        ba->data[i] = (uint8_t)(val & 0xFF);
    }
    return ba;
}

bool prove_bytes_validates(Prove_ByteArray *data) {
    return data != NULL && data->length > 0;
}

/* ── slice channel ───────────────────────────────────────────── */

Prove_ByteArray *prove_bytes_slice(Prove_ByteArray *data, int64_t start, int64_t length) {
#ifndef PROVE_RELEASE
    if (!data || start < 0 || length < 0 || start + length > data->length) {
#else
    if (start < 0 || length < 0 || start + length > data->length) {
#endif
        return _alloc_bytes(0);
    }
    Prove_ByteArray *result = _alloc_bytes(length);
    memcpy(result->data, data->data + start, (size_t)length);
    return result;
}

Prove_ByteArray *prove_bytes_concat(Prove_ByteArray *first, Prove_ByteArray *second) {
#ifndef PROVE_RELEASE
    int64_t len1 = first ? first->length : 0;
    int64_t len2 = second ? second->length : 0;
#else
    int64_t len1 = first->length;
    int64_t len2 = second->length;
#endif
    Prove_ByteArray *result = _alloc_bytes(len1 + len2);
    if (len1 > 0) memcpy(result->data, first->data, (size_t)len1);
    if (len2 > 0) memcpy(result->data + len1, second->data, (size_t)len2);
    return result;
}

/* ── hex channel ─────────────────────────────────────────────── */

static const char _hex_chars[] = "0123456789abcdef";

Prove_String *prove_bytes_hex_encode(Prove_ByteArray *data) {
    if (!data || data->length == 0) {
        return prove_string_from_cstr("");
    }
    int64_t hex_len = data->length * 2;
    Prove_String *result = (Prove_String *)prove_alloc(sizeof(Prove_String) + (size_t)hex_len + 1);
    result->length = hex_len;
    for (int64_t i = 0; i < data->length; i++) {
        result->data[i * 2] = _hex_chars[(data->data[i] >> 4) & 0xF];
        result->data[i * 2 + 1] = _hex_chars[data->data[i] & 0xF];
    }
    result->data[hex_len] = '\0';
    return result;
}

static int _hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

Prove_ByteArray *prove_bytes_hex_decode(Prove_String *source) {
    if (!source || source->length == 0 || source->length % 2 != 0) {
        return _alloc_bytes(0);
    }
    int64_t out_len = source->length / 2;
    Prove_ByteArray *result = _alloc_bytes(out_len);
    for (int64_t i = 0; i < out_len; i++) {
        int hi = _hex_val(source->data[i * 2]);
        int lo = _hex_val(source->data[i * 2 + 1]);
        if (hi < 0 || lo < 0) {
            result->data[i] = 0;
        } else {
            result->data[i] = (uint8_t)((hi << 4) | lo);
        }
    }
    return result;
}

bool prove_bytes_hex_validates(Prove_String *source) {
    if (!source || source->length == 0 || source->length % 2 != 0) {
        return false;
    }
    for (int64_t i = 0; i < source->length; i++) {
        if (_hex_val(source->data[i]) < 0) return false;
    }
    return true;
}

/* ── at channel ──────────────────────────────────────────────── */

int64_t prove_bytes_at(Prove_ByteArray *data, int64_t index) {
#ifndef PROVE_RELEASE
    if (!data || index < 0 || index >= data->length) {
        prove_panic("byte index out of bounds");
    }
#endif
    return (int64_t)data->data[index];
}

bool prove_bytes_at_validates(Prove_ByteArray *data, int64_t index) {
    return data != NULL && index >= 0 && index < data->length;
}
