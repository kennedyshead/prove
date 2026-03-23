#include "prove_random.h"
#include <stdlib.h>
#include <stdint.h>

/* ── Full 64-bit random helper (arc4random, no seeding needed) ── */

static uint64_t _random_u64(void) {
    uint64_t val;
    arc4random_buf(&val, sizeof(val));
    return val;
}

/* ── Integer ─────────────────────────────────────────────────── */

int64_t prove_random_integer(void) {
    return (int64_t)_random_u64();
}

int64_t prove_random_integer_range(int64_t min, int64_t max) {
    if (min >= max) return min;
    uint64_t range = (uint64_t)(max - min) + 1;
    /* Rejection sampling: discard values that would cause modulo bias */
    uint64_t limit = UINT64_MAX - (UINT64_MAX % range);
    uint64_t r;
    do { r = _random_u64(); } while (r >= limit);
    return min + (int64_t)(r % range);
}

bool prove_random_validates_integer(int64_t value, int64_t min, int64_t max) {
    return value >= min && value <= max;
}

/* ── Decimal ─────────────────────────────────────────────────── */

double prove_random_decimal(void) {
    /* Use 53 bits for a uniform double in [0, 1) */
    return (double)(_random_u64() >> 11) * (1.0 / 9007199254740992.0);
}

double prove_random_decimal_range(double min, double max) {
    if (min >= max) return min;
    double t = prove_random_decimal();
    return min + t * (max - min);
}

/* ── Boolean ─────────────────────────────────────────────────── */

bool prove_random_boolean(void) {
    return (_random_u64() & 1) == 0;
}

/* ── Choice (raw — returns void*) ───────────────────────────── */

void *prove_random_choice_raw(Prove_List *list) {
    if (list->length == 0) {
        prove_panic("choice: empty list");
    }
    uint64_t len = (uint64_t)list->length;
    uint64_t limit = UINT64_MAX - (UINT64_MAX % len);
    uint64_t r;
    do { r = _random_u64(); } while (r >= limit);
    int64_t idx = (int64_t)(r % len);
    return prove_list_get(list, idx);
}

/* ── Shuffle (raw — returns new list) ───────────────────────── */

Prove_List *prove_random_shuffle_raw(Prove_List *list) {
    if (list->length == 0) {
        return prove_list_new(4);
    }
    Prove_List *result = prove_list_new(list->length);
    memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
    result->length = list->length;

    /* Fisher-Yates shuffle */
    for (int64_t i = result->length - 1; i > 0; i--) {
        uint64_t range = (uint64_t)(i + 1);
        uint64_t limit = UINT64_MAX - (UINT64_MAX % range);
        uint64_t r;
        do { r = _random_u64(); } while (r >= limit);
        int64_t j = (int64_t)(r % range);
        /* Swap pointers */
        void *tmp = result->data[i];
        result->data[i] = result->data[j];
        result->data[j] = tmp;
    }
    return result;
}
