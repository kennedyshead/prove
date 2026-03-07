#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_pattern.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    prove_println(prove_string_concat(prove_string_from_cstr("test 'hello' '[a-z]+' = "), prove_string_from_bool(prove_pattern_match(prove_string_from_cstr("hello"), prove_string_from_cstr("[a-z]+")))));
    prove_println(prove_string_concat(prove_string_from_cstr("replace = "), prove_pattern_replace(prove_string_from_cstr("hello world"), prove_string_from_cstr("world"), prove_string_from_cstr("prove"))));
    prove_runtime_cleanup();
    return 0;
}

