#ifndef PROVE_MATH_H
#define PROVE_MATH_H

#include "prove_runtime.h"

/* ── Absolute value ──────────────────────────────────────────── */

int64_t prove_math_abs_int(int64_t n);
double  prove_math_abs_float(double x);

/* ── Min / Max ───────────────────────────────────────────────── */

int64_t prove_math_min_int(int64_t a, int64_t b);
double  prove_math_min_float(double a, double b);
int64_t prove_math_max_int(int64_t a, int64_t b);
double  prove_math_max_float(double a, double b);

/* ── Clamp ───────────────────────────────────────────────────── */

int64_t prove_math_clamp_int(int64_t val, int64_t lo, int64_t hi);
double  prove_math_clamp_float(double val, double lo, double hi);

/* ── Floating-point math ─────────────────────────────────────── */

double  prove_math_sqrt(double x);
double  prove_math_pow(double base, double exp);
int64_t prove_math_floor(double x);
int64_t prove_math_ceil(double x);
int64_t prove_math_round(double x);
double  prove_math_log(double x);

/* ── Scale:N rounding ───────────────────────────────────────── */

#include <math.h>

static inline double prove_decimal_round(double val, int scale) {
    double factor = pow(10.0, (double)scale);
    return round(val * factor) / factor;
}

#endif /* PROVE_MATH_H */
