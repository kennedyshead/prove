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
#include "prove_text.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    Prove_String* text = prove_string_from_cstr("  Hello, World!  ");
    prove_retain(text);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Original: '"), text), prove_string_from_cstr("'")));
    prove_println(prove_string_concat(prove_string_from_cstr("Length: "), prove_string_from_int(prove_text_length(text))));
    Prove_String* trimmed = prove_text_trim(text);
    prove_retain(trimmed);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Trimmed: '"), trimmed), prove_string_from_cstr("'")));
    Prove_String* upper_text = prove_text_to_upper(trimmed);
    prove_retain(upper_text);
    Prove_String* lower_text = prove_text_to_lower(trimmed);
    prove_retain(lower_text);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Upper: '"), upper_text), prove_string_from_cstr("'")));
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Lower: '"), lower_text), prove_string_from_cstr("'")));
    Prove_String* slice_text = prove_text_slice(text, 0L, 5L);
    prove_retain(slice_text);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Slice [0:5]: '"), slice_text), prove_string_from_cstr("'")));
    bool starts = prove_text_starts_with(text, prove_string_from_cstr("  Hello"));
    bool ends = prove_text_ends_with(text, prove_string_from_cstr("!"));
    prove_println(prove_string_concat(prove_string_from_cstr("Starts with '  Hello': "), prove_string_from_bool(starts)));
    prove_println(prove_string_concat(prove_string_from_cstr("Ends with '!': "), prove_string_from_bool(ends)));
    bool contains_w = prove_text_contains(text, prove_string_from_cstr("World"));
    prove_println(prove_string_concat(prove_string_from_cstr("Contains 'World': "), prove_string_from_bool(contains_w)));
    Prove_String* csv = prove_string_from_cstr("apple,banana,cherry");
    prove_retain(csv);
    Prove_List* parts = prove_text_split(csv, prove_string_from_cstr(","));
    prove_retain(parts);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Split into "), prove_string_from_int(prove_list_ops_length(parts))), prove_string_from_cstr(" parts")));
    Prove_List *_tmp1 = prove_list_new(sizeof(Prove_String*), 3);
    Prove_String* _tmp2 = prove_string_from_cstr("one");
    prove_list_push(&_tmp1, &_tmp2);
    Prove_String* _tmp3 = prove_string_from_cstr("two");
    prove_list_push(&_tmp1, &_tmp3);
    Prove_String* _tmp4 = prove_string_from_cstr("three");
    prove_list_push(&_tmp1, &_tmp4);
    Prove_List* items = _tmp1;
    prove_retain(items);
    Prove_String* joined = prove_text_join(items, prove_string_from_cstr(", "));
    prove_retain(joined);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Joined: '"), joined), prove_string_from_cstr("'")));
    Prove_String* replaced = prove_text_replace(prove_string_from_cstr("hello world"), prove_string_from_cstr("world"), prove_string_from_cstr("Prove"));
    prove_retain(replaced);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Replaced: '"), replaced), prove_string_from_cstr("'")));
    Prove_String* repeated = prove_text_repeat(prove_string_from_cstr("ha"), 3L);
    prove_retain(repeated);
    prove_println(prove_string_concat(prove_string_concat(prove_string_from_cstr("Repeated: '"), repeated), prove_string_from_cstr("'")));
    prove_println(prove_string_from_cstr("All text operations completed!"));
    prove_runtime_cleanup();
    return 0;
}

