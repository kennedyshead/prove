"""Tests for the Format C runtime module."""

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


class TestFormatPad:
    def test_pad_left(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hi");
                Prove_String *r = prove_format_pad_left(s, 6, '*');
                printf("[%.*s]\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="pad_left")
        assert result.returncode == 0
        assert result.stdout.strip() == "[****hi]"

    def test_pad_right(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hi");
                Prove_String *r = prove_format_pad_right(s, 6, '.');
                printf("[%.*s]\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="pad_right")
        assert result.returncode == 0
        assert result.stdout.strip() == "[hi....]"

    def test_pad_no_change(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                Prove_String *r = prove_format_pad_left(s, 3, ' ');
                printf("[%.*s]\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="pad_noop")
        assert result.returncode == 0
        assert result.stdout.strip() == "[hello]"

    def test_center(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hi");
                Prove_String *r = prove_format_center(s, 8, '-');
                printf("[%.*s]\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="center")
        assert result.returncode == 0
        assert result.stdout.strip() == "[---hi---]"


class TestFormatNumber:
    def test_hex(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *r = prove_format_hex(255);
                printf("%.*s\\n", (int)r->length, r->data);
                Prove_String *z = prove_format_hex(0);
                printf("%.*s\\n", (int)z->length, z->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="hex")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "ff"
        assert lines[1] == "0"

    def test_binary(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *r = prove_format_binary(42);
                printf("%.*s\\n", (int)r->length, r->data);
                Prove_String *z = prove_format_binary(0);
                printf("%.*s\\n", (int)z->length, z->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="binary")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "101010"
        assert lines[1] == "0"

    def test_octal(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *r = prove_format_octal(8);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="octal")
        assert result.returncode == 0
        assert result.stdout.strip() == "10"

    def test_decimal(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_format.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *r = prove_format_decimal(3.14159, 2);
                printf("%.*s\\n", (int)r->length, r->data);
                Prove_String *z = prove_format_decimal(1.0, 0);
                printf("%.*s\\n", (int)z->length, z->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="decimal")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "3.14"
        assert lines[1] == "1"
