#include "prove_hash.h"

/* ── Hardware CRC32 paths ─────────────────────────────────────── */

#if defined(__SSE4_2__)
#include <nmmintrin.h>

uint32_t prove_hash(const char *data, size_t len) {
    uint32_t h = 0xFFFFFFFF;
    size_t i = 0;
    /* Process 8 bytes at a time on 64-bit */
    for (; i + 8 <= len; i += 8) {
        uint64_t word;
        __builtin_memcpy(&word, data + i, 8);
        h = (uint32_t)_mm_crc32_u64(h, word);
    }
    /* Process remaining bytes */
    for (; i < len; i++) {
        h = _mm_crc32_u8(h, (uint8_t)data[i]);
    }
    return h ^ 0xFFFFFFFF;
}

#elif defined(__ARM_FEATURE_CRC32)
#include <arm_acle.h>

uint32_t prove_hash(const char *data, size_t len) {
    uint32_t h = 0xFFFFFFFF;
    size_t i = 0;
    for (; i + 8 <= len; i += 8) {
        uint64_t word;
        __builtin_memcpy(&word, data + i, 8);
        h = __crc32cd(h, word);
    }
    for (; i < len; i++) {
        h = __crc32cb(h, (uint8_t)data[i]);
    }
    return h ^ 0xFFFFFFFF;
}

#else
/* ── FNV-1a fallback ──────────────────────────────────────────── */

uint32_t prove_hash(const char *data, size_t len) {
    uint32_t h = 0x811C9DC5u;  /* FNV offset basis */
    for (size_t i = 0; i < len; i++) {
        h ^= (uint8_t)data[i];
        h *= 0x01000193u;      /* FNV prime */
    }
    return h;
}

#endif
