#include "prove_text.h"
#include <ctype.h>
#include <string.h>

/* ── String queries ──────────────────────────────────────────── */

int64_t prove_text_length(Prove_String *s) {
    return s ? s->length : 0;
}

Prove_String *prove_text_slice(Prove_String *s, int64_t start, int64_t end) {
    if (!s) return prove_string_new("", 0);
    if (start < 0) start = 0;
    if (end > s->length) end = s->length;
    if (start >= end) return prove_string_new("", 0);
    return prove_string_new(s->data + start, end - start);
}

bool prove_text_starts_with(Prove_String *s, Prove_String *prefix) {
    if (!s || !prefix) return false;
    if (prefix->length > s->length) return false;
    return memcmp(s->data, prefix->data, (size_t)prefix->length) == 0;
}

bool prove_text_ends_with(Prove_String *s, Prove_String *suffix) {
    if (!s || !suffix) return false;
    if (suffix->length > s->length) return false;
    int64_t offset = s->length - suffix->length;
    return memcmp(s->data + offset, suffix->data, (size_t)suffix->length) == 0;
}

bool prove_text_contains(Prove_String *s, Prove_String *sub) {
    if (!s || !sub) return false;
    if (sub->length == 0) return true;
    if (sub->length > s->length) return false;
    /* Use strstr on null-terminated data */
    return strstr(s->data, sub->data) != NULL;
}

Prove_Option_int64_t prove_text_index_of(Prove_String *s, Prove_String *sub) {
    if (!s || !sub) return Prove_Option_int64_t_none();
    if (sub->length == 0) return Prove_Option_int64_t_some(0);
    if (sub->length > s->length) return Prove_Option_int64_t_none();
    char *found = strstr(s->data, sub->data);
    if (!found) return Prove_Option_int64_t_none();
    return Prove_Option_int64_t_some((int64_t)(found - s->data));
}

/* ── String transformations ──────────────────────────────────── */

Prove_List *prove_text_split(Prove_String *s, Prove_String *sep) {
    Prove_List *list = prove_list_new(sizeof(Prove_String *), 8);
    if (!s || s->length == 0) {
        return list;
    }
    if (!sep || sep->length == 0) {
        /* Empty separator: return list with the original string */
        Prove_String *copy = prove_string_new(s->data, s->length);
        prove_list_push(&list, &copy);
        return list;
    }

    const char *start = s->data;
    const char *end = s->data + s->length;
    size_t sep_len = (size_t)sep->length;

    while (start <= end) {
        const char *found = NULL;
        if (start < end) {
            /* Search within remaining data */
            for (const char *p = start; p + sep_len <= end; p++) {
                if (memcmp(p, sep->data, sep_len) == 0) {
                    found = p;
                    break;
                }
            }
        }
        if (found) {
            Prove_String *part = prove_string_new(start, (int64_t)(found - start));
            prove_list_push(&list, &part);
            start = found + sep_len;
        } else {
            Prove_String *part = prove_string_new(start, (int64_t)(end - start));
            prove_list_push(&list, &part);
            break;
        }
    }

    return list;
}

Prove_String *prove_text_join(Prove_List *parts, Prove_String *sep) {
    if (!parts || parts->length == 0) return prove_string_new("", 0);

    /* Calculate total length */
    int64_t total = 0;
    for (int64_t i = 0; i < parts->length; i++) {
        Prove_String **sp = (Prove_String **)prove_list_get(parts, i);
        if (*sp) total += (*sp)->length;
        if (i > 0 && sep) total += sep->length;
    }

    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)total + 1
    );
    result->length = total;

    char *dst = result->data;
    for (int64_t i = 0; i < parts->length; i++) {
        if (i > 0 && sep && sep->length > 0) {
            memcpy(dst, sep->data, (size_t)sep->length);
            dst += sep->length;
        }
        Prove_String **sp = (Prove_String **)prove_list_get(parts, i);
        if (*sp && (*sp)->length > 0) {
            memcpy(dst, (*sp)->data, (size_t)(*sp)->length);
            dst += (*sp)->length;
        }
    }
    result->data[total] = '\0';

    return result;
}

Prove_String *prove_text_trim(Prove_String *s) {
    if (!s || s->length == 0) return prove_string_new("", 0);

    int64_t start = 0;
    int64_t end = s->length;
    while (start < end && isspace((unsigned char)s->data[start])) start++;
    while (end > start && isspace((unsigned char)s->data[end - 1])) end--;

    return prove_string_new(s->data + start, end - start);
}

