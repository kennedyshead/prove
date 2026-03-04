"""Tests for the Convert C runtime module."""

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
    global _RUNTIME_DIR
    copy_runtime(tmp_path)
    _RUNTIME_DIR = tmp_path / "runtime"


def _compile_and_run(
    tmp_path: Path, c_code: str, *, name: str = "test",
) -> subprocess.CompletedProcess:
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
        "-lm",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"Compile failed:\n{result.stderr}"

    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)


class TestConvertInteger:
    def test_integer_from_string_ok(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("42");
                Prove_Result r = prove_convert_integer_str(s);
                if (prove_result_is_ok(r)) {
                    printf("%lld\\n", (long long)r.ok_int);
                } else {
                    printf("ERR\\n");
                }
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="int_ok")
        assert result.returncode == 0
        assert result.stdout.strip() == "42"

    def test_integer_from_string_negative(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("-100");
                Prove_Result r = prove_convert_integer_str(s);
                if (prove_result_is_ok(r)) {
                    printf("%lld\\n", (long long)r.ok_int);
                }
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="int_neg")
        assert result.returncode == 0
        assert result.stdout.strip() == "-100"

    def test_integer_from_string_invalid(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("abc");
                Prove_Result r = prove_convert_integer_str(s);
                printf("%s\\n", prove_result_is_err(r) ? "ERR" : "OK");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="int_err")
        assert result.returncode == 0
        assert result.stdout.strip() == "ERR"

    def test_integer_from_float(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_convert_integer_float(3.7));
                printf("%lld\\n", (long long)prove_convert_integer_float(-2.9));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="int_float")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "3"
        assert lines[1] == "-2"


class TestConvertFloat:
    def test_float_from_string_ok(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("3.14");
                Prove_Result r = prove_convert_float_str(s);
                if (prove_result_is_ok(r)) {
                    printf("%.2f\\n", r.ok_double);
                }
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="float_ok")
        assert result.returncode == 0
        assert result.stdout.strip() == "3.14"

    def test_float_from_string_invalid(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("not_a_number");
                Prove_Result r = prove_convert_float_str(s);
                printf("%s\\n", prove_result_is_err(r) ? "ERR" : "OK");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="float_err")
        assert result.returncode == 0
        assert result.stdout.strip() == "ERR"

    def test_float_from_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                printf("%.1f\\n", prove_convert_float_int(42));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="float_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "42.0"


class TestConvertString:
    def test_string_from_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_convert_string_int(42);
                printf("%.*s\\n", (int)s->length, s->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="str_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "42"

    def test_string_from_bool(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_convert_string_bool(true);
                Prove_String *f = prove_convert_string_bool(false);
                printf("%.*s\\n", (int)t->length, t->data);
                printf("%.*s\\n", (int)f->length, f->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="str_bool")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "true"
        assert lines[1] == "false"


class TestConvertCharacter:
    def test_code(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_convert_code('A'));
                printf("%lld\\n", (long long)prove_convert_code('0'));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="code")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "65"
        assert lines[1] == "48"

    def test_character(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_convert.h"
            #include <stdio.h>
            int main(void) {
                printf("%c\\n", prove_convert_character(65));
                printf("%c\\n", prove_convert_character(48));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="char")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "A"
        assert lines[1] == "0"
