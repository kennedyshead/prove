"""Tests for the Bytes C runtime module."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestBytesFromString:
    def test_from_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                printf("%lld\\n", (long long)ba->length);
                for (int64_t i = 0; i < ba->length; i++) {
                    printf("%c", ba->data[i]);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="from_str")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "5"
        assert lines[1] == "hello"

    def test_from_empty_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                printf("%lld\\n", (long long)ba->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="from_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestBytesValidates:
    def test_validates_nonempty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hi");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                printf("%d\\n", prove_bytes_validates(ba) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="val_ok")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_validates_empty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                printf("%d\\n", prove_bytes_validates(ba) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="val_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_validates_null(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                printf("%d\\n", prove_bytes_validates(NULL) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="val_null")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestBytesSlice:
    def test_slice(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello world");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                Prove_ByteArray *sl = prove_bytes_slice(ba, 6, 5);
                printf("%lld\\n", (long long)sl->length);
                for (int64_t i = 0; i < sl->length; i++) {
                    printf("%c", sl->data[i]);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="slice")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "5"
        assert lines[1] == "world"

    def test_slice_out_of_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hi");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                Prove_ByteArray *sl = prove_bytes_slice(ba, 0, 100);
                printf("%lld\\n", (long long)sl->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="slice_oob")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestBytesConcat:
    def test_concat(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s1 = prove_string_from_cstr("hello");
                Prove_String *s2 = prove_string_from_cstr(" world");
                Prove_ByteArray *ba1 = prove_bytes_from_string(s1);
                Prove_ByteArray *ba2 = prove_bytes_from_string(s2);
                Prove_ByteArray *cat = prove_bytes_concat(ba1, ba2);
                printf("%lld\\n", (long long)cat->length);
                for (int64_t i = 0; i < cat->length; i++) {
                    printf("%c", cat->data[i]);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="concat")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "11"
        assert lines[1] == "hello world"


class TestBytesHex:
    def test_hex_encode(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("AB");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                Prove_String *hex = prove_bytes_hex_encode(ba);
                printf("%.*s\\n", (int)hex->length, hex->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hex_enc")
        assert result.returncode == 0
        assert result.stdout.strip() == "4142"

    def test_hex_decode(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *hex = prove_string_from_cstr("4142");
                Prove_ByteArray *ba = prove_bytes_hex_decode(hex);
                printf("%lld\\n", (long long)ba->length);
                for (int64_t i = 0; i < ba->length; i++) {
                    printf("%c", ba->data[i]);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hex_dec")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "2"
        assert lines[1] == "AB"

    def test_hex_roundtrip(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("Hello!");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                Prove_String *hex = prove_bytes_hex_encode(ba);
                Prove_ByteArray *decoded = prove_bytes_hex_decode(hex);
                int same = (ba->length == decoded->length);
                if (same) {
                    for (int64_t i = 0; i < ba->length; i++) {
                        if (ba->data[i] != decoded->data[i]) { same = 0; break; }
                    }
                }
                printf("%d\\n", same);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hex_rt")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_hex_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *good = prove_string_from_cstr("4142ab");
                Prove_String *bad_odd = prove_string_from_cstr("414");
                Prove_String *bad_char = prove_string_from_cstr("41GG");
                printf("%d\\n", prove_bytes_hex_validates(good) ? 1 : 0);
                printf("%d\\n", prove_bytes_hex_validates(bad_odd) ? 1 : 0);
                printf("%d\\n", prove_bytes_hex_validates(bad_char) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hex_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # valid hex
        assert lines[1] == "0"  # odd length
        assert lines[2] == "0"  # invalid chars

    def test_hex_encode_empty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                Prove_String *hex = prove_bytes_hex_encode(ba);
                printf("%lld\\n", (long long)hex->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="hex_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestBytesAt:
    def test_at(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("ABC");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                printf("%lld\\n", (long long)prove_bytes_at(ba, 0));
                printf("%lld\\n", (long long)prove_bytes_at(ba, 1));
                printf("%lld\\n", (long long)prove_bytes_at(ba, 2));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="at")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "65"  # 'A'
        assert lines[1] == "66"  # 'B'
        assert lines[2] == "67"  # 'C'

    def test_at_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_bytes.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("AB");
                Prove_ByteArray *ba = prove_bytes_from_string(s);
                printf("%d\\n", prove_bytes_at_validates(ba, 0) ? 1 : 0);
                printf("%d\\n", prove_bytes_at_validates(ba, 1) ? 1 : 0);
                printf("%d\\n", prove_bytes_at_validates(ba, 2) ? 1 : 0);
                printf("%d\\n", prove_bytes_at_validates(ba, -1) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="at_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # index 0 valid
        assert lines[1] == "1"  # index 1 valid
        assert lines[2] == "0"  # index 2 out of bounds
        assert lines[3] == "0"  # negative index
