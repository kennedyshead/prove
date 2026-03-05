#include "prove_path.h"

/* ── Join ────────────────────────────────────────────────────── */

Prove_String *prove_path_join(Prove_String *base, Prove_String *part) {
    if (!base || base->length == 0) return part ? prove_string_new(part->data, part->length)
                                                 : prove_string_from_cstr("");
    if (!part || part->length == 0) return prove_string_new(base->data, base->length);

    /* If part is absolute, return it */
    if (part->data[0] == '/') return prove_string_new(part->data, part->length);

    /* Check if base ends with / */
    bool has_sep = base->data[base->length - 1] == '/';
    int64_t total = base->length + (!has_sep ? 1 : 0) + part->length;

    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)total + 1);
    result->length = total;

    char *dst = result->data;
    memcpy(dst, base->data, (size_t)base->length);
    dst += base->length;
    if (!has_sep) *dst++ = '/';
    memcpy(dst, part->data, (size_t)part->length);
    result->data[total] = '\0';

    return result;
}

/* ── Parent ──────────────────────────────────────────────────── */

Prove_String *prove_path_parent(Prove_String *path) {
    if (!path || path->length == 0) return prove_string_from_cstr(".");

    /* Find last / (ignoring trailing slash) */
    int64_t end = path->length - 1;
    while (end > 0 && path->data[end] == '/') end--;

    int64_t last_sep = -1;
    for (int64_t i = end; i >= 0; i--) {
        if (path->data[i] == '/') { last_sep = i; break; }
    }

    if (last_sep < 0) return prove_string_from_cstr(".");
    if (last_sep == 0) return prove_string_from_cstr("/");

    return prove_string_new(path->data, last_sep);
}

/* ── Name ────────────────────────────────────────────────────── */

Prove_String *prove_path_name(Prove_String *path) {
    if (!path || path->length == 0) return prove_string_from_cstr("");

    /* Find last / */
    int64_t last_sep = -1;
    for (int64_t i = path->length - 1; i >= 0; i--) {
        if (path->data[i] == '/') { last_sep = i; break; }
    }

    int64_t start = last_sep + 1;
    return prove_string_new(path->data + start, path->length - start);
}

/* ── Stem ────────────────────────────────────────────────────── */

Prove_String *prove_path_stem(Prove_String *path) {
    Prove_String *n = prove_path_name(path);
    if (!n || n->length == 0) return prove_string_from_cstr("");

    /* Find last . in name (not at position 0) */
    int64_t dot = -1;
    for (int64_t i = n->length - 1; i > 0; i--) {
        if (n->data[i] == '.') { dot = i; break; }
    }

    if (dot < 0) return n;
    return prove_string_new(n->data, dot);
}

/* ── Extension ───────────────────────────────────────────────── */

Prove_String *prove_path_extension(Prove_String *path) {
    Prove_String *n = prove_path_name(path);
    if (!n || n->length == 0) return prove_string_from_cstr("");

    int64_t dot = -1;
    for (int64_t i = n->length - 1; i > 0; i--) {
        if (n->data[i] == '.') { dot = i; break; }
    }

    if (dot < 0) return prove_string_from_cstr("");
    return prove_string_new(n->data + dot, n->length - dot);
}

/* ── Absolute ────────────────────────────────────────────────── */

bool prove_path_absolute(Prove_String *path) {
    return path && path->length > 0 && path->data[0] == '/';
}

/* ── Normalize ───────────────────────────────────────────────── */

Prove_String *prove_path_normalize(Prove_String *path) {
    if (!path || path->length == 0) return prove_string_from_cstr(".");

    bool is_abs = path->data[0] == '/';

    /* Work on a copy */
    char *buf = (char *)malloc((size_t)path->length + 1);
    memcpy(buf, path->data, (size_t)path->length);
    buf[path->length] = '\0';

    /* Dynamic segments array */
    int seg_cap = 32;
    int seg_count = 0;
    char **segments = (char **)malloc((size_t)seg_cap * sizeof(char *));

    char *tok = strtok(buf, "/");
    while (tok) {
        if (strcmp(tok, ".") == 0) {
            /* skip */
        } else if (strcmp(tok, "..") == 0) {
            if (seg_count > 0 && strcmp(segments[seg_count - 1], "..") != 0) {
                seg_count--;
            } else if (!is_abs) {
                if (seg_count >= seg_cap) {
                    seg_cap *= 2;
                    segments = (char **)realloc(segments, (size_t)seg_cap * sizeof(char *));
                }
                segments[seg_count++] = "..";
            }
        } else {
            if (seg_count >= seg_cap) {
                seg_cap *= 2;
                segments = (char **)realloc(segments, (size_t)seg_cap * sizeof(char *));
            }
            segments[seg_count++] = tok;
        }
        tok = strtok(NULL, "/");
    }

    /* Calculate result size */
    size_t result_len = is_abs ? 1 : 0;
    for (int i = 0; i < seg_count; i++) {
        if (i > 0) result_len++;
        result_len += strlen(segments[i]);
    }

    if (result_len == 0) {
        free(segments);
        free(buf);
        return prove_string_from_cstr(".");
    }

    /* Build result */
    char *result = (char *)malloc(result_len + 1);
    int pos = 0;

    if (is_abs) result[pos++] = '/';

    for (int i = 0; i < seg_count; i++) {
        if (i > 0) result[pos++] = '/';
        int slen = (int)strlen(segments[i]);
        memcpy(result + pos, segments[i], (size_t)slen);
        pos += slen;
    }
    result[pos] = '\0';

    Prove_String *ret = prove_string_new(result, pos);
    free(result);
    free(segments);
    free(buf);
    return ret;
}