Prove_String *prove_text_to_lower(Prove_String *s) {
    if (!s) return prove_string_new("", 0);
    Prove_String *result = prove_string_new(s->data, s->length);
    for (int64_t i = 0; i < result->length; i++) {
        result->data[i] = (char)tolower((unsigned char)result->data[i]);
    }
    return result;
}

Prove_String *prove_text_to_upper(Prove_String *s) {
    if (!s) return prove_string_new("", 0);
    Prove_String *result = prove_string_new(s->data, s->length);
    for (int64_t i = 0; i < result->length; i++) {
        result->data[i] = (char)toupper((unsigned char)result->data[i]);
    }
    return result;
}

Prove_String *prove_text_replace(Prove_String *s, Prove_String *old_s, Prove_String *new_s) {
    if (!s || !old_s || old_s->length == 0) {
        return s ? prove_string_new(s->data, s->length) : prove_string_new("", 0);
    }
    if (!new_s) new_s = prove_string_new("", 0);

    /* Count occurrences */
    int64_t count = 0;
    const char *p = s->data;
    const char *end = s->data + s->length;
    while (p + old_s->length <= end) {
        if (memcmp(p, old_s->data, (size_t)old_s->length) == 0) {
            count++;
            p += old_s->length;
        } else {
            p++;
        }
    }

    if (count == 0) return prove_string_new(s->data, s->length);

    int64_t new_len = s->length + count * (new_s->length - old_s->length);
    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)new_len + 1
    );
    result->length = new_len;

    const char *src = s->data;
    char *dst = result->data;
    while (src + old_s->length <= end) {
        if (memcmp(src, old_s->data, (size_t)old_s->length) == 0) {
            if (new_s->length > 0) {
                memcpy(dst, new_s->data, (size_t)new_s->length);
                dst += new_s->length;
            }
            src += old_s->length;
        } else {
            *dst++ = *src++;
        }
    }
    /* Copy remaining bytes */
    while (src < end) {
        *dst++ = *src++;
    }
    result->data[new_len] = '\0';

    return result;
}

Prove_String *prove_text_repeat(Prove_String *s, int64_t n) {
    if (!s || n <= 0) return prove_string_new("", 0);
    int64_t new_len = s->length * n;
    Prove_String *result = (Prove_String *)prove_alloc(
        sizeof(Prove_String) + (size_t)new_len + 1
    );
    result->length = new_len;
    char *dst = result->data;
    for (int64_t i = 0; i < n; i++) {
        memcpy(dst, s->data, (size_t)s->length);
        dst += s->length;
    }
    result->data[new_len] = '\0';
    return result;
}

/* ── Builder ─────────────────────────────────────────────────── */

#define BUILDER_INITIAL_CAP 64

Prove_Builder *prove_text_builder(void) {
    Prove_Builder *b = (Prove_Builder *)prove_alloc(
        sizeof(Prove_Builder) + BUILDER_INITIAL_CAP
    );
    b->length = 0;
    b->capacity = BUILDER_INITIAL_CAP;
    return b;
}

static Prove_Builder *_builder_grow(Prove_Builder *b, int64_t needed) {
    int64_t new_cap = b->capacity;
    while (new_cap < b->length + needed) {
        new_cap *= 2;
    }
    Prove_Builder *new_b = (Prove_Builder *)realloc(b, sizeof(Prove_Builder) + (size_t)new_cap);
    if (!new_b) prove_panic("Builder realloc failed");
    new_b->capacity = new_cap;
    return new_b;
}

Prove_Builder *prove_text_write(Prove_Builder *b, Prove_String *s) {
    if (!b) prove_panic("Builder.write: null builder");
    if (!s || s->length == 0) return b;
    if (b->length + s->length > b->capacity) {
        b = _builder_grow(b, s->length);
    }
    memcpy(b->data + b->length, s->data, (size_t)s->length);
    b->length += s->length;
    return b;
}

Prove_Builder *prove_text_write_char(Prove_Builder *b, char c) {
    if (!b) prove_panic("Builder.write_char: null builder");
    if (b->length + 1 > b->capacity) {
        b = _builder_grow(b, 1);
    }
    b->data[b->length] = c;
    b->length++;
    return b;
}

Prove_String *prove_text_build(Prove_Builder *b) {
    if (!b) return prove_string_new("", 0);
    return prove_string_new(b->data, b->length);
}

int64_t prove_text_builder_length(Prove_Builder *b) {
    return b ? b->length : 0;
}
