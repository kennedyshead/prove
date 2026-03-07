#ifndef PROVE_ERROR_H
#define PROVE_ERROR_H

#include "prove_runtime.h"
#include "prove_result.h"
#include "prove_option.h"
#include "prove_string.h"

/* ── Result validators ───────────────────────────────────────── */

static inline bool prove_error_ok(Prove_Result r) {
    return r.tag == 0;
}

static inline bool prove_error_err(Prove_Result r) {
    return r.tag == 1;
}

/* ── Option validators ───────────────────────────────────────── */
/* Options are monomorphized but all share tag at offset 0:
   tag == 1 means Some, tag == 0 means None.
   Guard the PROVE_DEFINE_OPTION calls so they don't conflict
   with prove_list_ops.h which defines the same types. */

#ifndef PROVE_OPTION_INT64_T_DEFINED
#define PROVE_OPTION_INT64_T_DEFINED
PROVE_DEFINE_OPTION(int64_t, Prove_Option_int64_t)
#endif

#ifndef PROVE_OPTION_STRINGPTR_DEFINED
#define PROVE_OPTION_STRINGPTR_DEFINED
PROVE_DEFINE_OPTION(Prove_String*, Prove_Option_Prove_Stringptr)
#endif

static inline bool prove_error_some_int(Prove_Option_int64_t o) {
    return o.tag == 1;
}

static inline bool prove_error_none_int(Prove_Option_int64_t o) {
    return o.tag == 0;
}

static inline bool prove_error_some_str(Prove_Option_Prove_Stringptr o) {
    return o.tag == 1;
}

static inline bool prove_error_none_str(Prove_Option_Prove_Stringptr o) {
    return o.tag == 0;
}

/* ── unwrap_or ───────────────────────────────────────────────── */

static inline int64_t prove_error_unwrap_or_int(Prove_Option_int64_t o, int64_t def) {
    return o.tag == 1 ? o.value : def;
}

static inline Prove_String *prove_error_unwrap_or_str(Prove_Option_Prove_Stringptr o, Prove_String *def) {
    return o.tag == 1 ? o.value : def;
}

/* ── unwrap ──────────────────────────────────────────────────── */

static inline int64_t prove_error_unwrap_int(Prove_Option_int64_t o) {
    return Prove_Option_int64_t_unwrap(o);
}

static inline Prove_String *prove_error_unwrap_str(Prove_Option_Prove_Stringptr o) {
    return Prove_Option_Prove_Stringptr_unwrap(o);
}

#endif /* PROVE_ERROR_H */
