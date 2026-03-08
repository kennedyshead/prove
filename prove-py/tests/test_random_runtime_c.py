"""Tests for the Random C runtime module."""

from __future__ import annotations

import textwrap

from runtime_helpers import compile_and_run


class TestRandomInteger:
    def test_integer_returns_value(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                int64_t v = prove_random_integer();
                printf("ok\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_int")
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"

    def test_integer_range(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                int ok = 1;
                for (int i = 0; i < 100; i++) {
                    int64_t v = prove_random_integer_range(10, 20);
                    if (v < 10 || v > 20) { ok = 0; break; }
                }
                printf("%d\\n", ok);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_range")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_integer_range_min_equals_max(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                int64_t v = prove_random_integer_range(42, 42);
                printf("%lld\\n", (long long)v);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_eq")
        assert result.returncode == 0
        assert result.stdout.strip() == "42"

    def test_validates_integer(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                printf("%d\\n", prove_random_validates_integer(5, 1, 10) ? 1 : 0);
                printf("%d\\n", prove_random_validates_integer(0, 1, 10) ? 1 : 0);
                printf("%d\\n", prove_random_validates_integer(11, 1, 10) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_val")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "1"  # 5 in [1,10]
        assert lines[1] == "0"  # 0 below range
        assert lines[2] == "0"  # 11 above range


class TestRandomDecimal:
    def test_decimal_in_range(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                int ok = 1;
                for (int i = 0; i < 100; i++) {
                    double v = prove_random_decimal();
                    if (v < 0.0 || v > 1.0) { ok = 0; break; }
                }
                printf("%d\\n", ok);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_dec")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_decimal_range(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                int ok = 1;
                for (int i = 0; i < 100; i++) {
                    double v = prove_random_decimal_range(5.0, 10.0);
                    if (v < 5.0 || v > 10.0) { ok = 0; break; }
                }
                printf("%d\\n", ok);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_dec_r")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestRandomBoolean:
    def test_boolean_returns_valid(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                int got_true = 0, got_false = 0;
                for (int i = 0; i < 200; i++) {
                    if (prove_random_boolean()) got_true = 1;
                    else got_false = 1;
                }
                /* Expect both values in 200 trials */
                printf("%d\\n", (got_true && got_false) ? 1 : 0);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_bool")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestRandomChoice:
    def test_choice_from_list(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *list = prove_list_new(3);
                int64_t a = 10, b = 20, c = 30;
                prove_list_push(list, &a);
                prove_list_push(list, &b);
                prove_list_push(list, &c);
                int ok = 1;
                for (int i = 0; i < 50; i++) {
                    int64_t *v = (int64_t *)prove_random_choice_raw(list);
                    if (*v != 10 && *v != 20 && *v != 30) { ok = 0; break; }
                }
                printf("%d\\n", ok);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_choice")
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestRandomShuffle:
    def test_shuffle_preserves_elements(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *list = prove_list_new(4);
                int64_t vals[] = {1, 2, 3, 4};
                for (int i = 0; i < 4; i++) prove_list_push(list, &vals[i]);
                Prove_List *shuffled = prove_random_shuffle_raw(list);
                /* Check same length */
                printf("%lld\\n", (long long)shuffled->length);
                /* Check all original elements present (sum should be 10) */
                int64_t sum = 0;
                for (int64_t i = 0; i < shuffled->length; i++) {
                    sum += *(int64_t *)prove_list_get(shuffled, i);
                }
                printf("%lld\\n", (long long)sum);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="rand_shuf")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "4"
        assert lines[1] == "10"

    def test_shuffle_empty_list(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_random.h"
            #include <stdio.h>
            int main(void) {
                Prove_List *list = prove_list_new(4);
                Prove_List *shuffled = prove_random_shuffle_raw(list);
                printf("%lld\\n", (long long)shuffled->length);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="shuf_empty")
        assert result.returncode == 0
        assert result.stdout.strip() == "0"
