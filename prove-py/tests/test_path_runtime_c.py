"""Tests for the Path C runtime module."""

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


class TestPathJoin:
    def test_join_basic(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *b = prove_string_from_cstr("/home/user");
                Prove_String *p = prove_string_from_cstr("file.txt");
                Prove_String *r = prove_path_join(b, p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="join")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user/file.txt"

    def test_join_trailing_slash(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *b = prove_string_from_cstr("/home/user/");
                Prove_String *p = prove_string_from_cstr("file.txt");
                Prove_String *r = prove_path_join(b, p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="join_slash")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user/file.txt"

    def test_join_absolute_part(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *b = prove_string_from_cstr("/home/user");
                Prove_String *p = prove_string_from_cstr("/etc/config");
                Prove_String *r = prove_path_join(b, p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="join_abs")
        assert result.returncode == 0
        assert result.stdout.strip() == "/etc/config"


class TestPathParent:
    def test_parent_nested(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_parent(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="parent")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user"

    def test_parent_root(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/file.txt");
                Prove_String *r = prove_path_parent(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="parent_root")
        assert result.returncode == 0
        assert result.stdout.strip() == "/"

    def test_parent_no_sep(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("file.txt");
                Prove_String *r = prove_path_parent(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="parent_nosep")
        assert result.returncode == 0
        assert result.stdout.strip() == "."


class TestPathComponents:
    def test_name(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_name(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="name")
        assert result.returncode == 0
        assert result.stdout.strip() == "file.txt"

    def test_stem(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_stem(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="stem")
        assert result.returncode == 0
        assert result.stdout.strip() == "file"

    def test_extension(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_extension(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="ext")
        assert result.returncode == 0
        assert result.stdout.strip() == ".txt"

    def test_extension_none(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/Makefile");
                Prove_String *r = prove_path_extension(p);
                printf("[%.*s]\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="ext_none")
        assert result.returncode == 0
        assert result.stdout.strip() == "[]"


class TestPathAbsolute:
    def test_absolute_true(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user");
                printf("%s\\n", prove_path_absolute(p) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="abs_true")
        assert result.returncode == 0
        assert result.stdout.strip() == "yes"

    def test_absolute_false(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("relative/path");
                printf("%s\\n", prove_path_absolute(p) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="abs_false")
        assert result.returncode == 0
        assert result.stdout.strip() == "no"


class TestPathNormalize:
    def test_normalize_dots(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/../admin/./config");
                Prove_String *r = prove_path_normalize(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="norm")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/admin/config"

    def test_normalize_clean(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user");
                Prove_String *r = prove_path_normalize(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="norm_clean")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user"
