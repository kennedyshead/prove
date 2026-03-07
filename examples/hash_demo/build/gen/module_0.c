#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_bytes.h"
#include "prove_hash_crypto.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_String* h256 = prove_crypto_sha256_string(prove_string_from_cstr("hello"));
    prove_retain(h256);
    prove_println(prove_string_concat(prove_string_from_cstr("sha256('hello'): "), h256));
    Prove_String* h512 = prove_crypto_sha512_string(prove_string_from_cstr("hello"));
    prove_retain(h512);
    prove_println(prove_string_concat(prove_string_from_cstr("sha512('hello'): "), h512));
    prove_runtime_cleanup();
    return 0;
}

