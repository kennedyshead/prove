#ifndef PROVE_OPTION_H
#define PROVE_OPTION_H

#include "prove_runtime.h"

/* ── Option<T> monomorphization macro ─────────────────────────── */

#define PROVE_DEFINE_OPTION(T, Name) \
    typedef struct {                  \
        uint8_t tag; /* 0=None, 1=Some */ \
        T       value;                \
    } Name;                           \
    static inline Name Name##_some(T val) { \
        Name opt; opt.tag = 1; opt.value = val; return opt; \
    }                                 \
    static inline Name Name##_none(void) { \
        Name opt; opt.tag = 0; memset(&opt.value, 0, sizeof(T)); return opt; \
    }                                 \
    static inline bool Name##_is_some(Name opt) { return opt.tag == 1; } \
    static inline bool Name##_is_none(Name opt) { return opt.tag == 0; }

#endif /* PROVE_OPTION_H */
