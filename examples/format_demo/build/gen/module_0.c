#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_format.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    prove_println(prove_string_concat(prove_string_from_cstr("hex(255) = "), prove_format_hex(255L)));
    prove_println(prove_string_concat(prove_string_from_cstr("pad_left('hi', 10, '*') = "), prove_format_pad_left(prove_string_from_cstr("hi"), 10L, '*')));
    prove_runtime_cleanup();
    return 0;
}

