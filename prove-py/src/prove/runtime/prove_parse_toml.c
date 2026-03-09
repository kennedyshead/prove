/* Prove TOML parser — hand-rolled recursive descent.
 *
 * Supports: key=value, [sections], strings, integers, floats, bools, arrays.
 * TOML subset sufficient for prove.toml and typical config files.
 */

#include "prove_parse.h"
#include "prove_text.h"
#include <ctype.h>
#include <string.h>
#include <stdio.h>

/* ── Value constructors (shared with JSON) ───────────────────── */

Prove_Value *prove_value_null(void) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_NULL;
    return v;
}

Prove_Value *prove_value_text(Prove_String *s) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_TEXT;
    v->text = s;
    return v;
}

Prove_Value *prove_value_number(int64_t n) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_NUMBER;
    v->number = n;
    return v;
}

Prove_Value *prove_value_decimal(double d) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_DECIMAL;
    v->decimal = d;
    return v;
}

Prove_Value *prove_value_bool(bool b) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_BOOL;
    v->boolean = b;
    return v;
}

Prove_Value *prove_value_array(Prove_List *arr) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_ARRAY;
    v->array = arr;
    return v;
}

Prove_Value *prove_value_object(Prove_Table *obj) {
    Prove_Value *v = (Prove_Value *)prove_alloc(sizeof(Prove_Value));
    v->tag = PROVE_VALUE_OBJECT;
    v->object = obj;
    return v;
}

/* ── Accessors ───────────────────────────────────────────────── */

static Prove_String *_tag_null = NULL;
static Prove_String *_tag_text = NULL;
static Prove_String *_tag_number = NULL;
static Prove_String *_tag_decimal = NULL;
static Prove_String *_tag_bool = NULL;
static Prove_String *_tag_array = NULL;
static Prove_String *_tag_object = NULL;

static void _init_tag_strings(void) {
    if (_tag_null) return;
    _tag_null = prove_string_from_cstr("null");
    _tag_null->header.refcount = INT32_MAX;
    _tag_text = prove_string_from_cstr("text");
    _tag_text->header.refcount = INT32_MAX;
    _tag_number = prove_string_from_cstr("number");
    _tag_number->header.refcount = INT32_MAX;
    _tag_decimal = prove_string_from_cstr("decimal");
    _tag_decimal->header.refcount = INT32_MAX;
    _tag_bool = prove_string_from_cstr("bool");
    _tag_bool->header.refcount = INT32_MAX;
    _tag_array = prove_string_from_cstr("array");
    _tag_array->header.refcount = INT32_MAX;
    _tag_object = prove_string_from_cstr("object");
    _tag_object->header.refcount = INT32_MAX;
}

Prove_String *prove_value_tag(Prove_Value *v) {
    _init_tag_strings();
    if (!v) return _tag_null;
    switch (v->tag) {
        case PROVE_VALUE_TEXT:    return _tag_text;
        case PROVE_VALUE_NUMBER:  return _tag_number;
        case PROVE_VALUE_DECIMAL: return _tag_decimal;
        case PROVE_VALUE_BOOL:    return _tag_bool;
        case PROVE_VALUE_ARRAY:   return _tag_array;
        case PROVE_VALUE_OBJECT:  return _tag_object;
        default:                  return _tag_null;
    }
}

Prove_String *prove_value_as_text(Prove_Value *v) {
    if (v && v->tag == PROVE_VALUE_TEXT) return v->text;
    return prove_string_from_cstr("");
}

int64_t prove_value_as_number(Prove_Value *v) {
    if (v && v->tag == PROVE_VALUE_NUMBER) return v->number;
    return 0;
}

double prove_value_as_decimal(Prove_Value *v) {
    if (v && v->tag == PROVE_VALUE_DECIMAL) return v->decimal;
    return 0.0;
}

bool prove_value_as_bool(Prove_Value *v) {
    if (v && v->tag == PROVE_VALUE_BOOL) return v->boolean;
    return false;
}

