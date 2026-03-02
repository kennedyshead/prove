#ifndef PROVE_PARSE_H
#define PROVE_PARSE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_table.h"
#include "prove_result.h"

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
bool prove_value_is_bool(Prove_Value *v);
bool prove_value_is_array(Prove_Value *v);
bool prove_value_is_object(Prove_Value *v);
bool prove_value_is_null(Prove_Value *v);

/* ── TOML codec ──────────────────────────────────────────────── */

Prove_Result prove_parse_toml(Prove_String *source);
Prove_String *prove_emit_toml(Prove_Value *value);

/* ── JSON codec ──────────────────────────────────────────────── */

Prove_Result prove_parse_json(Prove_String *source);
Prove_String *prove_emit_json(Prove_Value *value);

#endif /* PROVE_PARSE_H */
