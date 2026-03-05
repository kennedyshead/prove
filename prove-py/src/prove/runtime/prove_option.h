#ifndef PROVE_OPTION_H
#define PROVE_OPTION_H

#include "prove_runtime.h"
#include "prove_string.h"

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

/* ── Common Option instantiations ──────────────────────────────── */

#ifndef PROVE_OPTION_INT64_T_DEFINED
#define PROVE_OPTION_INT64_T_DEFINED
PROVE_DEFINE_OPTION(int64_t, Prove_Option_int64_t)
#endif

#ifndef PROVE_OPTION_STRINGPTR_DEFINED
#define PROVE_OPTION_STRINGPTR_DEFINED
PROVE_DEFINE_OPTION(Prove_String*, Prove_Option_Prove_Stringptr)
#endif

#endif /* PROVE_OPTION_H */
