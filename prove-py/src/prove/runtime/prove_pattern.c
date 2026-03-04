#include "prove_pattern.h"
#include <regex.h>

/* ── Helpers ─────────────────────────────────────────────────── */

/* Null-terminate a Prove_String into a temporary buffer. */
static char *_to_cstr(Prove_String *s, char *buf, size_t bufsz) {
    size_t len = (size_t)s->length;
    if (len >= bufsz) len = bufsz - 1;
    memcpy(buf, s->data, len);
    buf[len] = '\0';
    return buf;
}

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

    char tbuf[4096], pbuf[4096];
    _to_cstr(text, tbuf, sizeof(tbuf));
    _to_cstr(pattern, pbuf, sizeof(pbuf));

    regex_t regex;
    if (regcomp(&regex, pbuf, REG_EXTENDED) != 0) return false;

    regmatch_t match;
    int rc = regexec(&regex, tbuf, 1, &match, 0);
    regfree(&regex);

    if (rc != 0) return false;
    /* Full match: match spans entire string */
    return match.rm_so == 0 && match.rm_eo == (regoff_t)text->length;
}

/* ── search ──────────────────────────────────────────────────── */

Prove_Option_Prove_Matchptr prove_pattern_search(Prove_String *text, Prove_String *pattern) {
    if (!text || !pattern)
        return Prove_Option_Prove_Matchptr_none();

    char tbuf[4096], pbuf[4096];
    _to_cstr(text, tbuf, sizeof(tbuf));
    _to_cstr(pattern, pbuf, sizeof(pbuf));

    regex_t regex;
    if (regcomp(&regex, pbuf, REG_EXTENDED) != 0)
        return Prove_Option_Prove_Matchptr_none();

    regmatch_t match;
    int rc = regexec(&regex, tbuf, 1, &match, 0);
    regfree(&regex);

    if (rc != 0)
        return Prove_Option_Prove_Matchptr_none();

    Prove_Match *m = _make_match(text, (int64_t)match.rm_so, (int64_t)match.rm_eo);
    return Prove_Option_Prove_Matchptr_some(m);
}

/* ── find_all ────────────────────────────────────────────────── */

Prove_List *prove_pattern_find_all(Prove_String *text, Prove_String *pattern) {
    Prove_List *result = prove_list_new(sizeof(Prove_Match *), 8);
    if (!text || !pattern) return result;

    char tbuf[4096], pbuf[4096];
    _to_cstr(text, tbuf, sizeof(tbuf));
    _to_cstr(pattern, pbuf, sizeof(pbuf));

    regex_t regex;
    if (regcomp(&regex, pbuf, REG_EXTENDED) != 0) return result;

    const char *cursor = tbuf;
    int64_t offset = 0;
    regmatch_t match;

    while (regexec(&regex, cursor, 1, &match, 0) == 0) {
        int64_t start = offset + (int64_t)match.rm_so;
        int64_t end = offset + (int64_t)match.rm_eo;
        Prove_Match *m = _make_match(text, start, end);
        prove_list_push(&result, &m);

        /* Advance past match (avoid infinite loop on zero-length match) */
        int64_t advance = (int64_t)match.rm_eo;
        if (advance == (int64_t)match.rm_so) advance++;
        cursor += advance;
        offset += advance;

        if (*cursor == '\0') break;
    }

    regfree(&regex);
    return result;
}

/* ── replace ─────────────────────────────────────────────────── */

Prove_String *prove_pattern_replace(Prove_String *text, Prove_String *pattern, Prove_String *replacement) {
    if (!text || !pattern || !replacement) return text ? prove_string_new(text->data, text->length)
                                                        : prove_string_from_cstr("");

    char tbuf[4096], pbuf[4096];
    _to_cstr(text, tbuf, sizeof(tbuf));
    _to_cstr(pattern, pbuf, sizeof(pbuf));

    regex_t regex;
    if (regcomp(&regex, pbuf, REG_EXTENDED) != 0)
        return prove_string_new(text->data, text->length);

    /* Build result by replacing all occurrences */
    char result[8192];
    int rpos = 0;
    const char *cursor = tbuf;
    regmatch_t match;

    while (regexec(&regex, cursor, 1, &match, 0) == 0) {
        /* Copy text before match */
        int pre = match.rm_so;
        if (rpos + pre < (int)sizeof(result)) {
            memcpy(result + rpos, cursor, (size_t)pre);
            rpos += pre;
        }
        /* Copy replacement */
        int64_t rlen = replacement->length;
        if (rpos + (int)rlen < (int)sizeof(result)) {
            memcpy(result + rpos, replacement->data, (size_t)rlen);
            rpos += (int)rlen;
        }

        int advance = match.rm_eo;
        if (advance == match.rm_so) advance++;
        cursor += advance;

        if (*cursor == '\0') break;
    }
    /* Copy remainder */
    int remain = (int)strlen(cursor);
    if (rpos + remain < (int)sizeof(result)) {
        memcpy(result + rpos, cursor, (size_t)remain);
        rpos += remain;
    }

    regfree(&regex);
    return prove_string_new(result, rpos);
}

/* ── split ───────────────────────────────────────────────────── */

Prove_List *prove_pattern_split(Prove_String *text, Prove_String *pattern) {
    Prove_List *result = prove_list_new(sizeof(Prove_String *), 8);
    if (!text || !pattern) {
        if (text) {
            Prove_String *copy = prove_string_new(text->data, text->length);
            prove_list_push(&result, &copy);
        }
        return result;
    }

    char tbuf[4096], pbuf[4096];
    _to_cstr(text, tbuf, sizeof(tbuf));
    _to_cstr(pattern, pbuf, sizeof(pbuf));

    regex_t regex;
    if (regcomp(&regex, pbuf, REG_EXTENDED) != 0) {
        Prove_String *copy = prove_string_new(text->data, text->length);
        prove_list_push(&result, &copy);
        return result;
    }

    const char *cursor = tbuf;
    int64_t offset = 0;
    regmatch_t match;

    while (regexec(&regex, cursor, 1, &match, 0) == 0) {
        /* Segment before match */
        int64_t seg_start = offset;
        int64_t seg_end = offset + (int64_t)match.rm_so;
        Prove_String *seg = prove_string_new(text->data + seg_start, seg_end - seg_start);
        prove_list_push(&result, &seg);

        int64_t advance = (int64_t)match.rm_eo;
        if (advance == (int64_t)match.rm_so) advance++;
        cursor += advance;
        offset += advance;

        if (*cursor == '\0') { offset = text->length; break; }
    }

    /* Remainder */
    if (offset <= text->length) {
        Prove_String *seg = prove_string_new(text->data + offset, text->length - offset);
        prove_list_push(&result, &seg);
    }

    regfree(&regex);
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
