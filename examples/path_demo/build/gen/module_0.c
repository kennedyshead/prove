#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_path.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_String* p = prove_string_from_cstr("/home/user/file.txt");
    prove_retain(p);
    prove_println(prove_string_concat(prove_string_from_cstr("parent = "), prove_path_parent(p)));
    prove_println(prove_string_concat(prove_string_from_cstr("stem = "), prove_path_stem(p)));
    prove_println(prove_string_concat(prove_string_from_cstr("extension = "), prove_path_extension(p)));
    prove_runtime_cleanup();
    return 0;
}

