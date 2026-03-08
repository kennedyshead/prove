#ifndef PROVE_HOF_H
#define PROVE_HOF_H

#include "prove_list.h"

/* ── Higher-order list functions (Value-based) ───────────────── */

/* Map: apply fn to each element, producing a new list. */
Prove_List *prove_list_map(
    Prove_List *list,
    void *(*fn)(void *)
);

/* Filter: keep elements where pred returns true. */
Prove_List *prove_list_filter(
    Prove_List *list,
    bool (*pred)(void *)
);

/* Each: call fn for each element (side effects, returns nothing). */
void prove_list_each(
    Prove_List *list,
    void (*fn)(void *)
);

/* Reduce: fold list from left with an accumulator. */
void *prove_list_reduce(
    Prove_List *list,
    void *init,
    void *(*fn)(void *accum, void *elem)
);

#endif /* PROVE_HOF_H */
