#ifndef PROVE_HASH_CRYPTO_H
#define PROVE_HASH_CRYPTO_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_bytes.h"

/* ── SHA-256 channel ─────────────────────────────────────────── */

Prove_ByteArray *prove_crypto_sha256_bytes(Prove_ByteArray *data);
Prove_String    *prove_crypto_sha256_string(Prove_String *data);
bool             prove_crypto_sha256_validates(Prove_ByteArray *data, Prove_ByteArray *expected);

/* ── SHA-512 channel ─────────────────────────────────────────── */

Prove_ByteArray *prove_crypto_sha512_bytes(Prove_ByteArray *data);
Prove_String    *prove_crypto_sha512_string(Prove_String *data);
bool             prove_crypto_sha512_validates(Prove_ByteArray *data, Prove_ByteArray *expected);

/* ── BLAKE3 channel ──────────────────────────────────────────── */

Prove_ByteArray *prove_crypto_blake3_bytes(Prove_ByteArray *data);
Prove_String    *prove_crypto_blake3_string(Prove_String *data);
bool             prove_crypto_blake3_validates(Prove_ByteArray *data, Prove_ByteArray *expected);

/* ── HMAC channel ────────────────────────────────────────────── */

Prove_ByteArray *prove_crypto_hmac_create(Prove_ByteArray *data, Prove_ByteArray *key);
bool             prove_crypto_hmac_validates(Prove_ByteArray *data, Prove_ByteArray *key,
                                              Prove_ByteArray *signature);

#endif /* PROVE_HASH_CRYPTO_H */
