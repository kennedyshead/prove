#ifndef PROVE_PARSE_H
#define PROVE_PARSE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_table.h"
#include "prove_result.h"

/* Forward declaration for ByteArray (defined in prove_bytes.h) */
typedef struct Prove_ByteArray Prove_ByteArray;

/* ── Value tagged union ──────────────────────────────────────── */

typedef enum {
    PROVE_VALUE_NULL    = 0,
    PROVE_VALUE_TEXT    = 1,
    PROVE_VALUE_NUMBER  = 2,
    PROVE_VALUE_DECIMAL = 3,
    PROVE_VALUE_BOOL    = 4,
    PROVE_VALUE_ARRAY   = 5,
    PROVE_VALUE_OBJECT  = 6,
} Prove_ValueTag;

typedef struct Prove_Value Prove_Value;

struct Prove_Value {
    Prove_Header   header;
    Prove_ValueTag tag;
    union {
        Prove_String *text;
        int64_t       number;
        double        decimal;
        bool          boolean;
        Prove_List   *array;   /* List<Prove_Value*> */
        Prove_Table  *object;  /* Table<Prove_Value*> */
    };
};

/* ── Constructors ────────────────────────────────────────────── */

Prove_Value *prove_value_null(void);
Prove_Value *prove_value_text(Prove_String *s);
Prove_Value *prove_value_number(int64_t n);
Prove_Value *prove_value_decimal(double d);
Prove_Value *prove_value_bool(bool b);
Prove_Value *prove_value_array(Prove_List *arr);
Prove_Value *prove_value_object(Prove_Table *obj);

/* ── Accessors ───────────────────────────────────────────────── */

Prove_String *prove_value_tag(Prove_Value *v);
Prove_String *prove_value_as_text(Prove_Value *v);
int64_t       prove_value_as_number(Prove_Value *v);
double        prove_value_as_decimal(Prove_Value *v);
bool          prove_value_as_bool(Prove_Value *v);
Prove_List   *prove_value_as_array(Prove_Value *v);
Prove_Table  *prove_value_as_object(Prove_Value *v);

/* ── Type checks ─────────────────────────────────────────────── */

bool prove_value_is_text(Prove_Value *v);
bool prove_value_is_number(Prove_Value *v);
bool prove_value_is_decimal(Prove_Value *v);
bool prove_value_is_boolean(Prove_Value *v);
bool prove_value_is_array(Prove_Value *v);
bool prove_value_is_object(Prove_Value *v);
bool prove_value_is_unit(Prove_Value *v);

/* ── TOML codec ──────────────────────────────────────────────── */

Prove_Result prove_parse_toml(Prove_String *source);
Prove_String *prove_emit_toml(Prove_Value *value);

/* ── JSON codec ──────────────────────────────────────────────── */

Prove_Result prove_parse_json(Prove_String *source);
Prove_String *prove_emit_json(Prove_Value *value);

/* ── String validation ───────────────────────────────────────── */

bool prove_validates_json(Prove_String *source);
bool prove_validates_toml(Prove_String *source);

/* ── Record → Value conversion ───────────────────────────────── */

/* Identity passthrough when source is already a Value. */
Prove_Value *prove_creates_value(Prove_Value *v);

/* Validates that a Value is non-null (always true for records). */
bool prove_validates_value(Prove_Value *v);

/* ── URL ────────────────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *scheme;
    Prove_String *host;
    int64_t       port;      /* -1 = not set */
    Prove_String *path;
    Prove_String *query;     /* NULL = not set */
    Prove_String *fragment;  /* NULL = not set */
} Prove_Url;

Prove_Url    *prove_parse_url(Prove_String *raw);
Prove_Url    *prove_parse_url_create(Prove_String *scheme, Prove_String *host,
                                      Prove_String *path);
bool          prove_parse_url_validates(Prove_String *raw);
Prove_Url    *prove_parse_url_transform(Prove_Url *source, Prove_Table *params);
Prove_String *prove_parse_url_host_reads(Prove_Url *url);
int64_t       prove_parse_url_port_reads(Prove_Url *url);

/* ── Base64 ─────────────────────────────────────────────────── */

Prove_ByteArray *prove_parse_base64_decode(Prove_String *encoded);
Prove_String    *prove_parse_base64_encode(Prove_ByteArray *data);
bool             prove_parse_base64_validates(Prove_String *encoded);

/* ── CLI arguments ─────────────────────────────────────────── */

Prove_Value *prove_parse_arguments(Prove_List *args);

/* ── CSV ───────────────────────────────────────────────────── */

Prove_Result     prove_parse_csv(Prove_String *source);
Prove_String    *prove_emit_csv(Prove_List *rows);
bool             prove_validates_csv(Prove_String *source);

/* ── Token (generic) ──────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *text;
    int64_t       start;
    int64_t       end;
    int64_t       kind;
} Prove_Token;

/* ── Rule (tokenization rule) ─────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *pattern;   /* regex pattern for this token kind */
    int64_t       kind;      /* kind tag assigned to matches */
} Prove_Rule;

/* ── Generic tokenizer ────────────────────────────────────── */

Prove_List   *prove_parse_tokens(Prove_String *source, Prove_List *rules);

/* ── Rule constructor ─────────────────────────────────────── */

Prove_Rule   *prove_parse_rule(Prove_String *pattern, int64_t kind);

/* ── Token accessors ──────────────────────────────────────── */

Prove_String *prove_parse_token_text(Prove_Token *t);
int64_t       prove_parse_token_start(Prove_Token *t);
int64_t       prove_parse_token_end(Prove_Token *t);
int64_t       prove_parse_token_kind(Prove_Token *t);

#endif /* PROVE_PARSE_H */
