#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "prove_region.h"
#include "prove_character.h"
#include "prove_input_output.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_runtime.h"
#include "prove_string.h"


int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);
    char a = 'A';
    char z = 'Z';
    char num = '5';
    char space_char = ' ';
    char lower_a = 'a';
    prove_println(prove_string_concat(prove_string_from_cstr("'A' alpha: "), prove_string_from_bool(prove_character_alpha(a))));
    prove_println(prove_string_concat(prove_string_from_cstr("'A' digit: "), prove_string_from_bool(prove_character_digit(a))));
    prove_println(prove_string_concat(prove_string_from_cstr("'A' alnum: "), prove_string_from_bool(prove_character_alnum(a))));
    prove_println(prove_string_concat(prove_string_from_cstr("'A' upper: "), prove_string_from_bool(prove_character_upper(a))));
    prove_println(prove_string_concat(prove_string_from_cstr("'A' lower: "), prove_string_from_bool(prove_character_lower(a))));
    prove_println(prove_string_concat(prove_string_from_cstr("'5' alpha: "), prove_string_from_bool(prove_character_alpha(num))));
    prove_println(prove_string_concat(prove_string_from_cstr("'5' digit: "), prove_string_from_bool(prove_character_digit(num))));
    prove_println(prove_string_concat(prove_string_from_cstr("'5' alnum: "), prove_string_from_bool(prove_character_alnum(num))));
    prove_println(prove_string_concat(prove_string_from_cstr("' ' space: "), prove_string_from_bool(prove_character_space(space_char))));
    prove_println(prove_string_concat(prove_string_from_cstr("'a' upper: "), prove_string_from_bool(prove_character_upper(lower_a))));
    prove_println(prove_string_concat(prove_string_from_cstr("'a' lower: "), prove_string_from_bool(prove_character_lower(lower_a))));
    Prove_String* text = prove_string_from_cstr("Hello");
    prove_retain(text);
    char char_at_0 = prove_character_at(text, 0L);
    char char_at_4 = prove_character_at(text, 4L);
    prove_println(prove_string_concat(prove_string_from_cstr("First char of 'Hello': "), prove_string_from_char(char_at_0)));
    prove_println(prove_string_concat(prove_string_from_cstr("Last char of 'Hello': "), prove_string_from_char(char_at_4)));
    prove_println(prove_string_from_cstr("All character operations completed!"));
    prove_runtime_cleanup();
    return 0;
}