Prove_List *prove_value_as_array(Prove_Value *v) {
    if (v && v->tag == PROVE_VALUE_ARRAY) return v->array;
    return prove_list_new(4);
}

Prove_Table *prove_value_as_object(Prove_Value *v) {
    if (v && v->tag == PROVE_VALUE_OBJECT) return v->object;
    return prove_table_new();
}

/* ── Type checks ─────────────────────────────────────────────── */

bool prove_value_is_text(Prove_Value *v)    { return v && v->tag == PROVE_VALUE_TEXT; }
bool prove_value_is_number(Prove_Value *v)  { return v && v->tag == PROVE_VALUE_NUMBER; }
bool prove_value_is_decimal(Prove_Value *v) { return v && v->tag == PROVE_VALUE_DECIMAL; }
bool prove_value_is_bool(Prove_Value *v)    { return v && v->tag == PROVE_VALUE_BOOL; }
bool prove_value_is_array(Prove_Value *v)   { return v && v->tag == PROVE_VALUE_ARRAY; }
bool prove_value_is_object(Prove_Value *v)  { return v && v->tag == PROVE_VALUE_OBJECT; }
bool prove_value_is_null(Prove_Value *v)    { return !v || v->tag == PROVE_VALUE_NULL; }

/* ── Record → Value identity passthrough ─────────────────────── */

Prove_Value *prove_creates_value(Prove_Value *v) { return v; }
bool prove_validates_value(Prove_Value *v) { return v != NULL; }

/* ── TOML parser state ───────────────────────────────────────── */

typedef struct {
    const char *src;
    int64_t     len;
    int64_t     pos;
    char        err[256];
} TomlParser;

static void _toml_skip_ws(TomlParser *p) {
    while (p->pos < p->len) {
        char c = p->src[p->pos];
        if (c == ' ' || c == '\t' || c == '\r') {
            p->pos++;
        } else if (c == '#') {
            /* Skip comment to end of line */
            while (p->pos < p->len && p->src[p->pos] != '\n')
                p->pos++;
        } else {
            break;
        }
    }
}

static void _toml_skip_ws_nl(TomlParser *p) {
    while (p->pos < p->len) {
        char c = p->src[p->pos];
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
            p->pos++;
        } else if (c == '#') {
            while (p->pos < p->len && p->src[p->pos] != '\n')
                p->pos++;
        } else {
            break;
        }
    }
}

static bool _toml_at_end(TomlParser *p) {
    return p->pos >= p->len;
}

static char _toml_peek(TomlParser *p) {
    return p->pos < p->len ? p->src[p->pos] : '\0';
}

/* Parse a bare key or quoted string key */
static Prove_String *_toml_parse_key(TomlParser *p) {
    _toml_skip_ws(p);
    if (_toml_peek(p) == '"') {
        /* Quoted key */
        p->pos++; /* skip opening " */
        int64_t start = p->pos;
        while (p->pos < p->len && p->src[p->pos] != '"') {
            if (p->src[p->pos] == '\\') p->pos++; /* skip escape */
            p->pos++;
        }
        Prove_String *key = prove_string_new(p->src + start, p->pos - start);
        if (p->pos < p->len) p->pos++; /* skip closing " */
        return key;
    }
    /* Bare key: [A-Za-z0-9_-] */
    int64_t start = p->pos;
    while (p->pos < p->len) {
        char c = p->src[p->pos];
        if (isalnum((unsigned char)c) || c == '_' || c == '-') {
            p->pos++;
        } else {
            break;
        }
    }
    if (p->pos == start) return NULL;
    return prove_string_new(p->src + start, p->pos - start);
}

/* Forward declaration */
static Prove_Value *_toml_parse_value(TomlParser *p);

