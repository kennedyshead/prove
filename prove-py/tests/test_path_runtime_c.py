"""Tests for the Path C runtime module."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestPathJoin:
    def test_join_basic(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *b = prove_string_from_cstr("/home/user");
                Prove_String *p = prove_string_from_cstr("file.txt");
                Prove_String *r = prove_path_join(b, p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="join")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user/file.txt"

    def test_join_trailing_slash(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *b = prove_string_from_cstr("/home/user/");
                Prove_String *p = prove_string_from_cstr("file.txt");
                Prove_String *r = prove_path_join(b, p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="join_slash")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user/file.txt"

    def test_join_absolute_part(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *b = prove_string_from_cstr("/home/user");
                Prove_String *p = prove_string_from_cstr("/etc/config");
                Prove_String *r = prove_path_join(b, p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="join_abs")
        assert result.returncode == 0
        assert result.stdout.strip() == "/etc/config"


class TestPathParent:
    def test_parent_nested(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_parent(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="parent")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user"

    def test_parent_root(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/file.txt");
                Prove_String *r = prove_path_parent(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="parent_root")
        assert result.returncode == 0
        assert result.stdout.strip() == "/"

    def test_parent_no_sep(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("file.txt");
                Prove_String *r = prove_path_parent(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="parent_nosep")
        assert result.returncode == 0
        assert result.stdout.strip() == "."


class TestPathComponents:
    def test_name(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_name(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="name")
        assert result.returncode == 0
        assert result.stdout.strip() == "file.txt"

    def test_stem(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_stem(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="stem")
        assert result.returncode == 0
        assert result.stdout.strip() == "file"

    def test_extension(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/file.txt");
                Prove_String *r = prove_path_extension(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="ext")
        assert result.returncode == 0
        assert result.stdout.strip() == ".txt"

    def test_extension_none(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/Makefile");
                Prove_String *r = prove_path_extension(p);
                printf("[%.*s]\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="ext_none")
        assert result.returncode == 0
        assert result.stdout.strip() == "[]"


class TestPathAbsolute:
    def test_absolute_true(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user");
                printf("%s\\n", prove_path_absolute(p) ? "yes" : "no");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="abs_true")
        assert result.returncode == 0
        assert result.stdout.strip() == "yes"

    def test_absolute_false(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("relative/path");
                printf("%s\\n", prove_path_absolute(p) ? "yes" : "no");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="abs_false")
        assert result.returncode == 0
        assert result.stdout.strip() == "no"


class TestPathNormalize:
    def test_normalize_dots(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user/../admin/./config");
                Prove_String *r = prove_path_normalize(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="norm")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/admin/config"

    def test_normalize_clean(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_path.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *p = prove_string_from_cstr("/home/user");
                Prove_String *r = prove_path_normalize(p);
                printf("%.*s\\n", (int)r->length, r->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="norm_clean")
        assert result.returncode == 0
        assert result.stdout.strip() == "/home/user"
