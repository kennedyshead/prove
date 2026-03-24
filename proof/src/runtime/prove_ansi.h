#ifndef PROVE_ANSI_H
#define PROVE_ANSI_H

#include "prove_string.h"

/* Convert a Color or TextStyle name (e.g. "red", "bold") to its
 * ANSI SGR escape sequence (e.g. "\033[31m", "\033[1m").
 * Returns empty string for unknown names. */
Prove_String *prove_ansi_escape(Prove_String *name);

#endif /* PROVE_ANSI_H */
