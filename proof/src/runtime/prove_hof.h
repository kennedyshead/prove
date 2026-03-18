#ifndef PROVE_HOF_H
#define PROVE_HOF_H

#include "prove_list.h"
#include <string.h>

/* ── Float boxing for void* HOF callbacks ────────────────────── */

static inline void *_prove_f64_box(double d) {
    void *p;
    memcpy(&p, &d, sizeof(p));
    return p;
}

static inline double _prove_f64_unbox(void *p) {
    double d;
    memcpy(&d, &p, sizeof(d));
    return d;
}

/* ── Higher-order list functions (Value-based) ───────────────── */

/* Map: apply fn to each element, producing a new list. */
Prove_List *prove_list_map(
    Prove_List *list,
    void *(*fn)(void *, void *),
    void *ctx
);

/* Filter: keep elements where pred returns true. */
Prove_List *prove_list_filter(
    Prove_List *list,
    bool (*pred)(void *, void *),
    void *ctx
);

/* Each: call fn for each element (side effects, returns nothing). */
void prove_list_each(
    Prove_List *list,
    void (*fn)(void *, void *),
    void *ctx
);

/* Reduce: fold list from left with an accumulator. */
void *prove_list_reduce(
    Prove_List *list,
    void *init,
    void *(*fn)(void *accum, void *elem, void *ctx),
    void *ctx
);

#endif /* PROVE_HOF_H */
