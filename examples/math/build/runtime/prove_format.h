#ifndef PROVE_FORMAT_H
#define PROVE_FORMAT_H

#include "prove_runtime.h"
#include "prove_string.h"

/* ── Padding ─────────────────────────────────────────────────── */

Prove_String *prove_format_pad_left(Prove_String *s, int64_t width, char fill);
Prove_String *prove_format_pad_right(Prove_String *s, int64_t width, char fill);
Prove_String *prove_format_center(Prove_String *s, int64_t width, char fill);

/* ── Number formatting ───────────────────────────────────────── */

Prove_String *prove_format_hex(int64_t n);
Prove_String *prove_format_binary(int64_t n);
Prove_String *prove_format_octal(int64_t n);
Prove_String *prove_format_decimal(double x, int64_t places);

#endif /* PROVE_FORMAT_H */
