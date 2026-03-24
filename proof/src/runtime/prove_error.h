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

/* ── Unified Option validators ───────────────────────────────── */

static inline bool prove_error_some(Prove_Option o) {
    return o.tag == 1;
}

static inline bool prove_error_none(Prove_Option o) {
    return o.tag == 0;
}

/* ── Typed Option validators (aliases for overload dispatch) ── */

#define prove_error_some_int prove_error_some
#define prove_error_some_str prove_error_some
#define prove_error_some_float prove_error_some
#define prove_error_some_decimal prove_error_some
#define prove_error_some_bool prove_error_some
#define prove_error_none_int prove_error_none
#define prove_error_none_str prove_error_none
#define prove_error_none_float prove_error_none
#define prove_error_none_decimal prove_error_none
#define prove_error_none_bool prove_error_none

/* ── Typed unwrap (extract inner type from Option.value) ───── */

static inline int64_t prove_error_unwrap_int(Prove_Option o) {
    if (o.tag == 0) prove_panic("unwrap on None option");
    return (int64_t)(intptr_t)o.value;
}

static inline Prove_String *prove_error_unwrap_str(Prove_Option o) {
    if (o.tag == 0) prove_panic("unwrap on None option");
    return (Prove_String *)o.value;
}

/* ── Typed unwrap (bool) ─────────────────────────────────────── */

static inline bool prove_error_unwrap_bool(Prove_Option o) {
    if (o.tag == 0) prove_panic("unwrap on None option");
    return (bool)(intptr_t)o.value;
}

/* ── Typed unwrap (float) ────────────────────────────────────── */

static inline double prove_error_unwrap_float(Prove_Option o) {
    if (o.tag == 0) prove_panic("unwrap on None option");
    double d;
    memcpy(&d, &o.value, sizeof(d));
    return d;
}

/* ── Typed unwrap_or ─────────────────────────────────────────── */

static inline int64_t prove_error_unwrap_or_int(Prove_Option o, int64_t def) {
    return o.tag == 1 ? (int64_t)(intptr_t)o.value : def;
}

static inline Prove_String *prove_error_unwrap_or_str(Prove_Option o, Prove_String *def) {
    return o.tag == 1 ? (Prove_String *)o.value : def;
}

static inline bool prove_error_unwrap_or_bool(Prove_Option o, bool def) {
    return o.tag == 1 ? (bool)(intptr_t)o.value : def;
}

static inline double prove_error_unwrap_or_float(Prove_Option o, double def) {
    if (o.tag != 1) return def;
    double d;
    memcpy(&d, &o.value, sizeof(d));
    return d;
}

/* ── Unified unwrap ──────────────────────────────────────────── */

static inline Prove_Value *prove_error_unwrap(Prove_Option o) {
    return prove_option_unwrap(o);
}

/* ── Unified unwrap_or ───────────────────────────────────────── */

static inline Prove_Value *prove_error_unwrap_or(Prove_Option o, Prove_Value *def) {
    return o.tag == 1 ? o.value : def;
}

#endif /* PROVE_ERROR_H */
