"""Tests for the Parse C runtime (TOML/JSON codecs).

Each test compiles a standalone C program that exercises the parser and
checks results via exit codes and stdout.
"""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


# ── TOML tests ────────────────────────────────────────────────────


class TestTomlParse:
    def test_key_value_string(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("name = \\"hello\\"\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Table *t = (Prove_Table *)prove_result_unwrap_ptr(r);
                Prove_String *key = prove_string_from_cstr("name");
                Prove_Option opt = prove_table_get(key, t);
                if (prove_option_is_none(opt)) return 3;
                Prove_Value *val = (Prove_Value *)opt.value;
                if (!prove_value_is_text(val)) return 4;
                Prove_String *expected = prove_string_from_cstr("hello");
                if (!prove_string_eq(prove_value_as_text(val), expected)) return 5;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="toml_kv")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_key_value_integer(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("port = 8080\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Table *t = (Prove_Table *)prove_result_unwrap_ptr(r);
                Prove_String *key = prove_string_from_cstr("port");
                Prove_Option opt = prove_table_get(key, t);
                if (prove_option_is_none(opt)) return 2;
                Prove_Value *val = (Prove_Value *)opt.value;
                if (!prove_value_is_number(val)) return 3;
                if (prove_value_as_number(val) != 8080) return 4;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="toml_int")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_key_value_bool(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("debug = true\\nverbose = false\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Table *t = (Prove_Table *)prove_result_unwrap_ptr(r);

                Prove_String *k1 = prove_string_from_cstr("debug");
                Prove_Option o1 = prove_table_get(k1, t);
                if (prove_option_is_none(o1)) return 2;
                Prove_Value *v1 = (Prove_Value *)o1.value;
                if (!prove_value_as_bool(v1)) return 3;

                Prove_String *k2 = prove_string_from_cstr("verbose");
                Prove_Option o2 = prove_table_get(k2, t);
                if (prove_option_is_none(o2)) return 4;
                Prove_Value *v2 = (Prove_Value *)o2.value;
                if (prove_value_as_bool(v2)) return 5;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="toml_bool")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_section(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "[package]\\nname = \\"myapp\\"\\nversion = \\"1.0\\"\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Table *t = (Prove_Table *)prove_result_unwrap_ptr(r);

                Prove_String *pkg_key = prove_string_from_cstr("package");
                Prove_Option opt = prove_table_get(pkg_key, t);
                if (prove_option_is_none(opt)) return 2;
                Prove_Value *pkg = (Prove_Value *)opt.value;
                if (!prove_value_is_object(pkg)) return 3;

                Prove_Table *pkg_tbl = prove_value_as_object(pkg);
                Prove_String *name_key = prove_string_from_cstr("name");
                Prove_Option nopt = prove_table_get(name_key, pkg_tbl);
                if (prove_option_is_none(nopt)) return 4;
                Prove_Value *name_val = (Prove_Value *)nopt.value;
                Prove_String *expected = prove_string_from_cstr("myapp");
                if (!prove_string_eq(prove_value_as_text(name_val), expected)) return 5;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="toml_section")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_array(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("nums = [1, 2, 3]\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Table *t = (Prove_Table *)prove_result_unwrap_ptr(r);

                Prove_String *key = prove_string_from_cstr("nums");
                Prove_Option opt = prove_table_get(key, t);
                if (prove_option_is_none(opt)) return 2;
                Prove_Value *val = (Prove_Value *)opt.value;
                if (!prove_value_is_array(val)) return 3;

                Prove_List *arr = prove_value_as_array(val);
                if (prove_list_len(arr) != 3) return 4;

                Prove_Value *first = (Prove_Value *)prove_list_get(arr, 0);
                if (prove_value_as_number(first) != 1) return 5;
                Prove_Value *third = (Prove_Value *)prove_list_get(arr, 2);
                if (prove_value_as_number(third) != 3) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="toml_array")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestTomlRoundTrip:
    def test_emit_and_reparse(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "name = \\"test\\"\\ncount = 42\\n");
                Prove_Result r1 = prove_parse_toml(src);
                if (prove_result_is_err(r1)) return 1;
                Prove_Table *t1 = (Prove_Table *)prove_result_unwrap_ptr(r1);

                /* Emit (prove_emit_toml takes Prove_Value*) */
                Prove_String *emitted = prove_emit_toml(prove_value_object(t1));

                /* Re-parse */
                Prove_Result r2 = prove_parse_toml(emitted);
                if (prove_result_is_err(r2)) return 2;
                Prove_Table *t = (Prove_Table *)prove_result_unwrap_ptr(r2);
                Prove_String *nk = prove_string_from_cstr("name");
                Prove_Option opt = prove_table_get(nk, t);
                if (prove_option_is_none(opt)) return 3;
                Prove_String *expected = prove_string_from_cstr("test");
                Prove_Value *nv = (Prove_Value *)opt.value;
                if (!prove_string_eq(prove_value_as_text(nv), expected)) return 4;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="toml_round")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── JSON tests ────────────────────────────────────────────────────


class TestJsonParse:
    def test_object(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "{\\"name\\":\\"test\\",\\"count\\":42}");
                Prove_Result r = prove_parse_json(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                if (!prove_value_is_object(root)) return 2;

                Prove_Table *t = prove_value_as_object(root);
                Prove_String *nk = prove_string_from_cstr("name");
                Prove_Option opt = prove_table_get(nk, t);
                if (prove_option_is_none(opt)) return 3;
                Prove_String *expected = prove_string_from_cstr("test");
                Prove_Value *nv = (Prove_Value *)opt.value;
                if (!prove_string_eq(prove_value_as_text(nv), expected))
                    return 4;

                Prove_String *ck = prove_string_from_cstr("count");
                Prove_Option copt = prove_table_get(ck, t);
                if (prove_option_is_none(copt)) return 5;
                if (prove_value_as_number((Prove_Value *)copt.value) != 42) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="json_obj")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_array(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("[1, 2, 3]");
                Prove_Result r = prove_parse_json(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                if (!prove_value_is_array(root)) return 2;
                Prove_List *arr = prove_value_as_array(root);
                if (prove_list_len(arr) != 3) return 3;
                Prove_Value *second = (Prove_Value *)prove_list_get(arr, 1);
                if (prove_value_as_number(second) != 2) return 4;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="json_arr")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_primitives(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                /* true */
                Prove_String *s1 = prove_string_from_cstr("true");
                Prove_Result r1 = prove_parse_json(s1);
                if (prove_result_is_err(r1)) return 1;
                Prove_Value *v1 = (Prove_Value *)prove_result_unwrap_ptr(r1);
                if (!prove_value_is_bool(v1) || !prove_value_as_bool(v1)) return 2;

                /* null */
                Prove_String *s2 = prove_string_from_cstr("null");
                Prove_Result r2 = prove_parse_json(s2);
                if (prove_result_is_err(r2)) return 3;
                Prove_Value *v2 = (Prove_Value *)prove_result_unwrap_ptr(r2);
                if (!prove_value_is_null(v2)) return 4;

                /* string */
                Prove_String *s3 = prove_string_from_cstr("\\"hello\\"");
                Prove_Result r3 = prove_parse_json(s3);
                if (prove_result_is_err(r3)) return 5;
                Prove_Value *v3 = (Prove_Value *)prove_result_unwrap_ptr(r3);
                if (!prove_value_is_text(v3)) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="json_prims")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_malformed_returns_error(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("{invalid json}");
                Prove_Result r = prove_parse_json(src);
                if (prove_result_is_ok(r)) return 1;  /* Should fail */
                printf("ERR_OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="json_err")
        assert result.returncode == 0
        assert "ERR_OK" in result.stdout


class TestJsonRoundTrip:
    def test_emit_and_reparse(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "{\\"a\\":1,\\"b\\":\\"hello\\",\\"c\\":true}");
                Prove_Result r1 = prove_parse_json(src);
                if (prove_result_is_err(r1)) return 1;
                Prove_Value *v1 = (Prove_Value *)prove_result_unwrap_ptr(r1);

                /* Emit */
                Prove_String *emitted = prove_emit_json(v1);

                /* Re-parse */
                Prove_Result r2 = prove_parse_json(emitted);
                if (prove_result_is_err(r2)) return 2;
                Prove_Value *v2 = (Prove_Value *)prove_result_unwrap_ptr(r2);

                /* Check value preserved */
                Prove_Table *t = prove_value_as_object(v2);
                Prove_String *ak = prove_string_from_cstr("a");
                Prove_Option opt = prove_table_get(ak, t);
                if (prove_option_is_none(opt)) return 3;
                if (prove_value_as_number((Prove_Value *)opt.value) != 1) return 4;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="json_round")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestJsonNullString:
    def test_emit_json_null_text(self, tmp_path, runtime_dir):
        """JSON emitter should handle NULL text pointer without crashing."""
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                /* Create a Value with NULL text — simulates uninitialized field */
                Prove_Value *v = prove_value_text(NULL);
                Prove_String *out = prove_emit_json(v);
                /* Should emit "null" for NULL text */
                if (!prove_string_eq(out, prove_string_from_cstr("null"))) return 1;

                /* Object with a NULL-text field */
                Prove_Table *tbl = prove_table_new();
                tbl = prove_table_add(
                    prove_string_from_cstr("name"), prove_value_text(NULL), tbl);
                tbl = prove_table_add(
                    prove_string_from_cstr("id"), prove_value_number(42), tbl);
                Prove_Value *obj = prove_value_object(tbl);
                Prove_String *out2 = prove_emit_json(obj);
                /* Should not crash */
                if (!out2 || out2->length == 0) return 2;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="json_null_text")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestValueTag:
    def test_tag_names(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Value *vt = prove_value_text(prove_string_from_cstr("x"));
                Prove_Value *vn = prove_value_number(42);
                Prove_Value *vb = prove_value_bool(true);
                Prove_Value *va = prove_value_array(prove_list_new(4));
                Prove_Value *vo = prove_value_object(prove_table_new());
                Prove_Value *vl = prove_value_null();

                Prove_String *s;
                s = prove_string_from_cstr("text");
                if (!prove_string_eq(prove_value_tag(vt), s)) return 1;
                s = prove_string_from_cstr("number");
                if (!prove_string_eq(prove_value_tag(vn), s)) return 2;
                s = prove_string_from_cstr("bool");
                if (!prove_string_eq(prove_value_tag(vb), s)) return 3;
                s = prove_string_from_cstr("array");
                if (!prove_string_eq(prove_value_tag(va), s)) return 4;
                s = prove_string_from_cstr("object");
                if (!prove_string_eq(prove_value_tag(vo), s)) return 5;
                s = prove_string_from_cstr("null");
                if (!prove_string_eq(prove_value_tag(vl), s)) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="value_tags")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestValidatesJson:
    """Tests for prove_validates_json."""

    def test_valid_json_object(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("{\\"key\\": 42}");
                if (!prove_validates_json(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_json_ok")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_invalid_json(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("{bad json");
                if (prove_validates_json(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_json_bad")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_valid_json_array(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("[1, 2, 3]");
                if (!prove_validates_json(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_json_arr")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_empty_string_invalid(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("");
                if (prove_validates_json(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_json_empty")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestValidatesToml:
    """Tests for prove_validates_toml."""

    def test_valid_toml(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("name = \\"hello\\"\\n");
                if (!prove_validates_toml(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_toml_ok")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_invalid_toml(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("= no key");
                if (prove_validates_toml(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_toml_bad")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_valid_toml_with_section(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "[server]\\nport = 8080\\n"
                );
                if (!prove_validates_toml(src)) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="validates_toml_sec")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── URL host/port accessor tests ──────────────────────────────


class TestUrlHostReads:
    def test_host_from_parsed_url(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Url *u = prove_parse_url(
                    prove_string_from_cstr("https://example.com:8080/path")
                );
                Prove_String *h = prove_parse_url_host_reads(u);
                printf("host=%.*s\\n", (int)h->length, h->data);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="url_host")
        assert result.returncode == 0
        assert "host=example.com" in result.stdout

    def test_host_no_port(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Url *u = prove_parse_url(
                    prove_string_from_cstr("https://example.com/path")
                );
                Prove_String *h = prove_parse_url_host_reads(u);
                printf("host=%.*s\\n", (int)h->length, h->data);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="url_host_noport")
        assert result.returncode == 0
        assert "host=example.com" in result.stdout


class TestUrlPortReads:
    def test_port_from_parsed_url(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Url *u = prove_parse_url(
                    prove_string_from_cstr("https://example.com:9090/path")
                );
                int64_t p = prove_parse_url_port_reads(u);
                printf("port=%lld\\n", (long long)p);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="url_port")
        assert result.returncode == 0
        assert "port=9090" in result.stdout

    def test_port_not_set(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Url *u = prove_parse_url(
                    prove_string_from_cstr("https://example.com/path")
                );
                int64_t p = prove_parse_url_port_reads(u);
                printf("port=%lld\\n", (long long)p);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="url_port_unset")
        assert result.returncode == 0
        assert "port=-1" in result.stdout
