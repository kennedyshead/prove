#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_bytes.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_List *_tmp1 = prove_list_new(sizeof(int64_t), 5);
    int64_t _tmp2 = 72L;
    prove_list_push(&_tmp1, &_tmp2);
    int64_t _tmp3 = 101L;
    prove_list_push(&_tmp1, &_tmp3);
    int64_t _tmp4 = 108L;
    prove_list_push(&_tmp1, &_tmp4);
    int64_t _tmp5 = 108L;
    prove_list_push(&_tmp1, &_tmp5);
    int64_t _tmp6 = 111L;
    prove_list_push(&_tmp1, &_tmp6);
    Prove_ByteArray* data = prove_bytes_create(_tmp1);
    prove_retain(data);
    Prove_String* encoded = prove_bytes_hex_encode(data);
    prove_retain(encoded);
    prove_println(prove_string_concat(prove_string_from_cstr("hex: "), encoded));
    int64_t first = prove_bytes_at(data, 0L);
    prove_println(prove_string_concat(prove_string_from_cstr("first byte: "), prove_string_from_int(first)));
    Prove_ByteArray* decoded = prove_bytes_hex_decode(prove_string_from_cstr("48656c6c6f"));
    prove_retain(decoded);
    prove_println(prove_string_concat(prove_string_from_cstr("decoded hex: "), prove_bytes_hex_encode(decoded)));
    prove_runtime_cleanup();
    return 0;
}

