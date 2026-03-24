#ifndef PROVE_MATH_H
#define PROVE_MATH_H

#include "prove_runtime.h"
#include <math.h>
#include <stdlib.h>

/* ── Absolute value ──────────────────────────────────────────── */

static inline int64_t prove_math_abs_int(int64_t n) {
    return llabs(n);
}

static inline double prove_math_abs_float(double x) {
    return fabs(x);
}

/* ── Min / Max ───────────────────────────────────────────────── */

static inline int64_t prove_math_min_int(int64_t a, int64_t b) {
    return a < b ? a : b;
}

static inline double prove_math_min_float(double a, double b) {
    return fmin(a, b);
}

static inline int64_t prove_math_max_int(int64_t a, int64_t b) {
    return a > b ? a : b;
}

static inline double prove_math_max_float(double a, double b) {
    return fmax(a, b);
}

/* ── Clamp ───────────────────────────────────────────────────── */

static inline int64_t prove_math_clamp_int(int64_t val, int64_t lo, int64_t hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

static inline double prove_math_clamp_float(double val, double lo, double hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

/* ── Floating-point math ─────────────────────────────────────── */

static inline double prove_math_sqrt(double x) {
    return sqrt(x);
}

static inline double prove_math_pow(double base, double exp) {
    return pow(base, exp);
}

static inline int64_t prove_math_floor(double x) {
    return (int64_t)floor(x);
}

static inline int64_t prove_math_ceil(double x) {
    return (int64_t)ceil(x);
}

static inline int64_t prove_math_round(double x) {
    return (int64_t)round(x);
}

static inline double prove_math_log(double x) {
    return log(x);
}

static inline double prove_math_log10(double x) {
    return log10(x);
}

/* ── Trigonometry ───────────────────────────────────────────── */

static inline double prove_math_sin(double x) {
    return sin(x);
}

static inline double prove_math_cos(double x) {
    return cos(x);
}

static inline double prove_math_tan(double x) {
    return tan(x);
}

static inline double prove_math_asin(double x) {
    return asin(x);
}

static inline double prove_math_acos(double x) {
    return acos(x);
}

static inline double prove_math_atan(double x) {
    return atan(x);
}

static inline double prove_math_atan2(double y, double x) {
    return atan2(y, x);
}

/* ── Exponential / Logarithmic ─────────────────────────────── */

static inline double prove_math_exp(double x) {
    return exp(x);
}

static inline double prove_math_log2(double x) {
    return log2(x);
}

/* ── Constants ─────────────────────────────────────────────── */

static inline double prove_math_pi(void) {
    return M_PI;
}

static inline double prove_math_e(void) {
    return M_E;
}

/* ── Scale:N rounding ───────────────────────────────────────── */

static inline double prove_decimal_round(double val, int scale) {
    double factor = pow(10.0, (double)scale);
    return round(val * factor) / factor;
}

#endif /* PROVE_MATH_H */
