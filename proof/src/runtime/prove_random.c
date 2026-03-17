#include "prove_random.h"
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

/* ── Auto-seed ───────────────────────────────────────────────── */

static int _seeded = 0;

static void _ensure_seeded(void) {
    if (!_seeded) {
        srand((unsigned int)time(NULL));
        _seeded = 1;
    }
}

/* ── Full 64-bit random helper ───────────────────────────────── */

static uint64_t _random_u64(void) {
    /* Combine multiple rand() calls to fill 64 bits.
       rand() gives at least 15 bits (RAND_MAX >= 32767).
       5 * 15 = 75 bits > 64, so all bits are covered. */
    uint64_t r = 0;
    for (int i = 0; i < 5; i++) {
        r = (r << 15) | ((uint64_t)rand() & 0x7FFF);
    }
    return r;
}

/* ── Integer ─────────────────────────────────────────────────── */

int64_t prove_random_integer(void) {
    _ensure_seeded();
    return (int64_t)_random_u64();
}

int64_t prove_random_integer_range(int64_t min, int64_t max) {
    _ensure_seeded();
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
    _ensure_seeded();
    return (double)rand() / (double)RAND_MAX;
}

double prove_random_decimal_range(double min, double max) {
    _ensure_seeded();
    if (min >= max) return min;
    double t = (double)rand() / (double)RAND_MAX;
    return min + t * (max - min);
}

/* ── Boolean ─────────────────────────────────────────────────── */

bool prove_random_boolean(void) {
    _ensure_seeded();
    return rand() % 2 == 0;
}

/* ── Choice (raw — returns void*) ───────────────────────────── */

void *prove_random_choice_raw(Prove_List *list) {
    _ensure_seeded();
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
    _ensure_seeded();
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
