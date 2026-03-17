#ifndef PROVE_PATTERN_H
#define PROVE_PATTERN_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_option.h"

/* ── Match type ──────────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    int64_t       start;
    int64_t       end;
    Prove_String *text;
} Prove_Match;

/* ── Pattern functions ───────────────────────────────────────── */

bool          prove_pattern_match(Prove_String *text, Prove_String *pattern);
Prove_Option  prove_pattern_search(Prove_String *text, Prove_String *pattern);
Prove_List   *prove_pattern_find_all(Prove_String *text, Prove_String *pattern);
Prove_String *prove_pattern_replace(Prove_String *text, Prove_String *pattern, Prove_String *replacement);
Prove_List   *prove_pattern_split(Prove_String *text, Prove_String *pattern);

/* ── Match accessors ─────────────────────────────────────────── */

Prove_String *prove_pattern_text(Prove_Match *m);
int64_t       prove_pattern_start(Prove_Match *m);
int64_t       prove_pattern_end(Prove_Match *m);

#endif /* PROVE_PATTERN_H */
