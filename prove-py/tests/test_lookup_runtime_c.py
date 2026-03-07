"""Tests for the prove_lookup C runtime module."""

from __future__ import annotations

import textwrap

from runtime_helpers import compile_and_run


class TestLookupFind:
    def test_find_existing_key(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_lookup.h"
            #include <stdio.h>
            static const Prove_LookupEntry entries[] = {
                {"first", 0},
                {"second", 1},
                {"third", 2},
            };
            static const Prove_LookupTable table = {entries, 3};
            int main(void) {
                printf("%d\\n", prove_lookup_find(&table, "second"));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="find_existing")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_find_first_key(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_lookup.h"
            #include <stdio.h>
            static const Prove_LookupEntry entries[] = {
                {"alpha", 0},
                {"beta", 1},
            };
            static const Prove_LookupTable table = {entries, 2};
            int main(void) {
                printf("%d\\n", prove_lookup_find(&table, "alpha"));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="find_first")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_find_last_key(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_lookup.h"
            #include <stdio.h>
            static const Prove_LookupEntry entries[] = {
                {"alpha", 0},
                {"beta", 1},
                {"gamma", 2},
            };
            static const Prove_LookupTable table = {entries, 3};
            int main(void) {
                printf("%d\\n", prove_lookup_find(&table, "gamma"));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="find_last")
        assert result.returncode == 0
        assert result.stdout.strip() == "2"

    def test_find_missing_key(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_lookup.h"
            #include <stdio.h>
            static const Prove_LookupEntry entries[] = {
                {"first", 0},
                {"second", 1},
            };
            static const Prove_LookupTable table = {entries, 2};
            int main(void) {
                printf("%d\\n", prove_lookup_find(&table, "missing"));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="find_missing")
        assert result.returncode == 0
        assert result.stdout.strip() == "-1"

    def test_empty_table(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_lookup.h"
            #include <stdio.h>
            static const Prove_LookupTable table = {NULL, 0};
            int main(void) {
                printf("%d\\n", prove_lookup_find(&table, "anything"));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="empty_table")
        assert result.returncode == 0
        assert result.stdout.strip() == "-1"
