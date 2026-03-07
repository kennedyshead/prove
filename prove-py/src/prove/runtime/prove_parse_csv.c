/* Prove CSV parser — RFC 4180-compliant.
 *
 * - Comma delimiter, CRLF or LF line endings
 * - Quoted fields (double-quote escaping: "" → ")
 * - Returns List<List<String*>*> (rows of fields)
 */

#include "prove_parse.h"
#include "prove_text.h"
#include <string.h>
#include <stdio.h>

/* ── Parser state ────────────────────────────────────────────── */

typedef struct {
    const char *src;
    int64_t     len;
    int64_t     pos;
    char        err[256];
} CsvParser;

static bool _csv_at_end(CsvParser *p) {
    return p->pos >= p->len;
}

static char _csv_peek(CsvParser *p) {
    return p->pos < p->len ? p->src[p->pos] : '\0';
}

static char _csv_advance(CsvParser *p) {
    return p->pos < p->len ? p->src[p->pos++] : '\0';
}

/* ── Field parsing ───────────────────────────────────────────── */

/* Parse a quoted field: consumes opening ", reads until closing ",
 * handles "" escape sequences. */
static Prove_String *_csv_parse_quoted(CsvParser *p) {
    p->pos++; /* skip opening " */
    Prove_Builder *b = prove_text_builder();

    while (!_csv_at_end(p)) {
        char c = _csv_advance(p);
        if (c == '"') {
            /* Check for escaped quote "" */
            if (!_csv_at_end(p) && _csv_peek(p) == '"') {
                b = prove_text_write_char(b, '"');
                p->pos++; /* skip second " */
            } else {
                /* End of quoted field */
                return prove_text_build(b);
            }
        } else {
            b = prove_text_write_char(b, c);
        }
    }

    /* Unterminated quoted field */
    snprintf(p->err, sizeof(p->err), "unterminated quoted field");
    return NULL;
}

/* Parse an unquoted field: reads until comma, CR, LF, or end. */
static Prove_String *_csv_parse_unquoted(CsvParser *p) {
    Prove_Builder *b = prove_text_builder();

    while (!_csv_at_end(p)) {
        char c = _csv_peek(p);
        if (c == ',' || c == '\r' || c == '\n')
            break;
        b = prove_text_write_char(b, c);
        p->pos++;
    }

    return prove_text_build(b);
}

/* ── Row parsing ─────────────────────────────────────────────── */

/* Parse a single row. Returns a List of Prove_String*.
 * Advances past the line ending (CRLF or LF). */
static Prove_List *_csv_parse_row(CsvParser *p) {
    Prove_List *fields = prove_list_new(sizeof(Prove_String *), 8);

    for (;;) {
        Prove_String *field;

        if (_csv_peek(p) == '"') {
            field = _csv_parse_quoted(p);
            if (!field) return NULL;
        } else {
            field = _csv_parse_unquoted(p);
        }

        prove_list_push(&fields, &field);

        if (_csv_at_end(p))
            break;

        char c = _csv_peek(p);
        if (c == ',') {
            p->pos++; /* skip comma, continue to next field */
        } else {
            /* End of row — skip CRLF or LF */
            if (c == '\r') p->pos++;
            if (!_csv_at_end(p) && _csv_peek(p) == '\n') p->pos++;
            break;
        }
    }

    return fields;
}

/* ── Public API ──────────────────────────────────────────────── */

Prove_Result prove_parse_csv(Prove_String *source) {
    CsvParser p;
    p.src = source->data;
    p.len = source->length;
    p.pos = 0;
    p.err[0] = '\0';

    Prove_List *rows = prove_list_new(sizeof(Prove_List *), 8);

    while (!_csv_at_end(&p)) {
        /* Skip trailing empty lines */
        if (_csv_peek(&p) == '\n') { p.pos++; continue; }
        if (_csv_peek(&p) == '\r') {
            p.pos++;
            if (!_csv_at_end(&p) && _csv_peek(&p) == '\n') p.pos++;
            continue;
        }

        Prove_List *row = _csv_parse_row(&p);
        if (!row) {
            return prove_result_err(prove_string_from_cstr(p.err));
        }
        prove_list_push(&rows, &row);
    }

    return prove_result_ok_ptr(rows);
}

Prove_String *prove_emit_csv(Prove_List *rows) {
    Prove_Builder *b = prove_text_builder();
    int64_t nrows = prove_list_len(rows);

    for (int64_t i = 0; i < nrows; i++) {
        Prove_List *row = *(Prove_List **)prove_list_get(rows, i);
        int64_t ncols = prove_list_len(row);

        for (int64_t j = 0; j < ncols; j++) {
            if (j > 0) b = prove_text_write_char(b, ',');

            Prove_String *field = *(Prove_String **)prove_list_get(row, j);
            const char *data = field->data;
            int64_t len = field->length;

            /* Check if quoting is needed */
            bool needs_quote = false;
            for (int64_t k = 0; k < len; k++) {
                if (data[k] == ',' || data[k] == '"' ||
                    data[k] == '\r' || data[k] == '\n') {
                    needs_quote = true;
                    break;
                }
            }

            if (needs_quote) {
                b = prove_text_write_char(b, '"');
                for (int64_t k = 0; k < len; k++) {
                    if (data[k] == '"')
                        b = prove_text_write_char(b, '"'); /* escape " as "" */
                    b = prove_text_write_char(b, data[k]);
                }
                b = prove_text_write_char(b, '"');
            } else {
                for (int64_t k = 0; k < len; k++)
                    b = prove_text_write_char(b, data[k]);
            }
        }

        b = prove_text_write_char(b, '\r');
        b = prove_text_write_char(b, '\n');
    }

    return prove_text_build(b);
}

bool prove_validates_csv(Prove_String *source) {
    CsvParser p;
    p.src = source->data;
    p.len = source->length;
    p.pos = 0;
    p.err[0] = '\0';

    while (!_csv_at_end(&p)) {
        if (_csv_peek(&p) == '\n') { p.pos++; continue; }
        if (_csv_peek(&p) == '\r') {
            p.pos++;
            if (!_csv_at_end(&p) && _csv_peek(&p) == '\n') p.pos++;
            continue;
        }

        Prove_List *row = _csv_parse_row(&p);
        if (!row) return false;
    }

    return true;
}
