"""Tests for the Math C runtime module."""

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


class TestMathAbs:
    def test_abs_positive_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_abs_int(42));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="abs_pos")
        assert result.returncode == 0
        assert result.stdout.strip() == "42"

    def test_abs_negative_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_abs_int(-42));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="abs_neg")
        assert result.returncode == 0
        assert result.stdout.strip() == "42"

    def test_abs_zero(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_abs_int(0));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="abs_zero")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_abs_float(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%.1f\\n", prove_math_abs_float(-3.5));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="abs_float")
        assert result.returncode == 0
        assert result.stdout.strip() == "3.5"


class TestMathMinMax:
    def test_min_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_min_int(3, 7));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="min_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "3"

    def test_min_equal(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_min_int(5, 5));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="min_eq")
        assert result.returncode == 0
        assert result.stdout.strip() == "5"

    def test_max_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_max_int(3, 7));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="max_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "7"

    def test_min_float(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%.1f\\n", prove_math_min_float(2.5, 1.5));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="min_float")
        assert result.returncode == 0
        assert result.stdout.strip() == "1.5"

    def test_max_float(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%.1f\\n", prove_math_max_float(2.5, 1.5));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="max_float")
        assert result.returncode == 0
        assert result.stdout.strip() == "2.5"


class TestMathClamp:
    def test_clamp_below(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_clamp_int(-5, 0, 10));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="clamp_below")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_clamp_above(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_clamp_int(15, 0, 10));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="clamp_above")
        assert result.returncode == 0
        assert result.stdout.strip() == "10"

    def test_clamp_within(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_clamp_int(5, 0, 10));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="clamp_in")
        assert result.returncode == 0
        assert result.stdout.strip() == "5"


class TestMathFloat:
    def test_sqrt(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%.1f\\n", prove_math_sqrt(16.0));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="sqrt")
        assert result.returncode == 0
        assert result.stdout.strip() == "4.0"

    def test_pow(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%.1f\\n", prove_math_pow(2.0, 10.0));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="pow")
        assert result.returncode == 0
        assert result.stdout.strip() == "1024.0"

    def test_floor(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_floor(3.7));
                printf("%lld\\n", (long long)prove_math_floor(-1.2));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="floor")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "3"
        assert lines[1] == "-2"

    def test_ceil(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_ceil(3.2));
                printf("%lld\\n", (long long)prove_math_ceil(-1.7));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="ceil")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "4"
        assert lines[1] == "-1"

    def test_round(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            int main(void) {
                printf("%lld\\n", (long long)prove_math_round(3.5));
                printf("%lld\\n", (long long)prove_math_round(3.4));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="round")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "4"
        assert lines[1] == "3"

    def test_log(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_math.h"
            #include <stdio.h>
            #include <math.h>
            int main(void) {
                double val = prove_math_log(M_E);
                printf("%.1f\\n", val);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="log")
        assert result.returncode == 0
        assert result.stdout.strip() == "1.0"
