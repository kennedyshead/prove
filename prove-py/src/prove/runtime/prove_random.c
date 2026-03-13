#include "prove_random.h"
#include <stdlib.h>
#include <time.h>

/* ── Auto-seed ───────────────────────────────────────────────── */

static int _seeded = 0;

static void _ensure_seeded(void) {
    if (!_seeded) {
        srand((unsigned int)time(NULL));
        _seeded = 1;
    }
}

/* ── Integer ─────────────────────────────────────────────────── */

int64_t prove_random_integer(void) {
    _ensure_seeded();
    /* Combine two rand() calls for wider range */
    int64_t hi = (int64_t)rand();
    int64_t lo = (int64_t)rand();
    return (hi << 16) ^ lo;
}

int64_t prove_random_integer_range(int64_t min, int64_t max) {
    _ensure_seeded();
    if (min >= max) return min;
    uint64_t range = (uint64_t)(max - min) + 1;
    int64_t hi = (int64_t)rand();
    int64_t lo = (int64_t)rand();
    uint64_t r = ((uint64_t)hi << 16) ^ (uint64_t)lo;
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
    if (!list || list->length == 0) {
        prove_panic("choice: empty list");
    }
    uint64_t r = ((uint64_t)rand() << 16) ^ (uint64_t)rand();
    int64_t idx = (int64_t)(r % (uint64_t)list->length);
    return prove_list_get(list, idx);
}

/* ── Shuffle (raw — returns new list) ───────────────────────── */

Prove_List *prove_random_shuffle_raw(Prove_List *list) {
    _ensure_seeded();
    if (!list || list->length == 0) {
        return prove_list_new(4);
    }
    Prove_List *result = prove_list_new(list->length);
    memcpy(result->data, list->data, sizeof(void *) * (size_t)list->length);
    result->length = list->length;

    /* Fisher-Yates shuffle */
    for (int64_t i = result->length - 1; i > 0; i--) {
        uint64_t r = ((uint64_t)rand() << 16) ^ (uint64_t)rand();
        int64_t j = (int64_t)(r % (uint64_t)(i + 1));
        /* Swap pointers */
        void *tmp = result->data[i];
        result->data[i] = result->data[j];
        result->data[j] = tmp;
    }
    return result;
}
