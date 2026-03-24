#include "prove_parse.h"
#include <regex.h>
#include <string.h>

/* ═══════════════════════════════════════════════════════════════════
   Rule constructor
   ═══════════════════════════════════════════════════════════════════ */

Prove_Rule *prove_parse_rule(Prove_String *pattern, int64_t kind) {
    Prove_Rule *r = (Prove_Rule *)prove_alloc(sizeof(Prove_Rule));
    r->pattern = pattern;
    r->kind    = kind;
    return r;
}

/* ═══════════════════════════════════════════════════════════════════
   Generic tokenizer — matches rules in priority order
   ═══════════════════════════════════════════════════════════════════ */

Prove_List *prove_parse_tokens(Prove_String *source, Prove_List *rules) {
    const char *src = source->data;
    int64_t len = source->length;
    int64_t nrules = rules->length;
    Prove_List *result = prove_list_new(16);

    /* Pre-compile all rule patterns. */
    regex_t *compiled = (regex_t *)malloc((size_t)nrules * sizeof(regex_t));
    bool *valid = (bool *)calloc((size_t)nrules, sizeof(bool));

    for (int64_t r = 0; r < nrules; r++) {
        Prove_Rule *rule = (Prove_Rule *)prove_list_get(rules, r);
        if (regcomp(&compiled[r], rule->pattern->data, REG_EXTENDED) == 0) {
            valid[r] = true;
        }
    }

    int64_t pos = 0;
    while (pos < len) {
        int64_t best_len = 0;
        int64_t best_kind = -1;

        /* Try each rule; longest match wins, first rule breaks ties. */
        for (int64_t r = 0; r < nrules; r++) {
            if (!valid[r]) continue;

            regmatch_t m;
            /* Match must start at current position (anchor via REG_STARTEND). */
            m.rm_so = (regoff_t)pos;
            m.rm_eo = (regoff_t)len;
            int rc = regexec(&compiled[r], src, 1, &m, REG_STARTEND);
            if (rc != 0 || m.rm_so != (regoff_t)pos) continue;

            int64_t mlen = (int64_t)(m.rm_eo - m.rm_so);
            if (mlen > best_len) {
                best_len = mlen;
                Prove_Rule *rule = (Prove_Rule *)prove_list_get(rules, r);
                best_kind = rule->kind;
            }
        }

        if (best_len == 0) {
            /* No rule matched — skip one byte as unknown (kind -1). */
            Prove_Token *tok = (Prove_Token *)prove_alloc(sizeof(Prove_Token));
            tok->text  = prove_string_new(src + pos, 1);
            tok->start = pos;
            tok->end   = pos + 1;
            tok->kind  = -1;
            prove_list_push(result, tok);
            pos++;
        } else {
            Prove_Token *tok = (Prove_Token *)prove_alloc(sizeof(Prove_Token));
            tok->text  = prove_string_new(src + pos, best_len);
            tok->start = pos;
            tok->end   = pos + best_len;
            tok->kind  = best_kind;
            prove_list_push(result, tok);
            pos += best_len;
        }
    }

    /* Free compiled patterns. */
    for (int64_t r = 0; r < nrules; r++) {
        if (valid[r]) regfree(&compiled[r]);
    }
    free(compiled);
    free(valid);

    return result;
}

/* ═══════════════════════════════════════════════════════════════════
   Token accessors
   ═══════════════════════════════════════════════════════════════════ */

Prove_String *prove_parse_token_text(Prove_Token *t) {
    return t->text;
}

int64_t prove_parse_token_start(Prove_Token *t) {
    return t->start;
}

int64_t prove_parse_token_end(Prove_Token *t) {
    return t->end;
}

int64_t prove_parse_token_kind(Prove_Token *t) {
    return t->kind;
}
