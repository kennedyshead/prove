#ifndef PROVE_HASH_H
#define PROVE_HASH_H

#include <stdint.h>
#include <stddef.h>

/* Hash a byte buffer. Uses hardware CRC32 when available, FNV-1a fallback. */
uint32_t prove_hash(const char *data, size_t len);

#endif /* PROVE_HASH_H */
