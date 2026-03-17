#ifndef PROVE_CHARACTER_H
#define PROVE_CHARACTER_H

#include "prove_runtime.h"
#include "prove_string.h"

/* ── Character classification ────────────────────────────────── */

bool prove_character_alpha(char c);
bool prove_character_digit(char c);
bool prove_character_alnum(char c);
bool prove_character_upper(char c);
bool prove_character_lower(char c);
bool prove_character_space(char c);

/* ── String-to-character access ──────────────────────────────── */

char prove_character_at(Prove_String *s, int64_t index);

#endif /* PROVE_CHARACTER_H */
