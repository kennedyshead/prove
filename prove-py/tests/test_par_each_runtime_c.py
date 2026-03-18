"""Tests for the par_each C runtime function (prove_par_each)."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestParEachSequential:
    def test_sequential_fallback(self, tmp_path, runtime_dir):
        """prove_par_each with num_workers=1 processes all elements."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>
            #include <pthread.h>

            static int64_t counter = 0;
            static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;

            static void increment(void *x, void *ctx) {
                (void)x; (void)ctx;
                pthread_mutex_lock(&mu);
                counter++;
                pthread_mutex_unlock(&mu);
            }

            int main(void) {
                Prove_List *l = prove_list_new(5);
                for (int i = 0; i < 5; i++)
                    prove_list_push(l, (void *)(intptr_t)i);

                prove_par_each(l, increment, NULL, 1);
                printf("%lld\\n", (long long)counter);
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir,
            tmp_path,
            code,
            name="seq",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "5"

    def test_empty_list(self, tmp_path, runtime_dir):
        """prove_par_each on empty list does not crash."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>

            static void noop(void *x, void *ctx) {
                (void)x; (void)ctx;
            }

            int main(void) {
                Prove_List *l = prove_list_new(0);
                prove_par_each(l, noop, NULL, 4);
                printf("ok\\n");
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir,
            tmp_path,
            code,
            name="empty",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"


class TestParEachParallel:
    def test_parallel_four_workers(self, tmp_path, runtime_dir):
        """prove_par_each with 4 workers processes all elements exactly once."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>
            #include <pthread.h>

            static int64_t counter = 0;
            static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;

            static void increment(void *x, void *ctx) {
                (void)x; (void)ctx;
                pthread_mutex_lock(&mu);
                counter++;
                pthread_mutex_unlock(&mu);
            }

            int main(void) {
                Prove_List *l = prove_list_new(20);
                for (int i = 0; i < 20; i++)
                    prove_list_push(l, (void *)(intptr_t)i);

                prove_par_each(l, increment, NULL, 4);
                printf("%lld\\n", (long long)counter);
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir,
            tmp_path,
            code,
            name="par4",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "20"

    def test_parallel_auto_workers(self, tmp_path, runtime_dir):
        """prove_par_each with num_workers=0 auto-detects and processes all elements."""
        code = textwrap.dedent("""\
            #include "prove_par_map.h"
            #include <stdio.h>
            #include <stdint.h>
            #include <pthread.h>

            static int64_t counter = 0;
            static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;

            static void increment(void *x, void *ctx) {
                (void)x; (void)ctx;
                pthread_mutex_lock(&mu);
                counter++;
                pthread_mutex_unlock(&mu);
            }

            int main(void) {
                Prove_List *l = prove_list_new(16);
                for (int i = 0; i < 16; i++)
                    prove_list_push(l, (void *)(intptr_t)i);

                prove_par_each(l, increment, NULL, 0);
                printf("%lld\\n", (long long)counter);
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir,
            tmp_path,
            code,
            name="auto",
            extra_flags=["-lpthread"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "16"
