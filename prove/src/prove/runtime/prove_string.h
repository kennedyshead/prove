#ifndef PROVE_STRING_H
#define PROVE_STRING_H

#include "prove_runtime.h"

/* ── Prove_String ─────────────────────────────────────────────── */

typedef struct {
    Prove_Header header;
    int64_t      length;
    char         data[];  /* flexible array member */
} Prove_String;

Prove_String *prove_string_new(const char *src, int64_t len);
Prove_String *prove_string_from_cstr(const char *src);
Prove_String *prove_string_concat(Prove_String *a, Prove_String *b);
bool          prove_string_eq(Prove_String *a, Prove_String *b);
int64_t       prove_string_len(Prove_String *s);
Prove_String *prove_string_from_int(int64_t val);
Prove_String *prove_string_from_double(double val);
Prove_String *prove_string_from_bool(bool val);
Prove_String *prove_string_from_char(char val);

void prove_println(Prove_String *s);
void prove_print(Prove_String *s);
Prove_String *prove_readln(void);

#endif /* PROVE_STRING_H */
