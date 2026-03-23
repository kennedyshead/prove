#ifndef PROVE_BYTES_H
#define PROVE_BYTES_H

#include "prove_runtime.h"
#include "prove_list.h"
#include "prove_string.h"

/* ── ByteArray ───────────────────────────────────────────────── */

typedef struct Prove_ByteArray {
    Prove_Header header;
    int64_t length;
    uint8_t data[];  /* flexible array member */
} Prove_ByteArray;

/* ── constructors ────────────────────────────────────────────── */

Prove_ByteArray *prove_bytes_from_string(Prove_String *s);
Prove_String    *prove_bytes_to_string(Prove_ByteArray *ba);
Prove_ByteArray *prove_bytes_create(Prove_List *values);
bool             prove_bytes_validates(Prove_ByteArray *data);

/* ── slice channel ───────────────────────────────────────────── */

Prove_ByteArray *prove_bytes_slice(Prove_ByteArray *data, int64_t start, int64_t length);
Prove_ByteArray *prove_bytes_concat(Prove_ByteArray *first, Prove_ByteArray *second);

/* ── hex channel ─────────────────────────────────────────────── */

Prove_String    *prove_bytes_hex_encode(Prove_ByteArray *data);
Prove_ByteArray *prove_bytes_hex_decode(Prove_String *source);
bool             prove_bytes_hex_validates(Prove_String *source);

/* ── at channel ──────────────────────────────────────────────── */

int64_t prove_bytes_at(Prove_ByteArray *data, int64_t index);
bool    prove_bytes_at_validates(Prove_ByteArray *data, int64_t index);

#endif /* PROVE_BYTES_H */
