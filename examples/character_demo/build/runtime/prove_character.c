#include "prove_character.h"
#include <ctype.h>

/* ── Character classification ────────────────────────────────── */

bool prove_character_alpha(char c) {
    return isalpha((unsigned char)c) != 0;
}

bool prove_character_digit(char c) {
    return isdigit((unsigned char)c) != 0;
}

bool prove_character_alnum(char c) {
    return isalnum((unsigned char)c) != 0;
}

bool prove_character_upper(char c) {
    return isupper((unsigned char)c) != 0;
}

bool prove_character_lower(char c) {
    return islower((unsigned char)c) != 0;
}

bool prove_character_space(char c) {
    return isspace((unsigned char)c) != 0;
}

/* ── String-to-character access ──────────────────────────────── */

char prove_character_at(Prove_String *s, int64_t index) {
    if (!s || index < 0 || index >= s->length) {
        prove_panic("Character.at: index out of bounds");
    }
    return s->data[index];
}
