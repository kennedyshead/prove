#ifndef PROVE_TEXT_H
#define PROVE_TEXT_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_option.h"

/* ── Option<Integer> for index_of ────────────────────────────── */

PROVE_DEFINE_OPTION(int64_t, Prove_Option_int64_t)

/* ── Builder type ────────────────────────────────────────────── */

typedef struct {
    Prove_Header header;
    int64_t      length;
    int64_t      capacity;
    char         data[];
} Prove_Builder;

/* ── String queries ──────────────────────────────────────────── */

int64_t       prove_text_length(Prove_String *s);
Prove_String *prove_text_slice(Prove_String *s, int64_t start, int64_t end);
bool          prove_text_starts_with(Prove_String *s, Prove_String *prefix);
bool          prove_text_ends_with(Prove_String *s, Prove_String *suffix);
bool          prove_text_contains(Prove_String *s, Prove_String *sub);
Prove_Option_int64_t prove_text_index_of(Prove_String *s, Prove_String *sub);

/* ── String transformations ──────────────────────────────────── */

Prove_List   *prove_text_split(Prove_String *s, Prove_String *sep);
Prove_String *prove_text_join(Prove_List *parts, Prove_String *sep);
Prove_String *prove_text_trim(Prove_String *s);
Prove_String *prove_text_to_lower(Prove_String *s);
Prove_String *prove_text_to_upper(Prove_String *s);
Prove_String *prove_text_replace(Prove_String *s, Prove_String *old_s, Prove_String *new_s);
Prove_String *prove_text_repeat(Prove_String *s, int64_t n);

/* ── Builder ─────────────────────────────────────────────────── */

Prove_Builder *prove_text_builder(void);
Prove_Builder *prove_text_write(Prove_Builder *b, Prove_String *s);
Prove_Builder *prove_text_write_char(Prove_Builder *b, char c);
Prove_String  *prove_text_build(Prove_Builder *b);
int64_t        prove_text_builder_length(Prove_Builder *b);

#endif /* PROVE_TEXT_H */
