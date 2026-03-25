#ifndef PROVE_CONVERT_H
#define PROVE_CONVERT_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_result.h"

/* ── String → Integer ────────────────────────────────────────── */

Prove_Result prove_convert_integer_str(Prove_String *s);

/* ── Float → Integer ─────────────────────────────────────────── */

int64_t prove_convert_integer_float(double x);

/* ── String → Float ──────────────────────────────────────────── */

Prove_Result prove_convert_float_str(Prove_String *s);

/* ── Integer → Float ─────────────────────────────────────────── */

double prove_convert_float_int(int64_t n);

/* ── To String ───────────────────────────────────────────────── */

Prove_String *prove_convert_string_int(int64_t n);
Prove_String *prove_convert_string_float(double x);
Prove_String *prove_convert_string_bool(bool b);

/* ── Decimal aliases (Decimal = double, same as Float) ──────── */

static inline int64_t prove_convert_integer_decimal(double x) {
    return prove_convert_integer_float(x);
}

static inline Prove_Result prove_convert_decimal_str(Prove_String *s) {
    return prove_convert_float_str(s);
}

static inline double prove_convert_decimal_int(int64_t n) {
    return prove_convert_float_int(n);
}

static inline double prove_convert_float_decimal(double x) { return x; }

/* ── Boolean ↔ Integer ───────────────────────────────────────── */

static inline int64_t prove_convert_integer_bool(bool b) { return b ? 1 : 0; }
static inline bool prove_convert_boolean_int(int64_t n) { return n != 0; }

/* ── String → Boolean ───────────────────────────────────────── */

Prove_Result prove_convert_boolean_str(Prove_String *s);

/* ── Byte → String ──────────────────────────────────────────── */

Prove_String *prove_convert_string_byte(uint8_t b);

/* ── Character ↔ Integer ─────────────────────────────────────── */

int64_t prove_convert_code(char c);
char    prove_convert_character(int64_t n);

/* ── Position → String ──────────────────────────────────────── */

/* Forward-declare to avoid pulling in prove_terminal.h */
#ifndef PROVE_POSITION_DEFINED
#define PROVE_POSITION_DEFINED
typedef struct { int64_t x; int64_t y; } Prove_Position;
#endif

Prove_String *prove_convert_string_position(Prove_Position pos);

#endif /* PROVE_CONVERT_H */
