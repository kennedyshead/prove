#ifndef PROVE_OPTION_H
#define PROVE_OPTION_H

#include "prove_runtime.h"

/* ── Unified Option<Value> ────────────────────────────────────── */

typedef struct {
    uint8_t       tag;    /* 0 = None, 1 = Some */
    Prove_Value  *value;
} Prove_Option;

static inline Prove_Option prove_option_some(Prove_Value *v) {
    return (Prove_Option){1, v};
}

static inline Prove_Option prove_option_none(void) {
    return (Prove_Option){0, NULL};
}

static inline bool prove_option_is_some(Prove_Option o) {
    return o.tag == 1;
}

static inline bool prove_option_is_none(Prove_Option o) {
    return o.tag == 0;
}

static inline Prove_Value *prove_option_unwrap(Prove_Option o) {
    if (o.tag == 0) prove_panic("unwrap on None option");
    return o.value;
}

#endif /* PROVE_OPTION_H */
