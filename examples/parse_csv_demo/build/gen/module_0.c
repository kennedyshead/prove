#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_convert.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_list_ops.h"
#include "prove_parse.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_String* source = prove_string_from_cstr("name,age,city\nAlice,30,London\nBob,25,Paris\n");
    prove_retain(source);
    Prove_Result _tmp1 = prove_parse_csv(source);
    if (prove_result_is_err(_tmp1)) {
        Prove_String *_tmp2 = (Prove_String*)_tmp1.error;
        if (_tmp2) fprintf(stderr, "error: %.*s\n", (int)_tmp2->length, _tmp2->data);
        prove_runtime_cleanup();
        return 1;
    }
    Prove_List* rows = (void*)prove_result_unwrap_ptr(_tmp1);
    prove_retain(rows);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Parsed "), prove_convert_string_int(prove_list_ops_length(rows))), prove_string_from_cstr(" rows")));
    Prove_String* output = prove_emit_csv(rows);
    prove_retain(output);
    prove_println(prove_string_from_cstr("Emitted CSV:"));
    prove_println(output);
    bool is_valid = prove_validates_csv(source);
    prove_println(prove_string_concat(prove_string_from_cstr("Valid CSV: "), prove_convert_string_bool(is_valid)));
    prove_runtime_cleanup();
    return 0;
}