/* Parse a TOML string value (dynamic buffer via Builder) */
static Prove_Value *_toml_parse_string(TomlParser *p) {
    p->pos++; /* skip opening " */

    /* Check for triple-quoted string """...""" */
    if (p->pos + 1 < p->len && p->src[p->pos] == '"' && p->src[p->pos + 1] == '"') {
        p->pos += 2; /* skip remaining "" */
        /* Skip first newline after opening """ */
        if (p->pos < p->len && p->src[p->pos] == '\n') p->pos++;
        int64_t start = p->pos;
        while (p->pos + 2 < p->len) {
            if (p->src[p->pos] == '"' && p->src[p->pos+1] == '"' && p->src[p->pos+2] == '"') {
                Prove_String *s = prove_string_new(p->src + start, p->pos - start);
                p->pos += 3;
                return prove_value_text(s);
            }
            p->pos++;
        }
        snprintf(p->err, sizeof(p->err), "unterminated triple-quoted string");
        return NULL;
    }

    /* Regular string with escape handling (dynamic buffer) */
    Prove_Builder *b = prove_text_builder();
    while (p->pos < p->len && p->src[p->pos] != '"') {
        if (p->src[p->pos] == '\\' && p->pos + 1 < p->len) {
            p->pos++;
            char esc = p->src[p->pos];
            switch (esc) {
                case 'n':  b = prove_text_write_char(b, '\n'); break;
                case 't':  b = prove_text_write_char(b, '\t'); break;
                case 'r':  b = prove_text_write_char(b, '\r'); break;
                case '\\': b = prove_text_write_char(b, '\\'); break;
                case '"':  b = prove_text_write_char(b, '"');  break;
                default:   b = prove_text_write_char(b, esc);  break;
            }
        } else {
            b = prove_text_write_char(b, p->src[p->pos]);
        }
        p->pos++;
    }
    if (p->pos < p->len) p->pos++; /* skip closing " */
    Prove_String *result = prove_text_build(b);
    free(b);
    return prove_value_text(result);
}

/* Parse a TOML array */
static Prove_Value *_toml_parse_array(TomlParser *p) {
    p->pos++; /* skip [ */
    Prove_List *arr = prove_list_new(8);
    _toml_skip_ws_nl(p);
    while (!_toml_at_end(p) && _toml_peek(p) != ']') {
        Prove_Value *elem = _toml_parse_value(p);
        if (!elem) return NULL;
        prove_list_push(arr, elem);
        _toml_skip_ws_nl(p);
        if (_toml_peek(p) == ',') {
            p->pos++;
            _toml_skip_ws_nl(p);
        }
    }
    if (_toml_peek(p) == ']') p->pos++;
    return prove_value_array(arr);
}

/* Parse a TOML value */
static Prove_Value *_toml_parse_value(TomlParser *p) {
    _toml_skip_ws(p);
    if (_toml_at_end(p)) {
        snprintf(p->err, sizeof(p->err), "unexpected end of input");
        return NULL;
    }

    char c = _toml_peek(p);

    /* String */
    if (c == '"') return _toml_parse_string(p);

    /* Array */
    if (c == '[') return _toml_parse_array(p);

    /* Boolean */
    if (p->pos + 4 <= p->len && memcmp(p->src + p->pos, "true", 4) == 0 &&
        (p->pos + 4 >= p->len || !isalnum((unsigned char)p->src[p->pos + 4]))) {
        p->pos += 4;
        return prove_value_bool(true);
    }
    if (p->pos + 5 <= p->len && memcmp(p->src + p->pos, "false", 5) == 0 &&
        (p->pos + 5 >= p->len || !isalnum((unsigned char)p->src[p->pos + 5]))) {
        p->pos += 5;
        return prove_value_bool(false);
    }

    /* Number (integer or decimal) */
    if (c == '-' || c == '+' || isdigit((unsigned char)c)) {
        int64_t start = p->pos;
        if (c == '-' || c == '+') p->pos++;
        bool has_dot = false;
        while (p->pos < p->len) {
            char ch = p->src[p->pos];
            if (ch == '_') { p->pos++; continue; } /* TOML allows _ in numbers */
            if (ch == '.') { has_dot = true; p->pos++; continue; }
            if (isdigit((unsigned char)ch)) { p->pos++; continue; }
            break;
        }
        char numbuf[128];
        int64_t nlen = p->pos - start;
        if (nlen >= 127) nlen = 126;
        /* Copy without underscores */
        int64_t j = 0;
        for (int64_t i = start; i < start + nlen && j < 126; i++) {
            if (p->src[i] != '_') numbuf[j++] = p->src[i];
        }
        numbuf[j] = '\0';
        if (has_dot) {
            double d = strtod(numbuf, NULL);
            return prove_value_decimal(d);
        }
        int64_t n = strtoll(numbuf, NULL, 10);
        return prove_value_number(n);
    }

    snprintf(p->err, sizeof(p->err), "unexpected character '%c'", c);
    return NULL;
}

