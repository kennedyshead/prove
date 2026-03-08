"""Tests for the CSV C runtime (parse/emit/validate).

Each test compiles a standalone C program that exercises the CSV parser and
checks results via exit codes and stdout.
"""

from __future__ import annotations

import textwrap

from runtime_helpers import compile_and_run


class TestCsvParse:
    def test_simple_csv(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("a,b,c\\n1,2,3\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 2) return 2;
                Prove_List *row0 = (Prove_List *)prove_list_get(rows, 0);
                if (prove_list_len(row0) != 3) return 3;
                Prove_String *cell = (Prove_String *)prove_list_get(row0, 0);
                Prove_String *expected = prove_string_from_cstr("a");
                if (!prove_string_eq(cell, expected)) return 4;
                Prove_List *row1 = (Prove_List *)prove_list_get(rows, 1);
                Prove_String *cell1 = (Prove_String *)prove_list_get(row1, 1);
                Prove_String *expected1 = prove_string_from_cstr("2");
                if (!prove_string_eq(cell1, expected1)) return 5;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_simple")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_quoted_fields_with_commas(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("name,desc\\n\\"hello, world\\",test\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 2) return 2;
                Prove_List *row1 = (Prove_List *)prove_list_get(rows, 1);
                Prove_String *cell = (Prove_String *)prove_list_get(row1, 0);
                Prove_String *expected = prove_string_from_cstr("hello, world");
                if (!prove_string_eq(cell, expected)) return 3;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_quoted_comma")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_escaped_quotes(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("val\\n\\"say \\"\\"hi\\"\\"\\\"\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 2) return 2;
                Prove_List *row1 = (Prove_List *)prove_list_get(rows, 1);
                Prove_String *cell = (Prove_String *)prove_list_get(row1, 0);
                Prove_String *expected = prove_string_from_cstr("say \\"hi\\"");
                if (!prove_string_eq(cell, expected)) return 3;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_escaped_quotes")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_empty_fields(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("a,,c\\n,b,\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 2) return 2;
                Prove_List *row0 = (Prove_List *)prove_list_get(rows, 0);
                if (prove_list_len(row0) != 3) return 3;
                Prove_String *empty = prove_string_from_cstr("");
                Prove_String *cell1 = (Prove_String *)prove_list_get(row0, 1);
                if (!prove_string_eq(cell1, empty)) return 4;
                Prove_List *row1 = (Prove_List *)prove_list_get(rows, 1);
                Prove_String *first = (Prove_String *)prove_list_get(row1, 0);
                if (!prove_string_eq(first, empty)) return 5;
                Prove_String *last = (Prove_String *)prove_list_get(row1, 2);
                if (!prove_string_eq(last, empty)) return 6;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_empty_fields")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_single_column(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("one\\ntwo\\nthree\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 3) return 2;
                Prove_List *row0 = (Prove_List *)prove_list_get(rows, 0);
                if (prove_list_len(row0) != 1) return 3;
                Prove_String *cell = (Prove_String *)prove_list_get(row0, 0);
                Prove_String *expected = prove_string_from_cstr("one");
                if (!prove_string_eq(cell, expected)) return 4;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_single_col")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_crlf_line_endings(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("a,b\\r\\nc,d\\r\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 2) return 2;
                Prove_List *row1 = (Prove_List *)prove_list_get(rows, 1);
                Prove_String *cell = (Prove_String *)prove_list_get(row1, 0);
                Prove_String *expected = prove_string_from_cstr("c");
                if (!prove_string_eq(cell, expected)) return 3;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_crlf")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_empty_input(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                if (prove_list_len(rows) != 0) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_empty")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestCsvEmit:
    def test_emit_simple(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            #include <string.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *row0 = prove_list_new(4);
                Prove_String *a = prove_string_from_cstr("a");
                Prove_String *b = prove_string_from_cstr("b");
                prove_list_push(row0, (void*)a);
                prove_list_push(row0, (void*)b);
                Prove_List *row1 = prove_list_new(4);
                Prove_String *c1 = prove_string_from_cstr("1");
                Prove_String *c2 = prove_string_from_cstr("2");
                prove_list_push(row1, (void*)c1);
                prove_list_push(row1, (void*)c2);
                Prove_List *rows = prove_list_new(4);
                prove_list_push(rows, (void*)row0);
                prove_list_push(rows, (void*)row1);
                Prove_String *out = prove_emit_csv(rows);
                Prove_String *expected = prove_string_from_cstr("a,b\\r\\n1,2\\r\\n");
                if (!prove_string_eq(out, expected)) {
                    printf("GOT: %.*s\\n", (int)out->length, out->data);
                    return 1;
                }
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_emit")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_emit_quotes_special_chars(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_List *row = prove_list_new(4);
                Prove_String *f1 = prove_string_from_cstr("hello, world");
                Prove_String *f2 = prove_string_from_cstr("say \\"hi\\"");
                prove_list_push(row, (void*)f1);
                prove_list_push(row, (void*)f2);
                Prove_List *rows = prove_list_new(4);
                prove_list_push(rows, (void*)row);
                Prove_String *out = prove_emit_csv(rows);
                Prove_String *expected = prove_string_from_cstr(
                    "\\"hello, world\\",\\"say \\"\\"hi\\"\\"\\\"\\r\\n");
                if (!prove_string_eq(out, expected)) {
                    printf("GOT: %.*s\\n", (int)out->length, out->data);
                    return 1;
                }
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_emit_special")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_roundtrip(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "name,value\\r\\n\\"hello, world\\",42\\r\\n");
                Prove_Result r = prove_parse_csv(src);
                if (prove_result_is_err(r)) return 1;
                Prove_List *rows = (Prove_List *)prove_result_unwrap_ptr(r);
                Prove_String *out = prove_emit_csv(rows);
                if (!prove_string_eq(src, out)) {
                    printf("ROUNDTRIP FAILED\\nIN:  %.*s\\nOUT: %.*s\\n",
                           (int)src->length, src->data,
                           (int)out->length, out->data);
                    return 2;
                }
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_roundtrip")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestCsvValidate:
    def test_validates_valid(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("a,b\\n1,2\\n");
                if (!prove_validates_csv(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_valid")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_validates_invalid_unterminated_quote(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("\\"unterminated\\n");
                if (prove_validates_csv(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_invalid")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_validates_empty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("");
                if (!prove_validates_csv(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="csv_valid_empty")
        assert result.returncode == 0
        assert "OK" in result.stdout
