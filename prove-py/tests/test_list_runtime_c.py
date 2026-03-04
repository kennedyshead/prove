"""Tests for the List C runtime module (prove_list_ops)."""

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


class TestListLength:
    def test_length_nonempty(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                printf("%lld\\n", (long long)prove_list_ops_length(l));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="len")
        assert result.returncode == 0
        assert result.stdout.strip() == "3"

    def test_length_empty(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                printf("%lld\\n", (long long)prove_list_ops_length(l));
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="len_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestListFirstLast:
    def test_first_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                Prove_Option_int64_t opt = prove_list_ops_first_int(l);
                printf("%s %lld\\n", Prove_Option_int64_t_is_some(opt) ? "some" : "none",
                       (long long)opt.value);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="first")
        assert result.returncode == 0
        assert result.stdout.strip() == "some 10"

    def test_first_empty(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                Prove_Option_int64_t opt = prove_list_ops_first_int(l);
                printf("%s\\n", Prove_Option_int64_t_is_none(opt) ? "none" : "some");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="first_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "none"

    def test_last_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                Prove_Option_int64_t opt = prove_list_ops_last_int(l);
                printf("%s %lld\\n", Prove_Option_int64_t_is_some(opt) ? "some" : "none",
                       (long long)opt.value);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="last")
        assert result.returncode == 0
        assert result.stdout.strip() == "some 30"


class TestListContains:
    def test_contains_hit(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                printf("%s\\n", prove_list_ops_contains_int(l, 20) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="contains_hit")
        assert result.returncode == 0
        assert result.stdout.strip() == "yes"

    def test_contains_miss(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                printf("%s\\n", prove_list_ops_contains_int(l, 99) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="contains_miss")
        assert result.returncode == 0
        assert result.stdout.strip() == "no"

    def test_contains_str(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(Prove_String *), 4);
                Prove_String *a = prove_string_from_cstr("hello");
                Prove_String *b = prove_string_from_cstr("world");
                prove_list_push(&l, &a);
                prove_list_push(&l, &b);
                Prove_String *needle = prove_string_from_cstr("hello");
                printf("%s\\n", prove_list_ops_contains_str(l, needle) ? "yes" : "no");
                Prove_String *missing = prove_string_from_cstr("foo");
                printf("%s\\n", prove_list_ops_contains_str(l, missing) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="contains_str")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "yes"
        assert lines[1] == "no"


class TestListIndex:
    def test_index_found(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                Prove_Option_int64_t opt = prove_list_ops_index_int(l, 20);
                if (Prove_Option_int64_t_is_some(opt)) {
                    printf("%lld\\n", (long long)opt.value);
                } else {
                    printf("none\\n");
                }
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="index_found")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_index_not_found(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {10, 20, 30};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                Prove_Option_int64_t opt = prove_list_ops_index_int(l, 99);
                printf("%s\\n", Prove_Option_int64_t_is_none(opt) ? "none" : "some");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="index_miss")
        assert result.returncode == 0
        assert result.stdout.strip() == "none"


class TestListSort:
    def test_sort_int(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {30, 10, 20};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                Prove_List *sorted = prove_list_ops_sort_int(l);
                for (int64_t i = 0; i < sorted->length; i++) {
                    printf("%lld ", (long long)*(int64_t *)prove_list_get(sorted, i));
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="sort_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "10 20 30"

    def test_sort_str(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(Prove_String *), 4);
                Prove_String *c = prove_string_from_cstr("cherry");
                Prove_String *a = prove_string_from_cstr("apple");
                Prove_String *b = prove_string_from_cstr("banana");
                prove_list_push(&l, &c);
                prove_list_push(&l, &a);
                prove_list_push(&l, &b);
                Prove_List *sorted = prove_list_ops_sort_str(l);
                for (int64_t i = 0; i < sorted->length; i++) {
                    Prove_String *s = *(Prove_String **)prove_list_get(sorted, i);
                    printf("%.*s ", (int)s->length, s->data);
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="sort_str")
        assert result.returncode == 0
        assert result.stdout.strip() == "apple banana cherry"


class TestListReverse:
    def test_reverse(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t vals[] = {1, 2, 3};
                for (int i = 0; i < 3; i++) prove_list_push(&l, &vals[i]);
                Prove_List *rev = prove_list_ops_reverse(l);
                for (int64_t i = 0; i < rev->length; i++) {
                    printf("%lld ", (long long)*(int64_t *)prove_list_get(rev, i));
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="reverse")
        assert result.returncode == 0
        assert result.stdout.strip() == "3 2 1"


class TestListSlice:
    def test_slice(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 8);
                for (int64_t i = 0; i < 5; i++) prove_list_push(&l, &i);
                Prove_List *s = prove_list_ops_slice(l, 1, 4);
                printf("len=%lld:", (long long)s->length);
                for (int64_t i = 0; i < s->length; i++) {
                    printf(" %lld", (long long)*(int64_t *)prove_list_get(s, i));
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="slice")
        assert result.returncode == 0
        assert result.stdout.strip() == "len=3: 1 2 3"


class TestListRange:
    def test_range(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_ops_range(1, 6);
                for (int64_t i = 0; i < l->length; i++) {
                    printf("%lld ", (long long)*(int64_t *)prove_list_get(l, i));
                }
                printf("\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="range")
        assert result.returncode == 0
        assert result.stdout.strip() == "1 2 3 4 5"

    def test_range_empty(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_ops_range(5, 3);
                printf("%lld\\n", (long long)l->length);
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="range_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestListEmpty:
    def test_empty_true(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                printf("%s\\n", prove_list_ops_empty(l) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="empty_true")
        assert result.returncode == 0
        assert result.stdout.strip() == "yes"

    def test_empty_false(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_list_ops.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *l = prove_list_new(sizeof(int64_t), 4);
                int64_t v = 42;
                prove_list_push(&l, &v);
                printf("%s\\n", prove_list_ops_empty(l) ? "yes" : "no");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="empty_false")
        assert result.returncode == 0
        assert result.stdout.strip() == "no"
