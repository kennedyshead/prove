"""Tests for the C runtime components (arena, hash, intern).

Each test compiles a standalone C program that exercises the runtime and
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

    # Collect all .c files from runtime
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


# ── Arena tests ───────────────────────────────────────────────────


class TestArena:
    def test_alloc_and_free(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_arena.h"
            #include <stdio.h>

            int main(void) {
                ProveArena *a = prove_arena_new(4096);
                if (!a) return 1;

                void *p1 = prove_arena_alloc(a, 64, 8);
                void *p2 = prove_arena_alloc(a, 128, 8);
                void *p3 = prove_arena_alloc(a, 256, 16);

                if (!p1 || !p2 || !p3) return 2;
                if (p1 == p2 || p2 == p3 || p1 == p3) return 3;

                prove_arena_free(a);
                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="arena_alloc")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_reset_reuse(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_arena.h"
            #include <stdio.h>

            int main(void) {
                ProveArena *a = prove_arena_new(4096);
                if (!a) return 1;

                void *p1 = prove_arena_alloc(a, 64, 8);
                if (!p1) return 2;

                prove_arena_reset(a);

                void *p2 = prove_arena_alloc(a, 64, 8);
                if (!p2) return 3;

                /* After reset, allocation should reuse memory from same offset */
                if (p1 != p2) return 4;

                prove_arena_free(a);
                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="arena_reset")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_overflow_chunk(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_arena.h"
            #include <stdio.h>

            int main(void) {
                /* Small initial chunk to force overflow quickly */
                ProveArena *a = prove_arena_new(128);
                if (!a) return 1;

                /* Allocate more than 128 bytes total */
                void *p1 = prove_arena_alloc(a, 64, 8);
                void *p2 = prove_arena_alloc(a, 64, 8);
                void *p3 = prove_arena_alloc(a, 64, 8);  /* should trigger new chunk */

                if (!p1 || !p2 || !p3) return 2;

                prove_arena_free(a);
                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="arena_overflow")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Hash tests ────────────────────────────────────────────────────


class TestHash:
    def test_deterministic(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_hash.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                const char *s = "hello world";
                size_t len = strlen(s);
                uint32_t h1 = prove_hash(s, len);
                uint32_t h2 = prove_hash(s, len);

                if (h1 != h2) return 1;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="hash_determ")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_different_inputs(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_hash.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                uint32_t h1 = prove_hash("hello", 5);
                uint32_t h2 = prove_hash("world", 5);
                uint32_t h3 = prove_hash("", 0);
                uint32_t h4 = prove_hash("a", 1);

                /* Different inputs should produce different hashes (with high probability) */
                if (h1 == h2) return 1;
                if (h1 == h3) return 2;
                if (h3 == h4) return 3;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="hash_diff")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Intern tests ──────────────────────────────────────────────────


class TestIntern:
    def test_dedup(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_arena.h"
            #include "prove_intern.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                ProveArena *a = prove_arena_new(0);
                ProveInternTable *t = prove_intern_table_new(a);

                const char *s1 = prove_intern(t, "hello", 5);
                const char *s2 = prove_intern(t, "hello", 5);

                /* Same string interned twice must return same pointer */
                if (s1 != s2) return 1;
                if (strcmp(s1, "hello") != 0) return 2;

                prove_intern_table_free(t);
                prove_arena_free(a);
                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="intern_dedup")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_different(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_arena.h"
            #include "prove_intern.h"
            #include <stdio.h>

            int main(void) {
                ProveArena *a = prove_arena_new(0);
                ProveInternTable *t = prove_intern_table_new(a);

                const char *s1 = prove_intern(t, "hello", 5);
                const char *s2 = prove_intern(t, "world", 5);

                /* Different strings must return different pointers */
                if (s1 == s2) return 1;

                prove_intern_table_free(t);
                prove_arena_free(a);
                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="intern_diff")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_growth(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_arena.h"
            #include "prove_intern.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                ProveArena *a = prove_arena_new(0);
                ProveInternTable *t = prove_intern_table_new(a);

                /* Intern more than 256 strings to trigger growth */
                char buf[32];
                const char *ptrs[512];
                for (int i = 0; i < 512; i++) {
                    int len = snprintf(buf, sizeof(buf), "str_%d", i);
                    ptrs[i] = prove_intern(t, buf, (size_t)len);
                    if (!ptrs[i]) return 1;
                }

                /* Verify all are still retrievable and correct */
                for (int i = 0; i < 512; i++) {
                    int len = snprintf(buf, sizeof(buf), "str_%d", i);
                    const char *p = prove_intern(t, buf, (size_t)len);
                    if (p != ptrs[i]) return 2;  /* pointer equality */
                    if (strcmp(p, buf) != 0) return 3;
                }

                prove_intern_table_free(t);
                prove_arena_free(a);
                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="intern_growth")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Character tests ──────────────────────────────────────────────


class TestCharacter:
    def test_classification(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_character.h"
            #include <stdio.h>

            int main(void) {
                if (!prove_character_alpha('A')) return 1;
                if (!prove_character_alpha('z')) return 2;
                if (prove_character_alpha('5')) return 3;

                if (!prove_character_digit('0')) return 4;
                if (!prove_character_digit('9')) return 5;
                if (prove_character_digit('a')) return 6;

                if (!prove_character_alnum('A')) return 7;
                if (!prove_character_alnum('5')) return 8;
                if (prove_character_alnum(' ')) return 9;

                if (!prove_character_upper('A')) return 10;
                if (prove_character_upper('a')) return 11;

                if (!prove_character_lower('a')) return 12;
                if (prove_character_lower('A')) return 13;

                if (!prove_character_space(' ')) return 14;
                if (!prove_character_space('\\t')) return 15;
                if (prove_character_space('x')) return 16;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="char_classify")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_at(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_character.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                if (prove_character_at(s, 0) != 'h') return 1;
                if (prove_character_at(s, 4) != 'o') return 2;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="char_at")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Text tests ───────────────────────────────────────────────────


class TestText:
    def test_length_and_slice(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello world");
                if (prove_text_length(s) != 11) return 1;

                Prove_String *sub = prove_text_slice(s, 0, 5);
                if (!prove_string_eq(sub, prove_string_from_cstr("hello"))) return 2;

                Prove_String *sub2 = prove_text_slice(s, 6, 11);
                if (!prove_string_eq(sub2, prove_string_from_cstr("world"))) return 3;

                /* Edge: empty slice */
                Prove_String *empty = prove_text_slice(s, 5, 5);
                if (prove_text_length(empty) != 0) return 4;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_slice")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_starts_ends_contains(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello world");
                Prove_String *he = prove_string_from_cstr("hello");
                Prove_String *ld = prove_string_from_cstr("world");
                Prove_String *lo = prove_string_from_cstr("lo wo");
                Prove_String *zz = prove_string_from_cstr("xyz");

                if (!prove_text_starts_with(s, he)) return 1;
                if (prove_text_starts_with(s, ld)) return 2;

                if (!prove_text_ends_with(s, ld)) return 3;
                if (prove_text_ends_with(s, he)) return 4;

                if (!prove_text_contains(s, lo)) return 5;
                if (prove_text_contains(s, zz)) return 6;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_prefix")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_index_of(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello world");
                Prove_String *wo = prove_string_from_cstr("world");
                Prove_String *zz = prove_string_from_cstr("xyz");

                Prove_Option_int64_t r1 = prove_text_index_of(s, wo);
                if (!Prove_Option_int64_t_is_some(r1)) return 1;
                if (r1.value != 6) return 2;

                Prove_Option_int64_t r2 = prove_text_index_of(s, zz);
                if (!Prove_Option_int64_t_is_none(r2)) return 3;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_indexof")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_split_join(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("a,b,c");
                Prove_String *sep = prove_string_from_cstr(",");

                Prove_List *parts = prove_text_split(s, sep);
                if (prove_list_len(parts) != 3) return 1;

                Prove_String **p0 = (Prove_String **)prove_list_get(parts, 0);
                if (!prove_string_eq(*p0, prove_string_from_cstr("a"))) return 2;
                Prove_String **p2 = (Prove_String **)prove_list_get(parts, 2);
                if (!prove_string_eq(*p2, prove_string_from_cstr("c"))) return 3;

                /* Join back together */
                Prove_String *joined = prove_text_join(parts, prove_string_from_cstr("-"));
                if (!prove_string_eq(joined, prove_string_from_cstr("a-b-c"))) return 4;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_split")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_trim(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("  hello  ");
                Prove_String *trimmed = prove_text_trim(s);
                if (!prove_string_eq(trimmed, prove_string_from_cstr("hello"))) return 1;

                /* Already trimmed */
                Prove_String *clean = prove_string_from_cstr("hello");
                Prove_String *same = prove_text_trim(clean);
                if (!prove_string_eq(same, clean)) return 2;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_trim")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_case_conversion(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("Hello World");
                Prove_String *lo = prove_text_to_lower(s);
                if (!prove_string_eq(lo, prove_string_from_cstr("hello world"))) return 1;

                Prove_String *up = prove_text_to_upper(s);
                if (!prove_string_eq(up, prove_string_from_cstr("HELLO WORLD"))) return 2;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_case")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_replace(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("aabaa");
                Prove_String *old_s = prove_string_from_cstr("aa");
                Prove_String *new_s = prove_string_from_cstr("X");
                Prove_String *result = prove_text_replace(s, old_s, new_s);
                if (!prove_string_eq(result, prove_string_from_cstr("XbX"))) return 1;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_replace")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_repeat(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("ab");
                Prove_String *r = prove_text_repeat(s, 3);
                if (!prove_string_eq(r, prove_string_from_cstr("ababab"))) return 1;

                Prove_String *z = prove_text_repeat(s, 0);
                if (prove_text_length(z) != 0) return 2;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_repeat")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_builder(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_text.h"
            #include <stdio.h>

            int main(void) {
                Prove_Builder *b = prove_text_builder();
                if (prove_text_builder_length(b) != 0) return 1;

                b = prove_text_write(b, prove_string_from_cstr("hello"));
                b = prove_text_write_char(b, ' ');
                b = prove_text_write(b, prove_string_from_cstr("world"));

                if (prove_text_builder_length(b) != 11) return 2;

                Prove_String *result = prove_text_build(b);
                if (!prove_string_eq(result, prove_string_from_cstr("hello world"))) return 3;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="text_builder")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Table tests ──────────────────────────────────────────────────


class TestTable:
    def test_add_get_has(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_table.h"
            #include <stdio.h>

            int main(void) {
                Prove_Table *t = prove_table_new();
                if (prove_table_length(t) != 0) return 1;

                Prove_String *k1 = prove_string_from_cstr("key1");
                Prove_String *k2 = prove_string_from_cstr("key2");

                t = prove_table_add(k1, (void*)42, t);
                t = prove_table_add(k2, (void*)99, t);

                if (prove_table_length(t) != 2) return 2;
                if (!prove_table_has(k1, t)) return 3;
                if (!prove_table_has(k2, t)) return 4;

                Prove_Option_voidptr r1 = prove_table_get(k1, t);
                if (!Prove_Option_voidptr_is_some(r1)) return 5;
                if ((int64_t)r1.value != 42) return 6;

                Prove_Option_voidptr r2 = prove_table_get(k2, t);
                if ((int64_t)r2.value != 99) return 7;

                /* Missing key */
                Prove_String *k3 = prove_string_from_cstr("missing");
                if (prove_table_has(k3, t)) return 8;
                Prove_Option_voidptr r3 = prove_table_get(k3, t);
                if (Prove_Option_voidptr_is_some(r3)) return 9;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="table_basic")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_update_existing(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_table.h"
            #include <stdio.h>

            int main(void) {
                Prove_Table *t = prove_table_new();
                Prove_String *k = prove_string_from_cstr("key");

                t = prove_table_add(k, (void*)1, t);
                t = prove_table_add(k, (void*)2, t);

                if (prove_table_length(t) != 1) return 1;
                Prove_Option_voidptr r = prove_table_get(k, t);
                if ((int64_t)r.value != 2) return 2;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="table_update")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_remove(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_table.h"
            #include <stdio.h>

            int main(void) {
                Prove_Table *t = prove_table_new();
                Prove_String *k1 = prove_string_from_cstr("a");
                Prove_String *k2 = prove_string_from_cstr("b");

                t = prove_table_add(k1, (void*)1, t);
                t = prove_table_add(k2, (void*)2, t);
                if (prove_table_length(t) != 2) return 1;

                t = prove_table_remove(k1, t);
                if (prove_table_length(t) != 1) return 2;
                if (prove_table_has(k1, t)) return 3;
                if (!prove_table_has(k2, t)) return 4;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="table_remove")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_keys_values(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_table.h"
            #include <stdio.h>

            int main(void) {
                Prove_Table *t = prove_table_new();
                t = prove_table_add(prove_string_from_cstr("x"), (void*)10, t);
                t = prove_table_add(prove_string_from_cstr("y"), (void*)20, t);

                Prove_List *ks = prove_table_keys(t);
                if (prove_list_len(ks) != 2) return 1;

                Prove_List *vs = prove_table_values(t);
                if (prove_list_len(vs) != 2) return 2;

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="table_keys")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_growth(self, tmp_path):
        code = textwrap.dedent("""\
            #include "prove_table.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                Prove_Table *t = prove_table_new();

                /* Insert enough entries to trigger resize */
                char buf[32];
                for (int i = 0; i < 100; i++) {
                    snprintf(buf, sizeof(buf), "key_%d", i);
                    Prove_String *k = prove_string_from_cstr(buf);
                    t = prove_table_add(k, (void*)(int64_t)i, t);
                }

                if (prove_table_length(t) != 100) return 1;

                /* Verify all entries */
                for (int i = 0; i < 100; i++) {
                    snprintf(buf, sizeof(buf), "key_%d", i);
                    Prove_String *k = prove_string_from_cstr(buf);
                    Prove_Option_voidptr r = prove_table_get(k, t);
                    if (!Prove_Option_voidptr_is_some(r)) return 2;
                    if ((int64_t)r.value != i) return 3;
                }

                printf("OK\\n");
                return 0;
            }
        """)
        result = _compile_and_run(tmp_path, code, name="table_growth")
        assert result.returncode == 0
        assert "OK" in result.stdout
