/*
 * prove_parse_args.c — Parse CLI arguments into a Value
 *
 * Input:  List<String> (from prove_io_process_inputs())
 * Output: Value object with:
 *   "args"   → array of positional strings
 *   "kwargs" → object of --key/value or --flag/null pairs
 *
 * Rules:
 *   --key value  → kwargs.key = "value"  (if next arg doesn't start with --)
 *   --flag       → kwargs.flag = null    (bare flag or next starts with --)
 *   everything else → positional, appended to args array
 */

#include "prove_parse.h"
#include <string.h>

Prove_Value *prove_parse_arguments(Prove_List *args) {
    Prove_List  *positional = prove_list_new(4);
    Prove_Table *kwargs     = prove_table_new();

    int64_t len = prove_list_len(args);
    int64_t i   = 0;

    while (i < len) {
        Prove_String *arg = (Prove_String *)prove_list_get(args, i);
        const char   *raw = arg->data;
        int64_t       slen = arg->length;

        if (slen > 2 && raw[0] == '-' && raw[1] == '-') {
            /* Strip leading "--" to get the key name */
            Prove_String *key = prove_string_new(raw + 2, slen - 2);

            /* Check if next arg exists and is not a flag */
            if (i + 1 < len) {
                Prove_String *next = (Prove_String *)prove_list_get(args, i + 1);
                if (next->length >= 2 && next->data[0] == '-' && next->data[1] == '-') {
                    /* Next is a flag — current is bare */
                    kwargs = prove_table_add(key, prove_value_null(), kwargs);
                } else {
                    /* Next is the value */
                    kwargs = prove_table_add(key, prove_value_text(next), kwargs);
                    i++; /* consume the value */
                }
            } else {
                /* Last arg — bare flag */
                kwargs = prove_table_add(key, prove_value_null(), kwargs);
            }
        } else {
            /* Positional argument */
            prove_list_push(positional, prove_value_text(arg));
        }

        i++;
    }

    /* Build the result object: {"args": [...], "kwargs": {...}} */
    Prove_Table *result = prove_table_new();
    result = prove_table_add(
        prove_string_from_cstr("args"),
        prove_value_array(positional),
        result
    );
    result = prove_table_add(
        prove_string_from_cstr("kwargs"),
        prove_value_object(kwargs),
        result
    );

    return prove_value_object(result);
}
