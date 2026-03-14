#ifndef PROVE_BITARRAY_H
#define PROVE_BITARRAY_H

/*
 * Prove_BitArray — optimized boolean array for release-mode builds.
 *
 * Layout-compatible with Prove_Array (same field offsets) so it can be
 * safely cast to/from Prove_Array*.  The optimisation is that the inline
 * accessors bypass memcpy and function-call overhead, allowing the C
 * compiler to vectorise and optimise the tight loops directly.
 *
 * In debug mode, the standard Prove_Array is used instead and these
 * functions are never called.
 */

#include "prove_array.h"

/* ── Optimised inline accessors ──────────────────────────────── */

/* Create via the standard path — same allocation, same layout. */
static inline Prove_Array *prove_bitarray_new(int64_t size, bool default_val) {
    return prove_array_new_bool(size, default_val);
}

/* Direct indexed read — no memcpy, no function-call overhead. */
static inline bool prove_bitarray_get(Prove_Array *arr, int64_t idx) {
    return ((bool *)arr->data)[idx];
}

/* Direct indexed write for mutable arrays — no memcpy. */
static inline void prove_bitarray_set(Prove_Array *arr, int64_t idx, bool val) {
    ((bool *)arr->data)[idx] = val;
}

#endif /* PROVE_BITARRAY_H */
