#include "prove_pattern.h"
#include "prove_text.h"
#include <regex.h>

/* ── Regex cache (4 slots, direct-mapped by hash) ────────────── */

#define REGEX_CACHE_SIZE 4

typedef struct {
    char    *pattern;  /* malloc'd copy of pattern string */
    regex_t  regex;
    bool     valid;
} RegexCacheEntry;

static RegexCacheEntry _regex_cache[REGEX_CACHE_SIZE];

static uint32_t _hash_str(const char *s) {
    uint32_t h = 5381;
    while (*s) h = h * 33 + (unsigned char)*s++;
    return h;
}

static regex_t *_get_regex(const char *pattern) {
    uint32_t h = _hash_str(pattern);
    int slot = (int)(h % REGEX_CACHE_SIZE);
    RegexCacheEntry *e = &_regex_cache[slot];

    if (e->valid && strcmp(e->pattern, pattern) == 0) {
        return &e->regex;  /* cache hit */
    }

    /* Evict old entry if present */
    if (e->valid) {
        regfree(&e->regex);
        free(e->pattern);
        e->valid = false;
        e->pattern = NULL;
    }

    if (regcomp(&e->regex, pattern, REG_EXTENDED) != 0) {
        return NULL;
    }

    e->pattern = strdup(pattern);
    e->valid = true;
    return &e->regex;
}

/* ── Helpers ─────────────────────────────────────────────────── */

static Prove_Match *_make_match(Prove_String *text, int64_t start, int64_t end) {
    Prove_Match *m = (Prove_Match *)prove_alloc(sizeof(Prove_Match));
    m->start = start;
    m->end = end;
    m->text = prove_string_new(text->data + start, end - start);
    return m;
}

/* ── match ───────────────────────────────────────────────────── */

bool prove_pattern_match(Prove_String *text, Prove_String *pattern) {
    if (!text || !pattern) return false;

    /* Prove_String.data is already null-terminated */
    regex_t *re = _get_regex(pattern->data);
    if (!re) return false;

    regmatch_t match;
    int rc = regexec(re, text->data, 1, &match, 0);

    if (rc != 0) return false;
    /* Full match: match spans entire string */
    return match.rm_so == 0 && match.rm_eo == (regoff_t)text->length;
}

/* ── search ──────────────────────────────────────────────────── */

Prove_Option prove_pattern_search(Prove_String *text, Prove_String *pattern) {
    if (!text || !pattern)
        return prove_option_none();

    regex_t *re = _get_regex(pattern->data);
    if (!re)
        return prove_option_none();

    regmatch_t match;
    int rc = regexec(re, text->data, 1, &match, 0);

    if (rc != 0)
        return prove_option_none();

    Prove_Match *m = _make_match(text, (int64_t)match.rm_so, (int64_t)match.rm_eo);
    return prove_option_some((Prove_Value *)m);
}

/* ── find_all ────────────────────────────────────────────────── */

Prove_List *prove_pattern_find_all(Prove_String *text, Prove_String *pattern) {
    Prove_List *result = prove_list_new(8);
    if (!text || !pattern) return result;

    regex_t *re = _get_regex(pattern->data);
    if (!re) return result;

    const char *cursor = text->data;
    int64_t offset = 0;
    regmatch_t match;

    while (regexec(re, cursor, 1, &match, 0) == 0) {
        int64_t start = offset + (int64_t)match.rm_so;
        int64_t end = offset + (int64_t)match.rm_eo;
        Prove_Match *m = _make_match(text, start, end);
        prove_list_push(result, m);

        /* Advance past match (avoid infinite loop on zero-length match) */
        int64_t advance = (int64_t)match.rm_eo;
        if (advance == (int64_t)match.rm_so) advance++;
        cursor += advance;
        offset += advance;

        if (*cursor == '\0') break;
    }

    return result;
}

/* ── replace (dynamic buffer via Builder) ────────────────────── */

Prove_String *prove_pattern_replace(Prove_String *text, Prove_String *pattern, Prove_String *replacement) {
    if (!text || !pattern || !replacement) return text ? prove_string_new(text->data, text->length)
                                                        : prove_string_from_cstr("");

    regex_t *re = _get_regex(pattern->data);
    if (!re)
        return prove_string_new(text->data, text->length);

    /* Build result using Builder (no fixed-size buffer limit) */
    Prove_Builder *b = prove_text_builder();
    const char *cursor = text->data;
    regmatch_t match;

    while (regexec(re, cursor, 1, &match, 0) == 0) {
        /* Copy text before match */
        if (match.rm_so > 0) {
            Prove_String *pre = prove_string_new(cursor, (int64_t)match.rm_so);
            b = prove_text_write(b, pre);
            prove_release(pre);
        }
        /* Copy replacement */
        b = prove_text_write(b, replacement);

        int advance = match.rm_eo;
        if (advance == match.rm_so) {
            /* Zero-length match: copy one char and advance */
            if (cursor[advance] != '\0') {
                b = prove_text_write_char(b, cursor[advance]);
            }
            advance++;
        }
        cursor += advance;

        if (*cursor == '\0') break;
    }
    /* Copy remainder */
    if (*cursor != '\0') {
        int remain = (int)strlen(cursor);
        Prove_String *rem = prove_string_new(cursor, (int64_t)remain);
        b = prove_text_write(b, rem);
        prove_release(rem);
    }

    Prove_String *result = prove_text_build(b);
    free(b);
    return result;
}

/* ── split ───────────────────────────────────────────────────── */

Prove_List *prove_pattern_split(Prove_String *text, Prove_String *pattern) {
    Prove_List *result = prove_list_new(8);
    if (!text || !pattern) {
        if (text) {
            Prove_String *copy = prove_string_new(text->data, text->length);
            prove_list_push(result, copy);
        }
        return result;
    }

    regex_t *re = _get_regex(pattern->data);
    if (!re) {
        Prove_String *copy = prove_string_new(text->data, text->length);
        prove_list_push(result, copy);
        return result;
    }

    const char *cursor = text->data;
    int64_t offset = 0;
    regmatch_t match;

    while (regexec(re, cursor, 1, &match, 0) == 0) {
        /* Segment before match */
        int64_t seg_start = offset;
        int64_t seg_end = offset + (int64_t)match.rm_so;
        Prove_String *seg = prove_string_new(text->data + seg_start, seg_end - seg_start);
        prove_list_push(result, seg);

        int64_t advance = (int64_t)match.rm_eo;
        if (advance == (int64_t)match.rm_so) advance++;
        cursor += advance;
        offset += advance;

        if (*cursor == '\0') { offset = text->length; break; }
    }

    /* Remainder */
    if (offset <= text->length) {
        Prove_String *seg = prove_string_new(text->data + offset, text->length - offset);
        prove_list_push(result, seg);
    }

    return result;
}

/* ── Match accessors ─────────────────────────────────────────── */

Prove_String *prove_pattern_text(Prove_Match *m) {
    if (!m) prove_panic("Pattern.text: null match");
    return m->text;
}

int64_t prove_pattern_start(Prove_Match *m) {
    if (!m) prove_panic("Pattern.start: null match");
    return m->start;
}

int64_t prove_pattern_end(Prove_Match *m) {
    if (!m) prove_panic("Pattern.end: null match");
    return m->end;
}
