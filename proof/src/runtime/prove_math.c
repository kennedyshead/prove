#include "prove_math.h"
#include <math.h>
#include <stdlib.h>

/* ── Absolute value ──────────────────────────────────────────── */

int64_t prove_math_abs_int(int64_t n) {
    return llabs(n);
}

double prove_math_abs_float(double x) {
    return fabs(x);
}

/* ── Min / Max ───────────────────────────────────────────────── */

int64_t prove_math_min_int(int64_t a, int64_t b) {
    return a < b ? a : b;
}

double prove_math_min_float(double a, double b) {
    return fmin(a, b);
}

int64_t prove_math_max_int(int64_t a, int64_t b) {
    return a > b ? a : b;
}

double prove_math_max_float(double a, double b) {
    return fmax(a, b);
}

/* ── Clamp ───────────────────────────────────────────────────── */

int64_t prove_math_clamp_int(int64_t val, int64_t lo, int64_t hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

double prove_math_clamp_float(double val, double lo, double hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

/* ── Floating-point math ─────────────────────────────────────── */

double prove_math_sqrt(double x) {
    return sqrt(x);
}

double prove_math_pow(double base, double exp) {
    return pow(base, exp);
}

int64_t prove_math_floor(double x) {
    return (int64_t)floor(x);
}

int64_t prove_math_ceil(double x) {
    return (int64_t)ceil(x);
}

int64_t prove_math_round(double x) {
    return (int64_t)round(x);
}

double prove_math_log(double x) {
    return log(x);
}
