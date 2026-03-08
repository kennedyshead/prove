/* Prove JSON parser — hand-rolled recursive descent.
 *
 * Supports full JSON: objects, arrays, strings, numbers, booleans, null.
 */

#include "prove_parse.h"
#include "prove_text.h"
#include <ctype.h>
#include <string.h>
#include <stdio.h>

/* ── Parser state ────────────────────────────────────────────── */

typedef struct {
    const char *src;
    int64_t     len;
    int64_t     pos;
    char        err[256];
} JsonParser;

static void _json_skip_ws(JsonParser *p) {
    while (p->pos < p->len) {
        char c = p->src[p->pos];
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n')
            p->pos++;
        else
            break;
    }
}

static bool _json_at_end(JsonParser *p) {
    return p->pos >= p->len;
}

static char _json_peek(JsonParser *p) {
    return p->pos < p->len ? p->src[p->pos] : '\0';
}

/* Forward declaration */
static Prove_Value *_json_parse_value(JsonParser *p);

/* Parse a JSON string (dynamic buffer via Builder) */
static Prove_String *_json_parse_string(JsonParser *p) {
    if (_json_peek(p) != '"') return NULL;
    p->pos++; /* skip " */

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
                case '/':  b = prove_text_write_char(b, '/');  break;
                case 'u': {
                    /* \uXXXX — just pass through as-is for now */
                    b = prove_text_write_char(b, '\\');
                    b = prove_text_write_char(b, 'u');
                    break;
                }
                default: b = prove_text_write_char(b, esc); break;
            }
        } else {
            b = prove_text_write_char(b, p->src[p->pos]);
        }
        p->pos++;
    }
    if (p->pos < p->len) p->pos++; /* skip closing " */
    Prove_String *result = prove_text_build(b);
    free(b);
    return result;
}

/* Parse a JSON number */
static Prove_Value *_json_parse_number(JsonParser *p) {
    int64_t start = p->pos;
    bool has_dot = false;
    bool has_exp = false;

    if (_json_peek(p) == '-') p->pos++;
    while (p->pos < p->len && isdigit((unsigned char)p->src[p->pos]))
        p->pos++;

    if (p->pos < p->len && p->src[p->pos] == '.') {
        has_dot = true;
        p->pos++;
        while (p->pos < p->len && isdigit((unsigned char)p->src[p->pos]))
            p->pos++;
    }

    if (p->pos < p->len && (p->src[p->pos] == 'e' || p->src[p->pos] == 'E')) {
        has_exp = true;
        p->pos++;
        if (p->pos < p->len && (p->src[p->pos] == '+' || p->src[p->pos] == '-'))
            p->pos++;
        while (p->pos < p->len && isdigit((unsigned char)p->src[p->pos]))
            p->pos++;
    }

    char numbuf[128];
    int64_t nlen = p->pos - start;
    if (nlen >= 127) nlen = 126;
    memcpy(numbuf, p->src + start, (size_t)nlen);
    numbuf[nlen] = '\0';

    if (has_dot || has_exp) {
        return prove_value_decimal(strtod(numbuf, NULL));
    }
    return prove_value_number(strtoll(numbuf, NULL, 10));
}

/* Parse a JSON array */
static Prove_Value *_json_parse_array(JsonParser *p) {
    p->pos++; /* skip [ */
    Prove_List *arr = prove_list_new(8);
    _json_skip_ws(p);

    if (_json_peek(p) == ']') {
        p->pos++;
        return prove_value_array(arr);
    }

    while (!_json_at_end(p)) {
        Prove_Value *elem = _json_parse_value(p);
        if (!elem) return NULL;
        prove_list_push(arr, elem);
        _json_skip_ws(p);
        if (_json_peek(p) == ',') {
            p->pos++;
            _json_skip_ws(p);
        } else {
            break;
        }
    }

    if (_json_peek(p) == ']') p->pos++;
    return prove_value_array(arr);
}

/* Parse a JSON object */
static Prove_Value *_json_parse_object(JsonParser *p) {
    p->pos++; /* skip { */
    Prove_Table *obj = prove_table_new();
    _json_skip_ws(p);

    if (_json_peek(p) == '}') {
        p->pos++;
        return prove_value_object(obj);
    }

    while (!_json_at_end(p)) {
        _json_skip_ws(p);
        Prove_String *key = _json_parse_string(p);
        if (!key) {
            snprintf(p->err, sizeof(p->err), "expected string key in object");
            return NULL;
        }
        _json_skip_ws(p);
        if (_json_peek(p) != ':') {
            snprintf(p->err, sizeof(p->err), "expected ':' after object key");
            return NULL;
        }
        p->pos++; /* skip : */
        _json_skip_ws(p);
        Prove_Value *val = _json_parse_value(p);
        if (!val) return NULL;

        obj = prove_table_add(key, val, obj);
        _json_skip_ws(p);
        if (_json_peek(p) == ',') {
            p->pos++;
        } else {
            break;
        }
    }
    _json_skip_ws(p);
    if (_json_peek(p) == '}') p->pos++;
    return prove_value_object(obj);
}

