#ifndef PROVE_RANDOM_H
#define PROVE_RANDOM_H

#include "prove_runtime.h"
#include "prove_list.h"
#include "prove_string.h"

/* ── Integer ─────────────────────────────────────────────────── */

int64_t prove_random_integer(void);
int64_t prove_random_integer_range(int64_t min, int64_t max);
bool    prove_random_validates_integer(int64_t value, int64_t min, int64_t max);

/* ── Decimal ─────────────────────────────────────────────────── */

double prove_random_decimal(void);
double prove_random_decimal_range(double min, double max);

/* ── Boolean ─────────────────────────────────────────────────── */

bool prove_random_boolean(void);

/* ── Choice (unified) ────────────────────────────────────────── */

void *prove_random_choice_raw(Prove_List *list);

/* Typed wrappers for overload dispatch */
static inline int64_t prove_random_choice_int(Prove_List *list) {
    return (int64_t)(intptr_t)prove_random_choice_raw(list);
}

static inline Prove_String *prove_random_choice_str(Prove_List *list) {
    return (Prove_String *)prove_random_choice_raw(list);
}

/* ── Shuffle (unified) ───────────────────────────────────────── */

Prove_List *prove_random_shuffle_raw(Prove_List *list);

/* Typed wrappers — shuffle preserves element types, so both return Prove_List* */
static inline Prove_List *prove_random_shuffle_int(Prove_List *list) {
    return prove_random_shuffle_raw(list);
}

static inline Prove_List *prove_random_shuffle_str(Prove_List *list) {
    return prove_random_shuffle_raw(list);
}

#endif /* PROVE_RANDOM_H */
