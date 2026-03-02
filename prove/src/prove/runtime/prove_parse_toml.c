/* Prove TOML parser — hand-rolled recursive descent.
 *
 * Supports: key=value, [sections], strings, integers, floats, bools, arrays.
 * TOML subset sufficient for prove.toml and typical config files.
 */

#include "prove_parse.h"
#include <ctype.h>
#include <string.h>
#include <stdio.h>

/* ── Value constructors (shared with JSON) ───────────────────── */

Prove_Value *prove_value_null(void) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_NULL;
    return v;
}

Prove_Value *prove_value_text(Prove_String *s) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_TEXT;
    v->text = s;
    return v;
}

Prove_Value *prove_value_number(int64_t n) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_NUMBER;
    v->number = n;
    return v;
}

Prove_Value *prove_value_decimal(double d) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_DECIMAL;
    v->decimal = d;
    return v;
}

Prove_Value *prove_value_bool(bool b) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_BOOL;
    v->boolean = b;
    return v;
}

Prove_Value *prove_value_array(Prove_List *arr) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_ARRAY;
    v->array = arr;
    return v;
}

Prove_Value *prove_value_object(Prove_Table *obj) {
    Prove_Value *v = (Prove_Value *)malloc(sizeof(Prove_Value));
    if (!v) return NULL;
    v->tag = PROVE_VALUE_OBJECT;
    v->object = obj;
    return v;
}

/* ── Accessors ───────────────────────────────────────────────── */

Prove_String *prove_value_tag(Prove_Value *v) {
    if (!v) return prove_string_from_cstr("null");
    switch (v->tag) {
        case PROVE_VALUE_TEXT:    return prove_string_from_cstr("text");
        case PROVE_VALUE_NUMBER:  return prove_string_from_cstr("number");
        case PROVE_VALUE_DECIMAL: return prove_string_from_cstr("decimal");
        case PROVE_VALUE_BOOL:    return prove_string_from_cstr("bool");
        case PROVE_VALUE_ARRAY:   return prove_string_from_cstr("array");
        case PROVE_VALUE_OBJECT:  return prove_string_from_cstr("object");
        default:                  return prove_string_from_cstr("null");
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
    return prove_list_new(sizeof(Prove_Value *), 4);
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

/* Parse a TOML string value */
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

    /* Regular string with escape handling */
    char buf[4096];
    int64_t bi = 0;
    while (p->pos < p->len && p->src[p->pos] != '"') {
        if (p->src[p->pos] == '\\' && p->pos + 1 < p->len) {
            p->pos++;
            char esc = p->src[p->pos];
            switch (esc) {
                case 'n':  buf[bi++] = '\n'; break;
                case 't':  buf[bi++] = '\t'; break;
                case 'r':  buf[bi++] = '\r'; break;
                case '\\': buf[bi++] = '\\'; break;
                case '"':  buf[bi++] = '"';  break;
                default:   buf[bi++] = esc;  break;
            }
        } else {
            buf[bi++] = p->src[p->pos];
        }
        p->pos++;
        if (bi >= 4095) break;
    }
    if (p->pos < p->len) p->pos++; /* skip closing " */
    return prove_value_text(prove_string_new(buf, bi));
}

/* Parse a TOML array */
static Prove_Value *_toml_parse_array(TomlParser *p) {
    p->pos++; /* skip [ */
    Prove_List *arr = prove_list_new(sizeof(Prove_Value *), 8);
    _toml_skip_ws_nl(p);
    while (!_toml_at_end(p) && _toml_peek(p) != ']') {
        Prove_Value *elem = _toml_parse_value(p);
        if (!elem) return NULL;
        prove_list_push(&arr, &elem);
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

    Prove_Value *result = prove_value_object(root);
    return prove_result_ok_ptr(result);
}

/* ── TOML emitter ────────────────────────────────────────────── */

static void _toml_emit_value(Prove_Value *v, Prove_String **out);
static void _toml_emit_table(Prove_Table *t, Prove_String *prefix, Prove_String **out);

static void _append(Prove_String **out, const char *cstr) {
    Prove_String *s = prove_string_from_cstr(cstr);
    *out = prove_string_concat(*out, s);
}

static void _append_str(Prove_String **out, Prove_String *s) {
    *out = prove_string_concat(*out, s);
}

static void _toml_emit_value(Prove_Value *v, Prove_String **out) {
    if (!v || v->tag == PROVE_VALUE_NULL) {
        _append(out, "\"\"");
        return;
    }
    switch (v->tag) {
        case PROVE_VALUE_TEXT:
            _append(out, "\"");
            _append_str(out, v->text);
            _append(out, "\"");
            break;
        case PROVE_VALUE_NUMBER: {
            char buf[32];
            snprintf(buf, sizeof(buf), "%lld", (long long)v->number);
            _append(out, buf);
            break;
        }
        case PROVE_VALUE_DECIMAL: {
            char buf[64];
            snprintf(buf, sizeof(buf), "%g", v->decimal);
            _append(out, buf);
            break;
        }
        case PROVE_VALUE_BOOL:
            _append(out, v->boolean ? "true" : "false");
            break;
        case PROVE_VALUE_ARRAY: {
            _append(out, "[");
            int64_t n = prove_list_len(v->array);
            for (int64_t i = 0; i < n; i++) {
                if (i > 0) _append(out, ", ");
                Prove_Value *elem = *(Prove_Value **)prove_list_get(v->array, i);
                _toml_emit_value(elem, out);
            }
            _append(out, "]");
            break;
        }
        case PROVE_VALUE_OBJECT:
            /* Inline tables not emitted here — handled by section headers */
            _append(out, "{}");
            break;
        default:
            _append(out, "\"\"");
            break;
    }
}

static void _toml_emit_table(Prove_Table *t, Prove_String *prefix, Prove_String **out) {
    /* First emit simple key-value pairs */
    Prove_List *keys = prove_table_keys(t);
    int64_t nkeys = prove_list_len(keys);

    for (int64_t i = 0; i < nkeys; i++) {
        Prove_String *key = *(Prove_String **)prove_list_get(keys, i);
        Prove_Option_voidptr opt = prove_table_get(key, t);
        if (Prove_Option_voidptr_is_none(opt)) continue;
        Prove_Value *val = (Prove_Value *)opt.value;
        if (val && val->tag == PROVE_VALUE_OBJECT) continue; /* sections later */
        _append_str(out, key);
        _append(out, " = ");
        _toml_emit_value(val, out);
        _append(out, "\n");
    }

    /* Then emit sections */
    for (int64_t i = 0; i < nkeys; i++) {
        Prove_String *key = *(Prove_String **)prove_list_get(keys, i);
        Prove_Option_voidptr opt = prove_table_get(key, t);
        if (Prove_Option_voidptr_is_none(opt)) continue;
        Prove_Value *val = (Prove_Value *)opt.value;
        if (!val || val->tag != PROVE_VALUE_OBJECT) continue;

        Prove_String *section;
        if (prove_string_len(prefix) > 0) {
            section = prove_string_concat(prefix, prove_string_from_cstr("."));
            section = prove_string_concat(section, key);
        } else {
            section = key;
        }
        _append(out, "\n[");
        _append_str(out, section);
        _append(out, "]\n");
        _toml_emit_table(val->object, section, out);
    }
}

Prove_String *prove_emit_toml(Prove_Value *value) {
    if (!value || value->tag != PROVE_VALUE_OBJECT)
        return prove_string_from_cstr("");

    Prove_String *out = prove_string_from_cstr("");
    _toml_emit_table(value->object, prove_string_from_cstr(""), &out);
    return out;
}
