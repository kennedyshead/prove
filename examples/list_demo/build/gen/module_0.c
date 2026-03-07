#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_list_ops.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_List* numbers = prove_list_ops_range(1L, 6L);
    prove_retain(numbers);
    prove_println(prove_string_concat(prove_string_from_cstr("length = "), prove_string_from_int(prove_list_ops_length(numbers))));
    prove_println(prove_string_concat(prove_string_from_cstr("empty = "), prove_string_from_bool(prove_list_ops_empty(numbers))));
    prove_runtime_cleanup();
    return 0;
}