/* ── TOML top-level parser ───────────────────────────────────── */

Prove_Result prove_parse_toml(Prove_String *source) {
    TomlParser p;
    p.src = source->data;
    p.len = source->length;
    p.pos = 0;
    p.err[0] = '\0';

    Prove_Table *root = prove_table_new();
    Prove_Table *current = root; /* current section */

    while (!_toml_at_end(&p)) {
        _toml_skip_ws_nl(&p);
        if (_toml_at_end(&p)) break;

        char c = _toml_peek(&p);

        /* Section header [name] */
        if (c == '[') {
            p.pos++;
            Prove_String *section_name = _toml_parse_key(&p);
            if (!section_name) {
                return prove_result_err(
                    prove_string_from_cstr("expected section name"));
            }
            _toml_skip_ws(&p);
            if (_toml_peek(&p) != ']') {
                return prove_result_err(
                    prove_string_from_cstr("expected ']' after section name"));
            }
            p.pos++;

            /* Create nested table */
            Prove_Table *section = prove_table_new();
            Prove_Value *sv = prove_value_object(section);
            root = prove_table_add(section_name, sv, root);
            current = section;
            continue;
        }

        /* Key = Value */
        Prove_String *key = _toml_parse_key(&p);
        if (!key) {
            /* Skip unknown content */
            p.pos++;
            continue;
        }
        _toml_skip_ws(&p);
        if (_toml_peek(&p) != '=') {
            return prove_result_err(
                prove_string_from_cstr("expected '=' after key"));
        }
        p.pos++; /* skip = */
        _toml_skip_ws(&p);

        Prove_Value *val = _toml_parse_value(&p);
        if (!val) {
            return prove_result_err(prove_string_from_cstr(p.err));
        }

        current = prove_table_add(key, val, current);

        /* If current is not root, update root's reference */
        /* (prove_table_add may realloc, handled by pointer stability) */

        /* Skip to end of line */
        _toml_skip_ws(&p);
        if (!_toml_at_end(&p) && _toml_peek(&p) == '\n') p.pos++;
    }

    return prove_result_ok_ptr(root);
}

/* ── TOML emitter (uses Builder for O(n) emission) ───────────── */

static void _toml_emit_value(Prove_Value *v, Prove_Builder **b);
static void _toml_emit_table(Prove_Table *t, Prove_String *prefix, Prove_Builder **b);

static void _toml_emit_value(Prove_Value *v, Prove_Builder **b) {
    if (!v || v->tag == PROVE_VALUE_NULL) {
        *b = prove_text_write_cstr(*b, "\"\"");
        return;
    }
    switch (v->tag) {
        case PROVE_VALUE_TEXT:
            *b = prove_text_write_char(*b, '"');
            *b = prove_text_write(*b, v->text);
            *b = prove_text_write_char(*b, '"');
            break;
        case PROVE_VALUE_NUMBER: {
            char buf[32];
            snprintf(buf, sizeof(buf), "%lld", (long long)v->number);
            *b = prove_text_write_cstr(*b, buf);
            break;
        }
        case PROVE_VALUE_DECIMAL: {
            char buf[64];
            snprintf(buf, sizeof(buf), "%g", v->decimal);
            *b = prove_text_write_cstr(*b, buf);
            break;
        }
        case PROVE_VALUE_BOOL:
            *b = prove_text_write_cstr(*b, v->boolean ? "true" : "false");
            break;
        case PROVE_VALUE_ARRAY: {
            *b = prove_text_write_char(*b, '[');
            int64_t n = prove_list_len(v->array);
            for (int64_t i = 0; i < n; i++) {
                if (i > 0) *b = prove_text_write_cstr(*b, ", ");
                Prove_Value *elem = (Prove_Value *)prove_list_get(v->array, i);
                _toml_emit_value(elem, b);
            }
            *b = prove_text_write_char(*b, ']');
            break;
        }
        case PROVE_VALUE_OBJECT:
            /* Inline tables not emitted here — handled by section headers */
            *b = prove_text_write_cstr(*b, "{}");
            break;
        default:
            *b = prove_text_write_cstr(*b, "\"\"");
            break;
    }
}

