"""Tests for the Pattern C runtime module."""

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


class TestPatternMatch:
    def test_match_full(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("hello");
                Prove_String *p = prove_string_from_cstr("[a-z]+");
                printf("%s\\n", prove_pattern_match(t, p) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="match_full")
        assert result.returncode == 0
        assert result.stdout.strip() == "yes"

    def test_match_partial_fails(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("hello123");
                Prove_String *p = prove_string_from_cstr("[a-z]+");
                printf("%s\\n", prove_pattern_match(t, p) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="match_partial")
        assert result.returncode == 0
        assert result.stdout.strip() == "no"

    def test_match_no_match(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("12345");
                Prove_String *p = prove_string_from_cstr("[a-z]+");
                printf("%s\\n", prove_pattern_match(t, p) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="match_no")
        assert result.returncode == 0
        assert result.stdout.strip() == "no"


class TestPatternSearch:
    def test_search_found(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("hello 123 world");
                Prove_String *p = prove_string_from_cstr("[0-9]+");
                Prove_Option_Prove_Matchptr opt = prove_pattern_search(t, p);
                if (Prove_Option_Prove_Matchptr_is_some(opt)) {
                    Prove_Match *m = opt.value;
                    printf("found %.*s at %lld-%lld\\n",
                           (int)m->text->length, m->text->data,
                           (long long)m->start, (long long)m->end);
                } else {
                    printf("not found\\n");
                }
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="search")
        assert result.returncode == 0
        assert result.stdout.strip() == "found 123 at 6-9"

    def test_search_not_found(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("hello world");
                Prove_String *p = prove_string_from_cstr("[0-9]+");
                Prove_Option_Prove_Matchptr opt = prove_pattern_search(t, p);
                printf("%s\\n", Prove_Option_Prove_Matchptr_is_none(opt) ? "none" : "some");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="search_no")
        assert result.returncode == 0
        assert result.stdout.strip() == "none"


class TestPatternFindAll:
    def test_find_all(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("a1 b2 c3");
                Prove_String *p = prove_string_from_cstr("[0-9]+");
                Prove_List *matches = prove_pattern_find_all(t, p);
                printf("count=%lld\\n", (long long)matches->length);
                for (int64_t i = 0; i < matches->length; i++) {
                    Prove_Match *m = *(Prove_Match **)prove_list_get(matches, i);
                    printf("%.*s ", (int)m->text->length, m->text->data);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="find_all")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "count=3"
        assert lines[1].strip() == "1 2 3"


class TestPatternReplace:
    def test_replace(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("hello world");
                Prove_String *p = prove_string_from_cstr("world");
                Prove_String *r = prove_string_from_cstr("prove");
                Prove_String *result = prove_pattern_replace(t, p, r);
                printf("%.*s\\n", (int)result->length, result->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="replace")
        assert result.returncode == 0
        assert result.stdout.strip() == "hello prove"

    def test_replace_multiple(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("a1b2c3");
                Prove_String *p = prove_string_from_cstr("[0-9]");
                Prove_String *r = prove_string_from_cstr("X");
                Prove_String *result = prove_pattern_replace(t, p, r);
                printf("%.*s\\n", (int)result->length, result->data);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="replace_multi")
        assert result.returncode == 0
        assert result.stdout.strip() == "aXbXcX"


class TestPatternSplit:
    def test_split(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("one,two,,three");
                Prove_String *p = prove_string_from_cstr(",+");
                Prove_List *parts = prove_pattern_split(t, p);
                printf("count=%lld\\n", (long long)parts->length);
                for (int64_t i = 0; i < parts->length; i++) {
                    Prove_String *s = *(Prove_String **)prove_list_get(parts, i);
                    printf("[%.*s]", (int)s->length, s->data);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="split")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "count=3"
        assert lines[1] == "[one][two][three]"


class TestPatternMatchAccessors:
    def test_accessors(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_pattern.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *t = prove_string_from_cstr("hello 42 world");
                Prove_String *p = prove_string_from_cstr("[0-9]+");
                Prove_Option_Prove_Matchptr opt = prove_pattern_search(t, p);
                if (Prove_Option_Prove_Matchptr_is_some(opt)) {
                    Prove_Match *m = opt.value;
                    Prove_String *txt = prove_pattern_text(m);
                    printf("text=%.*s start=%lld end=%lld\\n",
                           (int)txt->length, txt->data,
                           (long long)prove_pattern_start(m),
                           (long long)prove_pattern_end(m));
                }
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="accessors")
        assert result.returncode == 0
        assert result.stdout.strip() == "text=42 start=6 end=8"
