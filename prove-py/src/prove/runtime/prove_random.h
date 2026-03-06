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

/* ── Choice ──────────────────────────────────────────────────── */

int64_t       prove_random_choice_int(Prove_List *list);
Prove_String *prove_random_choice_str(Prove_List *list);

/* ── Shuffle ─────────────────────────────────────────────────── */

Prove_List *prove_random_shuffle_int(Prove_List *list);
Prove_List *prove_random_shuffle_str(Prove_List *list);

#endif /* PROVE_RANDOM_H */
