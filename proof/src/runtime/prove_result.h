#ifndef PROVE_RESULT_H
#define PROVE_RESULT_H

#include "prove_runtime.h"
#include "prove_string.h"

_Static_assert(sizeof(double) <= sizeof(intptr_t), "double must fit in intptr_t");

/* ── Unified Result<Value, Error> ────────────────────────────── */

typedef struct {
    uint8_t       tag;    /* 0 = Ok, 1 = Err */
    Prove_Value  *value;  /* ok value (tag==0) */
    Prove_String *error;  /* error message (tag==1), NULL when Ok */
} Prove_Result;

static inline Prove_Result prove_result_ok(void) {
    Prove_Result r;
    r.tag = 0;
    r.value = NULL;
    r.error = NULL;
    return r;
}

static inline Prove_Result prove_result_ok_val(Prove_Value *v) {
    Prove_Result r;
    r.tag = 0;
    r.value = v;
    r.error = NULL;
    return r;
}

static inline Prove_Result prove_result_err(Prove_String *msg) {
    Prove_Result r;
    r.tag = 1;
    r.value = NULL;
    r.error = msg;
    return r;
}

static inline bool prove_result_is_ok(Prove_Result r) {
    return r.tag == 0;
}

static inline bool prove_result_is_err(Prove_Result r) {
    return r.tag == 1;
}

static inline Prove_Value *prove_result_unwrap(Prove_Result r) {
    if (r.tag != 0) prove_panic("unwrap on Err result");
    return r.value;
}

/* Legacy compatibility — kept for internal runtime use */

static inline Prove_Result prove_result_ok_int(int64_t val) {
    Prove_Result r;
    r.tag = 0;
    /* Store raw int64_t via cast — only valid when caller knows the type */
    r.value = (Prove_Value *)(intptr_t)val;
    r.error = NULL;
    return r;
}

static inline Prove_Result prove_result_ok_ptr(void *val) {
    Prove_Result r;
    r.tag = 0;
    r.value = (Prove_Value *)val;
    r.error = NULL;
    return r;
}

static inline int64_t prove_result_unwrap_int(Prove_Result r) {
    if (r.tag != 0) prove_panic("unwrap on Err result");
    return (int64_t)(intptr_t)r.value;
}

static inline void *prove_result_unwrap_ptr(Prove_Result r) {
    if (r.tag != 0) prove_panic("unwrap on Err result");
    return (void *)r.value;
}

static inline Prove_Result prove_result_ok_double(double val) {
    Prove_Result r;
    r.tag = 0;
    /* Store double bits via memcpy through intptr_t */
    intptr_t tmp;
    memcpy(&tmp, &val, sizeof(double));
    r.value = (Prove_Value *)tmp;
    r.error = NULL;
    return r;
}

static inline double prove_result_unwrap_double(Prove_Result r) {
    if (r.tag != 0) prove_panic("unwrap on Err result");
    intptr_t tmp = (intptr_t)r.value;
    double val;
    memcpy(&val, &tmp, sizeof(double));
    return val;
}

#endif /* PROVE_RESULT_H */
