#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_random.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    int64_t n = prove_random_integer();
    prove_println(prove_string_concat(prove_string_from_cstr("random integer: "), prove_string_from_int(n)));
    int64_t r = prove_random_integer_range(1L, 10L);
    prove_println(prove_string_concat(prove_string_from_cstr("random 1..10: "), prove_string_from_int(r)));
    double d = prove_random_decimal();
    prove_println(prove_string_concat(prove_string_from_cstr("random decimal: "), prove_string_from_double(d)));
    bool b = prove_random_boolean();
    prove_println(prove_string_concat(prove_string_from_cstr("random boolean: "), prove_string_from_bool(b)));
    prove_runtime_cleanup();
    return 0;
}

