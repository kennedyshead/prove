#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_bytes.h"
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
    Prove_Url* parsed = prove_parse_url(prove_string_from_cstr("https://example.com/path?q=1"));
    prove_retain(parsed);
    prove_println(prove_string_from_cstr("parsed URL ok"));
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
    Prove_String* encoded = prove_parse_base64_encode(data);
    prove_retain(encoded);
    prove_println(prove_string_concat(prove_string_from_cstr("base64: "), encoded));
    prove_runtime_cleanup();
    return 0;
}

