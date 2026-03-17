#ifndef PROVE_PAR_MAP_H
#define PROVE_PAR_MAP_H

#include "prove_list.h"
#include <stdint.h>
#include <stdbool.h>

/* Function pointer types for parallel HOFs. */
typedef void *(*Prove_MapFn)(void *);
typedef bool  (*Prove_FilterFn)(void *);
typedef void *(*Prove_ReduceFn)(void *accum, void *elem);

/* Parallel map over a list.
 *
 * Applies fn to each element of list using num_workers threads.
 * When num_workers == 0, auto-detects based on available CPU cores.
 * Falls back to sequential map when num_workers <= 1, the list is small,
 * or pthreads are unavailable.
 *
 * Pure functions only — no shared mutable state allowed (enforced by the
 * Prove type system, not by this runtime).
 */
Prove_List *prove_par_map(Prove_List *list, Prove_MapFn fn, int64_t num_workers);

/* Parallel filter over a list.
 *
 * Keeps elements where pred returns true, using num_workers threads.
 * When num_workers == 0, auto-detects based on available CPU cores.
 * Order is preserved.
 */
Prove_List *prove_par_filter(Prove_List *list, Prove_FilterFn pred, int64_t num_workers);

/* Parallel reduce over a list.
 *
 * Folds list from left with an accumulator, using num_workers threads
 * for the element-wise application phase.  The final merge is sequential.
 * When num_workers == 0, auto-detects based on available CPU cores.
 */
void *prove_par_reduce(Prove_List *list, void *init, Prove_ReduceFn fn, int64_t num_workers);

#endif /* PROVE_PAR_MAP_H */