static void _toml_emit_table(Prove_Table *t, Prove_String *prefix, Prove_Builder **b) {
    /* First emit simple key-value pairs */
    Prove_List *keys = prove_table_keys(t);
    int64_t nkeys = prove_list_len(keys);

    for (int64_t i = 0; i < nkeys; i++) {
        Prove_String *key = (Prove_String *)prove_list_get(keys, i);
        Prove_Option opt = prove_table_get(key, t);
        if (prove_option_is_none(opt)) continue;
        Prove_Value *val = (Prove_Value *)opt.value;
        if (val && val->tag == PROVE_VALUE_OBJECT) continue; /* sections later */
        *b = prove_text_write(*b, key);
        *b = prove_text_write_cstr(*b, " = ");
        _toml_emit_value(val, b);
        *b = prove_text_write_char(*b, '\n');
    }

    /* Then emit sections */
    for (int64_t i = 0; i < nkeys; i++) {
        Prove_String *key = (Prove_String *)prove_list_get(keys, i);
        Prove_Option opt = prove_table_get(key, t);
        if (prove_option_is_none(opt)) continue;
        Prove_Value *val = (Prove_Value *)opt.value;
        if (!val || val->tag != PROVE_VALUE_OBJECT) continue;

        Prove_String *section;
        if (prove_string_len(prefix) > 0) {
            section = prove_string_concat(prefix, prove_string_from_cstr("."));
            section = prove_string_concat(section, key);
        } else {
            section = key;
        }
        *b = prove_text_write_cstr(*b, "\n[");
        *b = prove_text_write(*b, section);
        *b = prove_text_write_cstr(*b, "]\n");
        _toml_emit_table(val->object, section, b);
    }
}

Prove_String *prove_emit_toml(Prove_Value *value) {
    if (!value || value->tag != PROVE_VALUE_OBJECT)
        return prove_string_from_cstr("");

    Prove_Builder *b = prove_text_builder();
    _toml_emit_table(value->object, prove_string_from_cstr(""), &b);
    Prove_String *result = prove_text_build(b);
    free(b);
    return result;
}

bool prove_validates_toml(Prove_String *source) {
    TomlParser p;
    p.src = source->data;
    p.len = source->length;
    p.pos = 0;
    p.err[0] = '\0';

    /* Attempt to parse key=value pairs and sections */
    while (!_toml_at_end(&p)) {
        _toml_skip_ws_nl(&p);
        if (_toml_at_end(&p)) break;

        char c = _toml_peek(&p);

        /* Section header [name] */
        if (c == '[') {
            p.pos++;
            Prove_String *section_name = _toml_parse_key(&p);
            if (!section_name) return false;
            _toml_skip_ws(&p);
            if (_toml_peek(&p) != ']') return false;
            p.pos++;
            continue;
        }

        /* Key = Value */
        Prove_String *key = _toml_parse_key(&p);
        if (!key) return false;
        _toml_skip_ws(&p);
        if (_toml_peek(&p) != '=') return false;
        p.pos++; /* skip = */
        _toml_skip_ws(&p);
        Prove_Value *val = _toml_parse_value(&p);
        if (!val) return false;
        _toml_skip_ws(&p);
        if (!_toml_at_end(&p) && _toml_peek(&p) == '\n') p.pos++;
    }
    return true;
}
