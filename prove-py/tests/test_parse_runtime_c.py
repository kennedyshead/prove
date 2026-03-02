"""Tests for the Parse C runtime (TOML/JSON codecs).

Each test compiles a standalone C program that exercises the parser and
checks results via exit codes and stdout.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from prove.c_compiler import find_c_compiler
from prove.c_runtime import copy_runtime

_RUNTIME_DIR: Path | None = None


@pytest.fixture(autouse=True)
def _setup_runtime(tmp_path, needs_cc):
    """Copy runtime files to tmp_path so tests can include them."""
    global _RUNTIME_DIR
    copy_runtime(tmp_path)
    _RUNTIME_DIR = tmp_path / "runtime"


def _compile_and_run(
    tmp_path: Path, c_code: str, *, name: str = "test",
) -> subprocess.CompletedProcess:
    """Compile a C test program and run it."""
    assert _RUNTIME_DIR is not None
    src = tmp_path / f"{name}.c"
    src.write_text(c_code)
    binary = tmp_path / name
    cc = find_c_compiler()
    assert cc is not None

    runtime_c = sorted(_RUNTIME_DIR.glob("*.c"))
    cmd = [
        cc, "-O0", "-Wall", "-Wextra", "-Wno-unused-parameter",
        "-I", str(_RUNTIME_DIR),
        str(src), *[str(f) for f in runtime_c],
        "-o", str(binary),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"Compile failed:\n{result.stderr}"

    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)


# ── TOML tests ────────────────────────────────────────────────────


class TestTomlParse:
    def test_key_value_string(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("name = \\"hello\\"\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                if (!prove_value_is_object(root)) return 2;
                Prove_Table *t = prove_value_as_object(root);
                Prove_String *key = prove_string_from_cstr("name");
                Prove_Option_voidptr opt = prove_table_get(key, t);
                if (Prove_Option_voidptr_is_none(opt)) return 3;
                Prove_Value *val = (Prove_Value *)opt.value;
                if (!prove_value_is_text(val)) return 4;
                Prove_String *expected = prove_string_from_cstr("hello");
                if (!prove_string_eq(prove_value_as_text(val), expected)) return 5;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="toml_kv")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_key_value_integer(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("port = 8080\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                Prove_Table *t = prove_value_as_object(root);
                Prove_String *key = prove_string_from_cstr("port");
                Prove_Option_voidptr opt = prove_table_get(key, t);
                if (Prove_Option_voidptr_is_none(opt)) return 2;
                Prove_Value *val = (Prove_Value *)opt.value;
                if (!prove_value_is_number(val)) return 3;
                if (prove_value_as_number(val) != 8080) return 4;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="toml_int")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_key_value_bool(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("debug = true\\nverbose = false\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                Prove_Table *t = prove_value_as_object(root);

                Prove_String *k1 = prove_string_from_cstr("debug");
                Prove_Option_voidptr o1 = prove_table_get(k1, t);
                if (Prove_Option_voidptr_is_none(o1)) return 2;
                Prove_Value *v1 = (Prove_Value *)o1.value;
                if (!prove_value_as_bool(v1)) return 3;

                Prove_String *k2 = prove_string_from_cstr("verbose");
                Prove_Option_voidptr o2 = prove_table_get(k2, t);
                if (Prove_Option_voidptr_is_none(o2)) return 4;
                Prove_Value *v2 = (Prove_Value *)o2.value;
                if (prove_value_as_bool(v2)) return 5;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="toml_bool")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_section(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "[package]\\nname = \\"myapp\\"\\nversion = \\"1.0\\"\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                Prove_Table *t = prove_value_as_object(root);

                Prove_String *pkg_key = prove_string_from_cstr("package");
                Prove_Option_voidptr opt = prove_table_get(pkg_key, t);
                if (Prove_Option_voidptr_is_none(opt)) return 2;
                Prove_Value *pkg = (Prove_Value *)opt.value;
                if (!prove_value_is_object(pkg)) return 3;

                Prove_Table *pkg_tbl = prove_value_as_object(pkg);
                Prove_String *name_key = prove_string_from_cstr("name");
                Prove_Option_voidptr nopt = prove_table_get(name_key, pkg_tbl);
                if (Prove_Option_voidptr_is_none(nopt)) return 4;
                Prove_Value *name_val = (Prove_Value *)nopt.value;
                Prove_String *expected = prove_string_from_cstr("myapp");
                if (!prove_string_eq(prove_value_as_text(name_val), expected)) return 5;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="toml_section")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_array(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr("nums = [1, 2, 3]\\n");
                Prove_Result r = prove_parse_toml(src);
                if (prove_result_is_err(r)) return 1;
                Prove_Value *root = (Prove_Value *)prove_result_unwrap_ptr(r);
                Prove_Table *t = prove_value_as_object(root);

                Prove_String *key = prove_string_from_cstr("nums");
                Prove_Option_voidptr opt = prove_table_get(key, t);
                if (Prove_Option_voidptr_is_none(opt)) return 2;
                Prove_Value *val = (Prove_Value *)opt.value;
                if (!prove_value_is_array(val)) return 3;

                Prove_List *arr = prove_value_as_array(val);
                if (prove_list_len(arr) != 3) return 4;

                Prove_Value *first = *(Prove_Value **)prove_list_get(arr, 0);
                if (prove_value_as_number(first) != 1) return 5;
                Prove_Value *third = *(Prove_Value **)prove_list_get(arr, 2);
                if (prove_value_as_number(third) != 3) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="toml_array")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestTomlRoundTrip:
    def test_emit_and_reparse(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *src = prove_string_from_cstr(
                    "name = \\"test\\"\\ncount = 42\\n");
                Prove_Result r1 = prove_parse_toml(src);
                if (prove_result_is_err(r1)) return 1;
                Prove_Value *v1 = (Prove_Value *)prove_result_unwrap_ptr(r1);

                /* Emit */
                Prove_String *emitted = prove_emit_toml(v1);

                /* Re-parse */
                Prove_Result r2 = prove_parse_toml(emitted);
                if (prove_result_is_err(r2)) return 2;
                Prove_Value *v2 = (Prove_Value *)prove_result_unwrap_ptr(r2);

                /* Check values preserved */
                Prove_Table *t = prove_value_as_object(v2);
                Prove_String *nk = prove_string_from_cstr("name");
                Prove_Option_voidptr opt = prove_table_get(nk, t);
                if (Prove_Option_voidptr_is_none(opt)) return 3;
                Prove_String *expected = prove_string_from_cstr("test");
                Prove_Value *nv = (Prove_Value *)opt.value;
                if (!prove_string_eq(prove_value_as_text(nv), expected)) return 4;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="toml_round")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── JSON tests ────────────────────────────────────────────────────


class TestJsonParse:
    def test_object(self, tmp_path):
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
                Prove_Option_voidptr opt = prove_table_get(nk, t);
                if (Prove_Option_voidptr_is_none(opt)) return 3;
                Prove_String *expected = prove_string_from_cstr("test");
                Prove_Value *nv = (Prove_Value *)opt.value;
                if (!prove_string_eq(prove_value_as_text(nv), expected))
                    return 4;

                Prove_String *ck = prove_string_from_cstr("count");
                Prove_Option_voidptr copt = prove_table_get(ck, t);
                if (Prove_Option_voidptr_is_none(copt)) return 5;
                if (prove_value_as_number((Prove_Value *)copt.value) != 42) return 6;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="json_obj")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_array(self, tmp_path):
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
                Prove_Value *second = *(Prove_Value **)prove_list_get(arr, 1);
                if (prove_value_as_number(second) != 2) return 4;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="json_arr")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_primitives(self, tmp_path):
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
        result = _compile_and_run(tmp_path, code, name="json_prims")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_malformed_returns_error(self, tmp_path):
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
        result = _compile_and_run(tmp_path, code, name="json_err")
        assert result.returncode == 0
        assert "ERR_OK" in result.stdout


class TestJsonRoundTrip:
    def test_emit_and_reparse(self, tmp_path):
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
                Prove_Option_voidptr opt = prove_table_get(ak, t);
                if (Prove_Option_voidptr_is_none(opt)) return 3;
                if (prove_value_as_number((Prove_Value *)opt.value) != 1) return 4;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="json_round")
        assert result.returncode == 0
        assert "OK" in result.stdout


class TestValueTag:
    def test_tag_names(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_parse.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Value *vt = prove_value_text(prove_string_from_cstr("x"));
                Prove_Value *vn = prove_value_number(42);
                Prove_Value *vb = prove_value_bool(true);
                Prove_Value *va = prove_value_array(prove_list_new(sizeof(Prove_Value*), 4));
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
        result = _compile_and_run(tmp_path, code, name="value_tags")
        assert result.returncode == 0
        assert "OK" in result.stdout
