#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_parse.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_table.h"
#include "prove_text.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_Result _tmp1 = prove_file_read(prove_string_from_cstr("config.toml"));
    if (prove_result_is_err(_tmp1)) {
        Prove_String *_tmp2 = (Prove_String*)_tmp1.error;
        if (_tmp2) fprintf(stderr, "error: %.*s\n", (int)_tmp2->length, _tmp2->data);
        prove_runtime_cleanup();
        return 1;
    }
    Prove_String* source = (Prove_String*)prove_result_unwrap_ptr(_tmp1);
    prove_retain(source);
    Prove_Result _tmp3 = prove_parse_toml(source);
    if (prove_result_is_err(_tmp3)) {
        Prove_String *_tmp4 = (Prove_String*)_tmp3.error;
        if (_tmp4) fprintf(stderr, "error: %.*s\n", (int)_tmp4->length, _tmp4->data);
        prove_runtime_cleanup();
        return 1;
    }
    Prove_Value* doc = (Prove_Value*)prove_result_unwrap_ptr(_tmp3);
    prove_retain(doc);
    Prove_Table* root = prove_value_as_object(doc);
    prove_retain(root);
    Prove_List* names = prove_table_keys(root);
    prove_retain(names);
    prove_println(prove_string_from_cstr("Parsed TOML keys:"));
    prove_println(prove_string_concat(prove_string_from_cstr("Keys: "), prove_text_join(names, prove_string_from_cstr(", "))));
    prove_runtime_cleanup();
    return 0;
}

