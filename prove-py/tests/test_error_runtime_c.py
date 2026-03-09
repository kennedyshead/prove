"""Tests for the Error C runtime module."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestErrorResult:
    def test_ok_on_success(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_result_ok_int(42);
                printf("%s\\n", prove_error_ok(r) ? "yes" : "no");
                printf("%s\\n", prove_error_err(r) ? "yes" : "no");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="ok_succ")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "yes"
        assert lines[1] == "no"

    def test_ok_on_failure(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_result_err(prove_string_from_cstr("fail"));
                printf("%s\\n", prove_error_ok(r) ? "yes" : "no");
                printf("%s\\n", prove_error_err(r) ? "yes" : "no");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="ok_fail")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "no"
        assert lines[1] == "yes"


class TestErrorOption:
    def test_some_present(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Option o = prove_option_some((Prove_Value*)(intptr_t)(42));
                printf("%s\\n", prove_error_some_int(o) ? "some" : "none");
                printf("%s\\n", prove_error_none_int(o) ? "none" : "some");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="some_int")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "some"
        assert lines[1] == "some"

    def test_none_absent(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Option o = prove_option_none();
                printf("%s\\n", prove_error_some_int(o) ? "some" : "none");
                printf("%s\\n", prove_error_none_int(o) ? "none" : "some");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="none_int")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "none"
        assert lines[1] == "none"

    def test_some_str(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                Prove_Option o = prove_option_some((Prove_Value*)s);
                printf("%s\\n", prove_error_some_str(o) ? "some" : "none");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="some_str")
        assert result.returncode == 0
        assert result.stdout.strip() == "some"

    def test_none_str(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Option o = prove_option_none();
                printf("%s\\n", prove_error_none_str(o) ? "none" : "some");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="none_str")
        assert result.returncode == 0
        assert result.stdout.strip() == "none"


class TestErrorUnwrapOr:
    def test_unwrap_or_present(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Option o = prove_option_some((Prove_Value*)(intptr_t)(42));
                printf("%lld\\n", (long long)prove_error_unwrap_or_int(o, 0));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="unwrap_some")
        assert result.returncode == 0
        assert result.stdout.strip() == "42"

    def test_unwrap_or_absent(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Option o = prove_option_none();
                printf("%lld\\n", (long long)prove_error_unwrap_or_int(o, 99));
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="unwrap_none")
        assert result.returncode == 0
        assert result.stdout.strip() == "99"

    def test_unwrap_or_str_present(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                Prove_Option o = prove_option_some((Prove_Value*)s);
                Prove_String *def = prove_string_from_cstr("default");
                Prove_String *r = prove_error_unwrap_or_str(o, def);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="unwrap_str_some")
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"

    def test_unwrap_or_str_absent(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_error.h"
            #include <stdio.h>
            int main(void) {
                Prove_Option o = prove_option_none();
                Prove_String *def = prove_string_from_cstr("default");
                Prove_String *r = prove_error_unwrap_or_str(o, def);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="unwrap_str_none")
        assert result.returncode == 0
        assert result.stdout.strip() == "default"
