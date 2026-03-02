#ifndef PROVE_HOF_H
#define PROVE_HOF_H

#include "prove_list.h"

/* ── Higher-order list functions ─────────────────────────────── */

/* Map: apply fn to each element, producing a new list. */
Prove_List *prove_list_map(
    Prove_List *list,
    void *(*fn)(const void *),
    size_t result_elem_size
);

/* Filter: keep elements where pred returns true. */
Prove_List *prove_list_filter(
    Prove_List *list,
    bool (*pred)(const void *)
);

/* Each: call fn for each element (side effects, returns nothing). */
void prove_list_each(
    Prove_List *list,
    void (*fn)(const void *)
);

/* Reduce: fold list from left with an accumulator. */
void prove_list_reduce(
    Prove_List *list,
    void *accum,
    void (*fn)(void *accum, const void *elem)
);

#endif /* PROVE_HOF_H */
