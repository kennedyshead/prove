"""Tests for the par_map C runtime module (prove_par_map)."""

from __future__ import annotations

import textwrap

from runtime_helpers import compile_and_run


class TestParMapSequential:
    def test_sequential_fallback(self, tmp_path, runtime_dir):
        """par_map with num_workers=1 falls back to sequential."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>

            static void *double_val(void *x) {
                return (void *)((intptr_t)x * 2);
            }

            int main(void) {
                Prove_List *l = prove_list_new(4);
                for (int i = 1; i <= 5; i++)
                    prove_list_push(l, (void *)(intptr_t)i);

                Prove_List *r = prove_par_map(l, double_val, 1);
                for (int64_t i = 0; i < prove_list_len(r); i++)
                    printf("%lld ", (long long)(intptr_t)prove_list_get(r, i));
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="seq",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "2 4 6 8 10"

    def test_empty_list(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>

            static void *double_val(void *x) {
                return (void *)((intptr_t)x * 2);
            }

            int main(void) {
                Prove_List *l = prove_list_new(0);
                Prove_List *r = prove_par_map(l, double_val, 4);
                printf("%lld\\n", (long long)prove_list_len(r));
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="empty",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestParMapParallel:
    def test_parallel_two_workers(self, tmp_path, runtime_dir):
        """par_map with 2 workers produces correct results."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>

            static void *square_val(void *x) {
                intptr_t v = (intptr_t)x;
                return (void *)(intptr_t)(v * v);
            }

            int main(void) {
                Prove_List *l = prove_list_new(8);
                for (int i = 1; i <= 8; i++)
                    prove_list_push(l, (void *)(intptr_t)i);

                Prove_List *r = prove_par_map(l, square_val, 2);
                for (int64_t i = 0; i < prove_list_len(r); i++)
                    printf("%lld ", (long long)(intptr_t)prove_list_get(r, i));
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="par2",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1 4 9 16 25 36 49 64"

    def test_parallel_four_workers(self, tmp_path, runtime_dir):
        """par_map with 4 workers on a larger list."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>

            static void *triple_val(void *x) {
                return (void *)((intptr_t)x * 3);
            }

            int main(void) {
                Prove_List *l = prove_list_new(16);
                for (int i = 0; i < 12; i++)
                    prove_list_push(l, (void *)(intptr_t)(i + 1));

                Prove_List *r = prove_par_map(l, triple_val, 4);
                int64_t sum = 0;
                for (int64_t i = 0; i < prove_list_len(r); i++)
                    sum += (intptr_t)prove_list_get(r, i);
                /* sum of 3*1 + 3*2 + ... + 3*12 = 3 * 78 = 234 */
                printf("%lld\\n", (long long)sum);
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="par4",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "234"

    def test_workers_exceed_list_length(self, tmp_path, runtime_dir):
        """More workers than elements falls back to sequential."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>

            static void *incr(void *x) {
                return (void *)((intptr_t)x + 1);
            }

            int main(void) {
                Prove_List *l = prove_list_new(2);
                prove_list_push(l, (void *)(intptr_t)10);
                prove_list_push(l, (void *)(intptr_t)20);

                Prove_List *r = prove_par_map(l, incr, 8);
                for (int64_t i = 0; i < prove_list_len(r); i++)
                    printf("%lld ", (long long)(intptr_t)prove_list_get(r, i));
                printf("\\n");
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="excess",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "11 21"