/* Parse any JSON value */
static Prove_Value *_json_parse_value(JsonParser *p) {
    _json_skip_ws(p);
    if (_json_at_end(p)) {
        snprintf(p->err, sizeof(p->err), "unexpected end of JSON");
        return NULL;
    }

    char c = _json_peek(p);

    if (c == '"') {
        Prove_String *s = _json_parse_string(p);
        if (!s) return NULL;
        return prove_value_text(s);
    }
    if (c == '{') return _json_parse_object(p);
    if (c == '[') return _json_parse_array(p);
    if (c == '-' || isdigit((unsigned char)c)) return _json_parse_number(p);

    if (p->pos + 4 <= p->len && memcmp(p->src + p->pos, "true", 4) == 0) {
        p->pos += 4;
        return prove_value_bool(true);
    }
    if (p->pos + 5 <= p->len && memcmp(p->src + p->pos, "false", 5) == 0) {
        p->pos += 5;
        return prove_value_bool(false);
    }
    if (p->pos + 4 <= p->len && memcmp(p->src + p->pos, "null", 4) == 0) {
        p->pos += 4;
        return prove_value_null();
    }

    snprintf(p->err, sizeof(p->err), "unexpected character '%c'", c);
    return NULL;
}

/* ── Public API ──────────────────────────────────────────────── */

Prove_Result prove_parse_json(Prove_String *source) {
    JsonParser p;
    p.src = source->data;
    p.len = source->length;
    p.pos = 0;
    p.err[0] = '\0';

    Prove_Value *val = _json_parse_value(&p);
    if (!val) {
        if (p.err[0])
            return prove_result_err(prove_string_from_cstr(p.err));
        return prove_result_err(prove_string_from_cstr("parse error"));
    }
    return prove_result_ok_ptr(val);
}

/* ── JSON emitter (uses Builder for O(n) emission) ───────────── */

static void _json_emit_value(Prove_Value *v, Prove_Builder **b);

static void _json_emit_string(Prove_String *s, Prove_Builder **b) {
    *b = prove_text_write_char(*b, '"');
    /* Escape special characters */
    for (int64_t i = 0; i < s->length; i++) {
        char c = s->data[i];
        switch (c) {
            case '"':  *b = prove_text_write_cstr(*b, "\\\""); break;
            case '\\': *b = prove_text_write_cstr(*b, "\\\\"); break;
            case '\n': *b = prove_text_write_cstr(*b, "\\n"); break;
            case '\r': *b = prove_text_write_cstr(*b, "\\r"); break;
            case '\t': *b = prove_text_write_cstr(*b, "\\t"); break;
            default:
                *b = prove_text_write_char(*b, c);
                break;
        }
    }
    *b = prove_text_write_char(*b, '"');
}

static void _json_emit_value(Prove_Value *v, Prove_Builder **b) {
    if (!v || v->tag == PROVE_VALUE_NULL) {
        *b = prove_text_write_cstr(*b, "null");
        return;
    }
    switch (v->tag) {
        case PROVE_VALUE_TEXT:
            _json_emit_string(v->text, b);
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
                if (i > 0) *b = prove_text_write_char(*b, ',');
                Prove_Value *elem = (Prove_Value *)prove_list_get(v->array, i);
                _json_emit_value(elem, b);
            }
            *b = prove_text_write_char(*b, ']');
            break;
        }
        case PROVE_VALUE_OBJECT: {
            *b = prove_text_write_char(*b, '{');
            Prove_List *keys = prove_table_keys(v->object);
            int64_t nkeys = prove_list_len(keys);
            for (int64_t i = 0; i < nkeys; i++) {
                if (i > 0) *b = prove_text_write_char(*b, ',');
                Prove_String *key = (Prove_String *)prove_list_get(keys, i);
                _json_emit_string(key, b);
                *b = prove_text_write_char(*b, ':');
                Prove_Option opt = prove_table_get(key, v->object);
                if (prove_option_is_some(opt)) {
                    _json_emit_value((Prove_Value *)opt.value, b);
                } else {
                    *b = prove_text_write_cstr(*b, "null");
                }
            }
            *b = prove_text_write_char(*b, '}');
            break;
        }
        default:
            *b = prove_text_write_cstr(*b, "null");
            break;
    }
}

Prove_String *prove_emit_json(Prove_Value *value) {
    Prove_Builder *b = prove_text_builder();
    _json_emit_value(value, &b);
    Prove_String *result = prove_text_build(b);
    free(b);
    return result;
}

bool prove_validates_json(Prove_String *source) {
    JsonParser p;
    p.src = source->data;
    p.len = source->length;
    p.pos = 0;
    p.err[0] = '\0';
    Prove_Value *val = _json_parse_value(&p);
    return val != NULL;
}
