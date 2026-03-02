/* Prove JSON parser — hand-rolled recursive descent.
 *
 * Supports full JSON: objects, arrays, strings, numbers, booleans, null.
 */

#include "prove_parse.h"
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

/* Parse a JSON string */
static Prove_String *_json_parse_string(JsonParser *p) {
    if (_json_peek(p) != '"') return NULL;
    p->pos++; /* skip " */

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
                case '/':  buf[bi++] = '/';  break;
                case 'u': {
                    /* \uXXXX — just pass through as-is for now */
                    buf[bi++] = '\\';
                    buf[bi++] = 'u';
                    break;
                }
                default: buf[bi++] = esc; break;
            }
        } else {
            buf[bi++] = p->src[p->pos];
        }
        p->pos++;
        if (bi >= 4095) break;
    }
    if (p->pos < p->len) p->pos++; /* skip closing " */
    return prove_string_new(buf, bi);
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
    Prove_List *arr = prove_list_new(sizeof(Prove_Value *), 8);
    _json_skip_ws(p);

    if (_json_peek(p) == ']') {
        p->pos++;
        return prove_value_array(arr);
    }

    while (!_json_at_end(p)) {
        Prove_Value *elem = _json_parse_value(p);
        if (!elem) return NULL;
        prove_list_push(&arr, &elem);
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

/* ── JSON emitter ────────────────────────────────────────────── */

static void _json_emit_value(Prove_Value *v, Prove_String **out);

static void _jappend(Prove_String **out, const char *cstr) {
    *out = prove_string_concat(*out, prove_string_from_cstr(cstr));
}

static void _json_emit_string(Prove_String *s, Prove_String **out) {
    _jappend(out, "\"");
    /* Escape special characters */
    for (int64_t i = 0; i < s->length; i++) {
        char c = s->data[i];
        switch (c) {
            case '"':  _jappend(out, "\\\""); break;
            case '\\': _jappend(out, "\\\\"); break;
            case '\n': _jappend(out, "\\n"); break;
            case '\r': _jappend(out, "\\r"); break;
            case '\t': _jappend(out, "\\t"); break;
            default: {
                char buf[2] = {c, '\0'};
                _jappend(out, buf);
                break;
            }
        }
    }
    _jappend(out, "\"");
}

static void _json_emit_value(Prove_Value *v, Prove_String **out) {
    if (!v || v->tag == PROVE_VALUE_NULL) {
        _jappend(out, "null");
        return;
    }
    switch (v->tag) {
        case PROVE_VALUE_TEXT:
            _json_emit_string(v->text, out);
            break;
        case PROVE_VALUE_NUMBER: {
            char buf[32];
            snprintf(buf, sizeof(buf), "%lld", (long long)v->number);
            _jappend(out, buf);
            break;
        }
        case PROVE_VALUE_DECIMAL: {
            char buf[64];
            snprintf(buf, sizeof(buf), "%g", v->decimal);
            _jappend(out, buf);
            break;
        }
        case PROVE_VALUE_BOOL:
            _jappend(out, v->boolean ? "true" : "false");
            break;
        case PROVE_VALUE_ARRAY: {
            _jappend(out, "[");
            int64_t n = prove_list_len(v->array);
            for (int64_t i = 0; i < n; i++) {
                if (i > 0) _jappend(out, ",");
                Prove_Value *elem = *(Prove_Value **)prove_list_get(v->array, i);
                _json_emit_value(elem, out);
            }
            _jappend(out, "]");
            break;
        }
        case PROVE_VALUE_OBJECT: {
            _jappend(out, "{");
            Prove_List *keys = prove_table_keys(v->object);
            int64_t nkeys = prove_list_len(keys);
            for (int64_t i = 0; i < nkeys; i++) {
                if (i > 0) _jappend(out, ",");
                Prove_String *key = *(Prove_String **)prove_list_get(keys, i);
                _json_emit_string(key, out);
                _jappend(out, ":");
                Prove_Option_voidptr opt = prove_table_get(key, v->object);
                if (Prove_Option_voidptr_is_some(opt)) {
                    _json_emit_value((Prove_Value *)opt.value, out);
                } else {
                    _jappend(out, "null");
                }
            }
            _jappend(out, "}");
            break;
        }
        default:
            _jappend(out, "null");
            break;
    }
}

Prove_String *prove_emit_json(Prove_Value *value) {
    Prove_String *out = prove_string_from_cstr("");
    _json_emit_value(value, &out);
    return out;
}
