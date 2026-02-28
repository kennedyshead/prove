#ifndef PROVE_RESULT_H
#define PROVE_RESULT_H

#include "prove_runtime.h"
#include "prove_string.h"

/* ── Result type with success payload ────────────────────────── */

typedef struct {
    uint8_t       tag;   /* 0 = Ok, 1 = Err */
    Prove_String *error; /* NULL when Ok */
    union {
        int64_t ok_int;
        double  ok_double;
        void   *ok_ptr;
    };
} Prove_Result;

static inline Prove_Result prove_result_ok(void) {
    Prove_Result r;
    r.tag = 0;
    r.error = NULL;
    r.ok_ptr = NULL;
    return r;
}

static inline Prove_Result prove_result_ok_int(int64_t val) {
    Prove_Result r;
    r.tag = 0;
    r.error = NULL;
    r.ok_int = val;
    return r;
}

static inline Prove_Result prove_result_ok_double(double val) {
    Prove_Result r;
    r.tag = 0;
    r.error = NULL;
    r.ok_double = val;
    return r;
}

static inline Prove_Result prove_result_ok_ptr(void *val) {
    Prove_Result r;
    r.tag = 0;
    r.error = NULL;
    r.ok_ptr = val;
    return r;
}

static inline Prove_Result prove_result_err(Prove_String *msg) {
    Prove_Result r;
    r.tag = 1;
    r.error = msg;
    r.ok_ptr = NULL;
    return r;
}

static inline bool prove_result_is_ok(Prove_Result r) {
    return r.tag == 0;
}

static inline bool prove_result_is_err(Prove_Result r) {
    return r.tag == 1;
}

static inline int64_t prove_result_unwrap_int(Prove_Result r) {
    if (r.tag != 0) prove_panic("unwrap on Err result");
    return r.ok_int;
}

static inline void *prove_result_unwrap_ptr(Prove_Result r) {
    if (r.tag != 0) prove_panic("unwrap on Err result");
    return r.ok_ptr;
}

#endif /* PROVE_RESULT_H */
