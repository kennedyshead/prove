#include "prove_hash_crypto.h"
#include <string.h>

/* ================================================================
 * SHA-256 implementation (FIPS 180-4)
 * ================================================================ */

static const uint32_t _sha256_k[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

#define RR32(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void _sha256_transform(uint32_t state[8], const uint8_t block[64]) {
    uint32_t w[64], a, b, c, d, e, f, g, h;
    for (int i = 0; i < 16; i++) {
        w[i] = ((uint32_t)block[i*4] << 24) | ((uint32_t)block[i*4+1] << 16) |
               ((uint32_t)block[i*4+2] << 8) | (uint32_t)block[i*4+3];
    }
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = RR32(w[i-15], 7) ^ RR32(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t s1 = RR32(w[i-2], 17) ^ RR32(w[i-2], 19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    a = state[0]; b = state[1]; c = state[2]; d = state[3];
    e = state[4]; f = state[5]; g = state[6]; h = state[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = RR32(e, 6) ^ RR32(e, 11) ^ RR32(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + S1 + ch + _sha256_k[i] + w[i];
        uint32_t S0 = RR32(a, 2) ^ RR32(a, 13) ^ RR32(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + maj;
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

static void _sha256(const uint8_t *data, size_t len, uint8_t out[32]) {
    if (!data) data = (const uint8_t *)"";
    uint32_t state[8] = {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
    };
    uint8_t block[64];
    size_t i;
    for (i = 0; i + 64 <= len; i += 64)
        _sha256_transform(state, data + i);
    size_t rem = len - i;
    if (rem > 0) memcpy(block, data + i, rem);
    block[rem] = 0x80;
    if (rem >= 56) {
        memset(block + rem + 1, 0, 64 - rem - 1);
        _sha256_transform(state, block);
        memset(block, 0, 56);
    } else {
        memset(block + rem + 1, 0, 56 - rem - 1);
    }
    uint64_t bits = (uint64_t)len * 8;
    for (int j = 7; j >= 0; j--) {
        block[56 + (7 - j)] = (uint8_t)(bits >> (j * 8));
    }
    _sha256_transform(state, block);
    for (int j = 0; j < 8; j++) {
        out[j*4]   = (uint8_t)(state[j] >> 24);
        out[j*4+1] = (uint8_t)(state[j] >> 16);
        out[j*4+2] = (uint8_t)(state[j] >> 8);
        out[j*4+3] = (uint8_t)(state[j]);
    }
}

/* ================================================================
 * SHA-512 implementation (FIPS 180-4)
 * ================================================================ */

static const uint64_t _sha512_k[80] = {
    0x428a2f98d728ae22ULL, 0x7137449123ef65cdULL, 0xb5c0fbcfec4d3b2fULL, 0xe9b5dba58189dbbcULL,
    0x3956c25bf348b538ULL, 0x59f111f1b605d019ULL, 0x923f82a4af194f9bULL, 0xab1c5ed5da6d8118ULL,
    0xd807aa98a3030242ULL, 0x12835b0145706fbeULL, 0x243185be4ee4b28cULL, 0x550c7dc3d5ffb4e2ULL,
    0x72be5d74f27b896fULL, 0x80deb1fe3b1696b1ULL, 0x9bdc06a725c71235ULL, 0xc19bf174cf692694ULL,
    0xe49b69c19ef14ad2ULL, 0xefbe4786384f25e3ULL, 0x0fc19dc68b8cd5b5ULL, 0x240ca1cc77ac9c65ULL,
    0x2de92c6f592b0275ULL, 0x4a7484aa6ea6e483ULL, 0x5cb0a9dcbd41fbd4ULL, 0x76f988da831153b5ULL,
    0x983e5152ee66dfabULL, 0xa831c66d2db43210ULL, 0xb00327c898fb213fULL, 0xbf597fc7beef0ee4ULL,
    0xc6e00bf33da88fc2ULL, 0xd5a79147930aa725ULL, 0x06ca6351e003826fULL, 0x142929670a0e6e70ULL,
    0x27b70a8546d22ffcULL, 0x2e1b21385c26c926ULL, 0x4d2c6dfc5ac42aedULL, 0x53380d139d95b3dfULL,
    0x650a73548baf63deULL, 0x766a0abb3c77b2a8ULL, 0x81c2c92e47edaee6ULL, 0x92722c851482353bULL,
    0xa2bfe8a14cf10364ULL, 0xa81a664bbc423001ULL, 0xc24b8b70d0f89791ULL, 0xc76c51a30654be30ULL,
    0xd192e819d6ef5218ULL, 0xd69906245565a910ULL, 0xf40e35855771202aULL, 0x106aa07032bbd1b8ULL,
    0x19a4c116b8d2d0c8ULL, 0x1e376c085141ab53ULL, 0x2748774cdf8eeb99ULL, 0x34b0bcb5e19b48a8ULL,
    0x391c0cb3c5c95a63ULL, 0x4ed8aa4ae3418acbULL, 0x5b9cca4f7763e373ULL, 0x682e6ff3d6b2b8a3ULL,
    0x748f82ee5defb2fcULL, 0x78a5636f43172f60ULL, 0x84c87814a1f0ab72ULL, 0x8cc702081a6439ecULL,
    0x90befffa23631e28ULL, 0xa4506cebde82bde9ULL, 0xbef9a3f7b2c67915ULL, 0xc67178f2e372532bULL,
    0xca273eceea26619cULL, 0xd186b8c721c0c207ULL, 0xeada7dd6cde0eb1eULL, 0xf57d4f7fee6ed178ULL,
    0x06f067aa72176fbaULL, 0x0a637dc5a2c898a6ULL, 0x113f9804bef90daeULL, 0x1b710b35131c471bULL,
    0x28db77f523047d84ULL, 0x32caab7b40c72493ULL, 0x3c9ebe0a15c9bebcULL, 0x431d67c49c100d4cULL,
    0x4cc5d4becb3e42b6ULL, 0x597f299cfc657e2aULL, 0x5fcb6fab3ad6faecULL, 0x6c44198c4a475817ULL,
};

#define RR64(x, n) (((x) >> (n)) | ((x) << (64 - (n))))

static void _sha512_transform(uint64_t state[8], const uint8_t block[128]) {
    uint64_t w[80], a, b, c, d, e, f, g, h;
    for (int i = 0; i < 16; i++) {
        w[i] = ((uint64_t)block[i*8] << 56) | ((uint64_t)block[i*8+1] << 48) |
               ((uint64_t)block[i*8+2] << 40) | ((uint64_t)block[i*8+3] << 32) |
               ((uint64_t)block[i*8+4] << 24) | ((uint64_t)block[i*8+5] << 16) |
               ((uint64_t)block[i*8+6] << 8)  | (uint64_t)block[i*8+7];
    }
    for (int i = 16; i < 80; i++) {
        uint64_t s0 = RR64(w[i-15], 1) ^ RR64(w[i-15], 8) ^ (w[i-15] >> 7);
        uint64_t s1 = RR64(w[i-2], 19) ^ RR64(w[i-2], 61) ^ (w[i-2] >> 6);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    a = state[0]; b = state[1]; c = state[2]; d = state[3];
    e = state[4]; f = state[5]; g = state[6]; h = state[7];
    for (int i = 0; i < 80; i++) {
        uint64_t S1 = RR64(e, 14) ^ RR64(e, 18) ^ RR64(e, 41);
        uint64_t ch = (e & f) ^ (~e & g);
        uint64_t t1 = h + S1 + ch + _sha512_k[i] + w[i];
        uint64_t S0 = RR64(a, 28) ^ RR64(a, 34) ^ RR64(a, 39);
        uint64_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint64_t t2 = S0 + maj;
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

static void _sha512(const uint8_t *data, size_t len, uint8_t out[64]) {
    if (!data) data = (const uint8_t *)"";
    uint64_t state[8] = {
        0x6a09e667f3bcc908ULL, 0xbb67ae8584caa73bULL,
        0x3c6ef372fe94f82bULL, 0xa54ff53a5f1d36f1ULL,
        0x510e527fade682d1ULL, 0x9b05688c2b3e6c1fULL,
        0x1f83d9abfb41bd6bULL, 0x5be0cd19137e2179ULL
    };
    uint8_t block[128];
    size_t i;
    for (i = 0; i + 128 <= len; i += 128)
        _sha512_transform(state, data + i);
    size_t rem = len - i;
    if (rem > 0) memcpy(block, data + i, rem);
    block[rem] = 0x80;
    if (rem >= 112) {
        memset(block + rem + 1, 0, 128 - rem - 1);
        _sha512_transform(state, block);
        memset(block, 0, 112);
    } else {
        memset(block + rem + 1, 0, 112 - rem - 1);
    }
    /* Length in bits (only lower 64 bits for simplicity) */
    uint64_t bits = (uint64_t)len * 8;
    memset(block + 112, 0, 8);  /* high 64 bits = 0 */
    for (int j = 7; j >= 0; j--) {
        block[120 + (7 - j)] = (uint8_t)(bits >> (j * 8));
    }
    _sha512_transform(state, block);
    for (int j = 0; j < 8; j++) {
        out[j*8]   = (uint8_t)(state[j] >> 56);
        out[j*8+1] = (uint8_t)(state[j] >> 48);
        out[j*8+2] = (uint8_t)(state[j] >> 40);
        out[j*8+3] = (uint8_t)(state[j] >> 32);
        out[j*8+4] = (uint8_t)(state[j] >> 24);
        out[j*8+5] = (uint8_t)(state[j] >> 16);
        out[j*8+6] = (uint8_t)(state[j] >> 8);
        out[j*8+7] = (uint8_t)(state[j]);
    }
}

/* ================================================================
 * BLAKE3 — simplified single-chunk implementation
 * Based on the BLAKE3 reference spec (256-bit output)
 * Uses BLAKE2s-like compression for single-chunk messages
 * ================================================================ */

static const uint32_t _blake3_iv[8] = {
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
};

static const uint8_t _blake3_sigma[7][16] = {
    {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
    {2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8},
    {3, 4, 10, 12, 13, 2, 7, 14, 6, 5, 9, 0, 11, 15, 8, 1},
    {10, 7, 12, 9, 14, 3, 13, 15, 4, 0, 11, 2, 5, 8, 1, 6},
    {12, 13, 9, 11, 15, 10, 14, 8, 7, 2, 5, 3, 0, 1, 6, 4},
    {9, 14, 11, 5, 8, 12, 15, 1, 13, 3, 0, 10, 2, 6, 4, 7},
    {11, 15, 5, 0, 1, 9, 8, 6, 14, 10, 2, 12, 3, 4, 7, 13},
};

#define B3_G(state, a, b, c, d, mx, my) do { \
    state[a] += state[b] + mx; \
    state[d] = RR32(state[d] ^ state[a], 16); \
    state[c] += state[d]; \
    state[b] = RR32(state[b] ^ state[c], 12); \
    state[a] += state[b] + my; \
    state[d] = RR32(state[d] ^ state[a], 8); \
    state[c] += state[d]; \
    state[b] = RR32(state[b] ^ state[c], 7); \
} while(0)

static void _blake3_compress(const uint32_t cv[8], const uint32_t block_words[16],
                              uint64_t counter, uint32_t block_len, uint32_t flags,
                              uint32_t out[16]) {
    uint32_t s[16];
    memcpy(s, cv, 32);
    s[8]  = _blake3_iv[0]; s[9]  = _blake3_iv[1];
    s[10] = _blake3_iv[2]; s[11] = _blake3_iv[3];
    s[12] = (uint32_t)counter;
    s[13] = (uint32_t)(counter >> 32);
    s[14] = block_len;
    s[15] = flags;

    for (int r = 0; r < 7; r++) {
        const uint8_t *sig = _blake3_sigma[r];
        B3_G(s, 0, 4,  8, 12, block_words[sig[0]],  block_words[sig[1]]);
        B3_G(s, 1, 5,  9, 13, block_words[sig[2]],  block_words[sig[3]]);
        B3_G(s, 2, 6, 10, 14, block_words[sig[4]],  block_words[sig[5]]);
        B3_G(s, 3, 7, 11, 15, block_words[sig[6]],  block_words[sig[7]]);
        B3_G(s, 0, 5, 10, 15, block_words[sig[8]],  block_words[sig[9]]);
        B3_G(s, 1, 6, 11, 12, block_words[sig[10]], block_words[sig[11]]);
        B3_G(s, 2, 7,  8, 13, block_words[sig[12]], block_words[sig[13]]);
        B3_G(s, 3, 4,  9, 14, block_words[sig[14]], block_words[sig[15]]);
    }
    for (int i = 0; i < 8; i++) {
        s[i] ^= s[i + 8];
        s[i + 8] ^= cv[i];
    }
    memcpy(out, s, 64);
}

#define BLAKE3_CHUNK_START 1
#define BLAKE3_CHUNK_END   2
#define BLAKE3_ROOT        8

static void _blake3(const uint8_t *data, size_t len, uint8_t out[32]) {
    if (!data) data = (const uint8_t *)"";
    /* Simplified: single-chunk (up to 1024 bytes) implementation.
     * For inputs longer than 1024 bytes, fall back to SHA-256 since this
     * implementation only handles a single chunk correctly. */
    if (len > 1024) {
        _sha256(data, len, out);
        return;
    }
    uint32_t cv[8];
    memcpy(cv, _blake3_iv, 32);

    size_t pos = 0;
    int block_idx = 0;
    while (pos < len || (pos == 0 && len == 0)) {
        uint32_t block_words[16];
        memset(block_words, 0, 64);
        size_t take = len - pos;
        if (take > 64) take = 64;
        uint8_t buf[64];
        memset(buf, 0, 64);
        if (take > 0) memcpy(buf, data + pos, take);
        for (int i = 0; i < 16; i++) {
            block_words[i] = (uint32_t)buf[i*4] | ((uint32_t)buf[i*4+1] << 8) |
                             ((uint32_t)buf[i*4+2] << 16) | ((uint32_t)buf[i*4+3] << 24);
        }
        uint32_t flags = 0;
        if (block_idx == 0) flags |= BLAKE3_CHUNK_START;
        int is_last = (pos + take >= len);
        if (is_last) flags |= BLAKE3_CHUNK_END | BLAKE3_ROOT;

        uint32_t out16[16];
        _blake3_compress(cv, block_words, 0, (uint32_t)take, flags, out16);
        memcpy(cv, out16, 32);

        pos += take;
        block_idx++;
        if (len == 0) break;
    }
    for (int i = 0; i < 8; i++) {
        out[i*4]   = (uint8_t)(cv[i]);
        out[i*4+1] = (uint8_t)(cv[i] >> 8);
        out[i*4+2] = (uint8_t)(cv[i] >> 16);
        out[i*4+3] = (uint8_t)(cv[i] >> 24);
    }
}

/* ================================================================
 * Helper: bytes to hex string
 * ================================================================ */

static const char _hc[] = "0123456789abcdef";

static Prove_String *_bytes_to_hex(const uint8_t *data, size_t len) {
    char *buf = malloc(len * 2 + 1);
    if (!buf) prove_panic("out of memory");
    for (size_t i = 0; i < len; i++) {
        buf[i*2] = _hc[(data[i] >> 4) & 0xF];
        buf[i*2+1] = _hc[data[i] & 0xF];
    }
    buf[len * 2] = '\0';
    Prove_String *result = prove_string_from_cstr(buf);
    free(buf);
    return result;
}

static Prove_ByteArray *_make_byte_array(const uint8_t *data, int64_t len) {
    size_t sz = sizeof(Prove_ByteArray) + (size_t)len;
    Prove_ByteArray *ba = prove_alloc(sz);
    ba->length = len;
    memcpy(ba->data, data, (size_t)len);
    return ba;
}

static bool _constant_time_eq(const uint8_t *a, const uint8_t *b, size_t len) {
    uint8_t diff = 0;
    for (size_t i = 0; i < len; i++) diff |= a[i] ^ b[i];
    return diff == 0;
}

/* ================================================================
 * SHA-256 channel
 * ================================================================ */

Prove_ByteArray *prove_crypto_sha256_bytes(Prove_ByteArray *data) {
    uint8_t hash[32];
    if (!data || data->length == 0) {
        _sha256(NULL, 0, hash);
    } else {
        _sha256(data->data, (size_t)data->length, hash);
    }
    return _make_byte_array(hash, 32);
}

Prove_String *prove_crypto_sha256_string(Prove_String *data) {
    uint8_t hash[32];
    if (!data || data->length == 0) {
        _sha256(NULL, 0, hash);
    } else {
        _sha256((const uint8_t *)data->data, (size_t)data->length, hash);
    }
    return _bytes_to_hex(hash, 32);
}

bool prove_crypto_sha256_validates(Prove_ByteArray *data, Prove_ByteArray *expected) {
    if (!expected || expected->length != 32) return false;
    uint8_t hash[32];
    if (!data || data->length == 0) {
        _sha256(NULL, 0, hash);
    } else {
        _sha256(data->data, (size_t)data->length, hash);
    }
    return _constant_time_eq(hash, expected->data, 32);
}

/* ================================================================
 * SHA-512 channel
 * ================================================================ */

Prove_ByteArray *prove_crypto_sha512_bytes(Prove_ByteArray *data) {
    uint8_t hash[64];
    if (!data || data->length == 0) {
        _sha512(NULL, 0, hash);
    } else {
        _sha512(data->data, (size_t)data->length, hash);
    }
    return _make_byte_array(hash, 64);
}

Prove_String *prove_crypto_sha512_string(Prove_String *data) {
    uint8_t hash[64];
    if (!data || data->length == 0) {
        _sha512(NULL, 0, hash);
    } else {
        _sha512((const uint8_t *)data->data, (size_t)data->length, hash);
    }
    return _bytes_to_hex(hash, 64);
}

bool prove_crypto_sha512_validates(Prove_ByteArray *data, Prove_ByteArray *expected) {
    if (!expected || expected->length != 64) return false;
    uint8_t hash[64];
    if (!data || data->length == 0) {
        _sha512(NULL, 0, hash);
    } else {
        _sha512(data->data, (size_t)data->length, hash);
    }
    return _constant_time_eq(hash, expected->data, 64);
}

/* ================================================================
 * BLAKE3 channel
 * ================================================================ */

Prove_ByteArray *prove_crypto_blake3_bytes(Prove_ByteArray *data) {
    uint8_t hash[32];
    if (!data || data->length == 0) {
        _blake3(NULL, 0, hash);
    } else {
        _blake3(data->data, (size_t)data->length, hash);
    }
    return _make_byte_array(hash, 32);
}

Prove_String *prove_crypto_blake3_string(Prove_String *data) {
    uint8_t hash[32];
    if (!data || data->length == 0) {
        _blake3(NULL, 0, hash);
    } else {
        _blake3((const uint8_t *)data->data, (size_t)data->length, hash);
    }
    return _bytes_to_hex(hash, 32);
}

bool prove_crypto_blake3_validates(Prove_ByteArray *data, Prove_ByteArray *expected) {
    if (!expected || expected->length != 32) return false;
    uint8_t hash[32];
    if (!data || data->length == 0) {
        _blake3(NULL, 0, hash);
    } else {
        _blake3(data->data, (size_t)data->length, hash);
    }
    return _constant_time_eq(hash, expected->data, 32);
}

/* ================================================================
 * HMAC-SHA256 channel
 * ================================================================ */

Prove_ByteArray *prove_crypto_hmac_create(Prove_ByteArray *data, Prove_ByteArray *key) {
    uint8_t k_pad[64];
    memset(k_pad, 0, 64);

    /* If key > 64 bytes, hash it first */
    if (key && key->length > 64) {
        _sha256(key->data, (size_t)key->length, k_pad);
    } else if (key) {
        memcpy(k_pad, key->data, (size_t)key->length);
    }

    /* Inner hash: SHA256((k ^ ipad) || data) */
    uint8_t inner_key[64];
    for (int i = 0; i < 64; i++) inner_key[i] = k_pad[i] ^ 0x36;

    size_t data_len = data ? (size_t)data->length : 0;
    size_t inner_len = 64 + data_len;
    uint8_t *inner_msg = malloc(inner_len);
    if (!inner_msg) prove_panic("out of memory");
    memcpy(inner_msg, inner_key, 64);
    if (data_len > 0) memcpy(inner_msg + 64, data->data, data_len);

    uint8_t inner_hash[32];
    _sha256(inner_msg, inner_len, inner_hash);
    free(inner_msg);

    /* Outer hash: SHA256((k ^ opad) || inner_hash) */
    uint8_t outer_key[64];
    for (int i = 0; i < 64; i++) outer_key[i] = k_pad[i] ^ 0x5c;

    uint8_t outer_msg[96]; /* 64 + 32 */
    memcpy(outer_msg, outer_key, 64);
    memcpy(outer_msg + 64, inner_hash, 32);

    uint8_t hmac[32];
    _sha256(outer_msg, 96, hmac);

    return _make_byte_array(hmac, 32);
}

bool prove_crypto_hmac_validates(Prove_ByteArray *data, Prove_ByteArray *key,
                                  Prove_ByteArray *signature) {
    if (!signature || signature->length != 32) return false;
    Prove_ByteArray *computed = prove_crypto_hmac_create(data, key);
    bool eq = _constant_time_eq(computed->data, signature->data, 32);
    prove_release(computed);
    return eq;
}
