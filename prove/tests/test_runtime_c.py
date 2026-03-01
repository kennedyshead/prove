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
