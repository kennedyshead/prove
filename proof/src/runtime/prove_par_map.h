#ifndef PROVE_PAR_MAP_H
#define PROVE_PAR_MAP_H

#include "prove_list.h"
#include <stdint.h>

/* Function pointer type for par_map: takes one element, returns one result. */
typedef void *(*Prove_MapFn)(void *);

/* Parallel map over a list.
 *
 * Applies fn to each element of list using num_workers threads.
 * Falls back to sequential map when num_workers <= 1, the list is small,
 * or pthreads are unavailable.
 *
 * Pure functions only — no shared mutable state allowed (enforced by the
 * Prove type system, not by this runtime).
 */
Prove_List *prove_par_map(Prove_List *list, Prove_MapFn fn, int64_t num_workers);

#endif /* PROVE_PAR_MAP_H */
