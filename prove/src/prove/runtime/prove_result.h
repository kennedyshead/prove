#ifndef PROVE_RESULT_H
#define PROVE_RESULT_H

#include "prove_runtime.h"
#include "prove_string.h"

/* ── Result type (simplified for POC) ─────────────────────────── */

typedef struct {
    uint8_t       tag;   /* 0 = Ok, 1 = Err */
    Prove_String *error; /* NULL when Ok */
} Prove_Result;

static inline Prove_Result prove_result_ok(void) {
    Prove_Result r;
    r.tag = 0;
    r.error = NULL;
    return r;
}

static inline Prove_Result prove_result_err(Prove_String *msg) {
    Prove_Result r;
    r.tag = 1;
    r.error = msg;
    return r;
}

static inline bool prove_result_is_ok(Prove_Result r) {
    return r.tag == 0;
}

static inline bool prove_result_is_err(Prove_Result r) {
    return r.tag == 1;
}

#endif /* PROVE_RESULT_H */
