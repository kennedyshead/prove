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


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_Url* parsed = prove_parse_url(prove_string_from_cstr("https://example.com/path"));
    prove_retain(parsed);
    prove_println(prove_string_from_cstr("parsed url successfully"));
    prove_runtime_cleanup();
    return 0;
}

