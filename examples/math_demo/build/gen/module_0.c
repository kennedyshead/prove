#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_math.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    prove_println(prove_string_concat(prove_string_from_cstr("abs(-42) = "), prove_string_from_int(prove_math_abs_int((-42L)))));
    prove_println(prove_string_concat(prove_string_from_cstr("min(3, 7) = "), prove_string_from_int(prove_math_min_int(3L, 7L))));
    prove_println(prove_string_concat(prove_string_from_cstr("max(3, 7) = "), prove_string_from_int(prove_math_max_int(3L, 7L))));
    prove_println(prove_string_concat(prove_string_from_cstr("sqrt(16.0f) = "), prove_string_from_double(prove_math_sqrt(16.0f))));
    prove_println(prove_string_concat(prove_string_from_cstr("floor(3.7f) = "), prove_string_from_int(prove_math_floor(3.7f))));
    prove_runtime_cleanup();
    return 0;
}

