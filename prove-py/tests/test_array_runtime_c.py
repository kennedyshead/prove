"""Tests for the Array C runtime module (prove_array)."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestArraySafeAccess:
    def test_get_safe_bool_in_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_bool(3, false);
                prove_array_set_mut_bool(arr, 1, true);
                Prove_Option opt = prove_array_get_safe_bool(arr, 1);
                printf("%d %d\\n", prove_option_is_some(opt),
                       (int)(intptr_t)opt.value);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="get_safe_bool")
        assert result.returncode == 0
        assert result.stdout.strip() == "1 1"

    def test_get_safe_bool_out_of_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_bool(3, false);
                Prove_Option opt = prove_array_get_safe_bool(arr, 5);
                printf("%d\\n", prove_option_is_none(opt));
                opt = prove_array_get_safe_bool(arr, -1);
                printf("%d\\n", prove_option_is_none(opt));
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="get_safe_bool_oob")
        assert result.returncode == 0
        assert result.stdout.strip() == "1\n1"

    def test_get_safe_int_in_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(3, 0);
                prove_array_set_mut_int(arr, 0, 42);
                prove_array_set_mut_int(arr, 2, 99);
                Prove_Option o0 = prove_array_get_safe_int(arr, 0);
                Prove_Option o2 = prove_array_get_safe_int(arr, 2);
                printf("%lld %lld\\n",
                       (long long)(int64_t)(intptr_t)o0.value,
                       (long long)(int64_t)(intptr_t)o2.value);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="get_safe_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "42 99"

    def test_get_safe_int_out_of_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(2, 0);
                Prove_Option opt = prove_array_get_safe_int(arr, 2);
                printf("%d\\n", prove_option_is_none(opt));
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="get_safe_int_oob")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_set_safe_int_in_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(3, 0);
                Prove_Option opt = prove_array_set_safe_int(arr, 1, 77);
                if (prove_option_is_none(opt)) return 1;
                Prove_Array *updated = (Prove_Array *)opt.value;
                printf("%lld\\n",
                       (long long)prove_array_get_int(updated, 1));
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="set_safe_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "77"

    def test_set_safe_int_out_of_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(3, 0);
                Prove_Option opt = prove_array_set_safe_int(arr, 10, 77);
                printf("%d\\n", prove_option_is_none(opt));
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="set_safe_int_oob")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_set_safe_bool_in_bounds(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_bool(3, false);
                Prove_Option opt = prove_array_set_safe_bool(arr, 2, true);
                if (prove_option_is_none(opt)) return 1;
                Prove_Array *updated = (Prove_Array *)opt.value;
                printf("%d\\n", prove_array_get_bool(updated, 2));
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="set_safe_bool")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestArrayHOF:
    def test_each_int(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            static int64_t total = 0;
            static void add_val(void *v) {
                total += (int64_t)(intptr_t)v;
            }
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(3, 0);
                prove_array_set_mut_int(arr, 0, 10);
                prove_array_set_mut_int(arr, 1, 20);
                prove_array_set_mut_int(arr, 2, 30);
                prove_array_each(arr, add_val);
                printf("%lld\\n", (long long)total);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="each_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "60"

    def test_map_int(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            static void *double_val(void *v) {
                return (void *)((intptr_t)v * 2);
            }
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(3, 0);
                prove_array_set_mut_int(arr, 0, 5);
                prove_array_set_mut_int(arr, 1, 10);
                prove_array_set_mut_int(arr, 2, 15);
                Prove_Array *mapped = prove_array_map(arr, double_val, sizeof(int64_t));
                for (int64_t i = 0; i < mapped->length; i++) {
                    printf("%lld ", (long long)prove_array_get_int(mapped, i));
                }
                printf("\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="map_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "10 20 30"

    def test_reduce_int(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            static void *sum_fn(void *accum, void *elem) {
                return (void *)((intptr_t)accum + (intptr_t)elem);
            }
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(4, 0);
                prove_array_set_mut_int(arr, 0, 1);
                prove_array_set_mut_int(arr, 1, 2);
                prove_array_set_mut_int(arr, 2, 3);
                prove_array_set_mut_int(arr, 3, 4);
                void *result = prove_array_reduce(arr, (void *)0, sum_fn);
                printf("%lld\\n", (long long)(int64_t)(intptr_t)result);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="reduce_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "10"

    def test_filter_int(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            static bool is_even(void *v) {
                return ((int64_t)(intptr_t)v % 2) == 0;
            }
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(5, 0);
                for (int64_t i = 0; i < 5; i++)
                    prove_array_set_mut_int(arr, i, i + 1);
                Prove_List *filtered = prove_array_filter(arr, is_even);
                printf("%lld:", (long long)prove_list_len(filtered));
                for (int64_t i = 0; i < prove_list_len(filtered); i++) {
                    printf(" %lld", (long long)(int64_t)(intptr_t)prove_list_get(filtered, i));
                }
                printf("\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="filter_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "2: 2 4"

    def test_map_empty(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_array.h"
            #include <stdio.h>
            static void *noop(void *v) { return v; }
            int main(void) {
                prove_runtime_init();
                Prove_Array *arr = prove_array_new_int(0, 0);
                Prove_Array *mapped = prove_array_map(arr, noop, sizeof(int64_t));
                printf("%lld\\n", (long long)mapped->length);
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="map_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"
