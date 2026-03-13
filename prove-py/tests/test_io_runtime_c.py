"""Tests for the System C runtime (file, system, dir, process channels).

Each test compiles a standalone C program that exercises the runtime and
checks results via exit codes and stdout.
"""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


# ── File I/O tests ────────────────────────────────────────────────


class TestFileIO:
    def test_file_write_and_read(self, tmp_path, runtime_dir):
        testfile = tmp_path / "test_data.txt"
        code = textwrap.dedent(f"""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {{
                prove_runtime_init();
                Prove_String *path = prove_string_from_cstr("{testfile}");
                Prove_String *content = prove_string_from_cstr("hello world");

                Prove_Result wr = prove_file_write(path, content);
                if (prove_result_is_err(wr)) return 1;

                Prove_Result rd = prove_file_read(path);
                if (prove_result_is_err(rd)) return 2;

                Prove_String *got = (Prove_String *)prove_result_unwrap_ptr(rd);
                if (!prove_string_eq(got, content)) return 3;

                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }}
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="file_rw")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_file_read_missing(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *path = prove_string_from_cstr("/tmp/nonexistent_prove_test_xyz");
                Prove_Result rd = prove_file_read(path);
                if (prove_result_is_err(rd)) {
                    printf("ERR_OK\\n");
                    prove_runtime_cleanup();
                    return 0;
                }
                return 1;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="file_missing")
        assert result.returncode == 0
        assert "ERR_OK" in result.stdout

    def test_file_validates(self, tmp_path, runtime_dir):
        testfile = tmp_path / "exists.txt"
        testfile.write_text("x")
        code = textwrap.dedent(f"""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {{
                prove_runtime_init();
                Prove_String *yes = prove_string_from_cstr("{testfile}");
                Prove_String *no = prove_string_from_cstr("/tmp/nonexistent_prove_xyz");
                if (!prove_io_file_validates(yes)) return 1;
                if (prove_io_file_validates(no)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }}
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="file_validates")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Console validates ─────────────────────────────────────────────


class TestConsoleValidates:
    def test_console_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                /* stdin is open, so validates should return true */
                if (!prove_io_console_validates()) return 1;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="console_val")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── System channel tests ──────────────────────────────────────────


class TestSystemChannel:
    def test_system_inputs_echo(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *cmd = prove_string_from_cstr("echo");
                Prove_List *args = prove_list_new(4);
                Prove_String *arg1 = prove_string_from_cstr("hello");
                prove_list_push(args, (void*)arg1);

                Prove_ProcessResult pr = prove_io_system_inputs(cmd, args);
                if (pr.exit_code != 0) return 1;
                /* stdout should contain "hello" */
                Prove_String *expected = prove_string_from_cstr("hello\\n");
                if (!prove_string_eq(pr.standard_output, expected)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="system_echo")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_system_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {
                prove_runtime_init();
                Prove_String *yes = prove_string_from_cstr("echo");
                Prove_String *no = prove_string_from_cstr("nonexistent_cmd_prove_xyz");
                if (!prove_io_system_validates(yes)) return 1;
                if (prove_io_system_validates(no)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="system_val")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Dir channel tests ─────────────────────────────────────────────


class TestDirChannel:
    def test_dir_outputs_creates_directory(self, tmp_path, runtime_dir):
        newdir = tmp_path / "subdir"
        code = textwrap.dedent(f"""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {{
                prove_runtime_init();
                Prove_String *path = prove_string_from_cstr("{newdir}");
                Prove_Result r = prove_io_dir_outputs(path);
                if (prove_result_is_err(r)) return 1;
                /* Verify it exists */
                if (!prove_io_dir_validates(path)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }}
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dir_create")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_dir_inputs_lists_entries(self, tmp_path, runtime_dir):
        # Create some entries
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()
        code = textwrap.dedent(f"""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {{
                prove_runtime_init();
                Prove_String *path = prove_string_from_cstr("{tmp_path}");
                Prove_List *entries = prove_io_dir_inputs(path);
                int64_t n = prove_list_len(entries);
                /* Should have at least 3 entries (a.txt, b.txt, sub)
                   but may include build artifacts from compilation */
                if (n < 3) return 1;
                printf("count=%lld\\n", (long long)n);
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }}
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dir_list")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_dir_inputs_trailing_slash_no_double(self, tmp_path, runtime_dir):
        """Path with trailing slash should not produce // in entry paths."""
        (tmp_path / "x.txt").write_text("x")
        path_with_slash = str(tmp_path) + "/"
        code = textwrap.dedent(f"""\
            #include "prove_input_output.h"
            #include <stdio.h>
            #include <string.h>
            int main(void) {{
                prove_runtime_init();
                Prove_String *path = prove_string_from_cstr("{path_with_slash}");
                Prove_List *entries = prove_io_dir_inputs(path);
                int64_t n = prove_list_len(entries);
                if (n < 1) return 1;
                for (int64_t i = 0; i < n; i++) {{
                    Prove_DirEntry *e = (Prove_DirEntry *)prove_list_get(entries, i);
                    if (strstr(e->path->data, "//")) {{
                        printf("DOUBLE_SLASH in %s\\n", e->path->data);
                        return 2;
                    }}
                }}
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }}
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dir_noslash")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_dir_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent(f"""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(void) {{
                prove_runtime_init();
                Prove_String *yes = prove_string_from_cstr("{tmp_path}");
                Prove_String *no = prove_string_from_cstr("/tmp/nonexistent_prove_dir_xyz");
                if (!prove_io_dir_validates(yes)) return 1;
                if (prove_io_dir_validates(no)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }}
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="dir_val")
        assert result.returncode == 0
        assert "OK" in result.stdout


# ── Process channel tests ─────────────────────────────────────────


class TestProcessChannel:
    def test_process_inputs_returns_argv(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(int argc, char **argv) {
                prove_runtime_init();
                prove_io_init_args(argc, argv);
                Prove_List *args = prove_io_process_inputs();
                int64_t n = prove_list_len(args);
                if (n != 3) return 1;
                /* argv[1] should be "foo" */
                Prove_String *a1 = (Prove_String *)prove_list_get(args, 1);
                Prove_String *expected = prove_string_from_cstr("foo");
                if (!prove_string_eq(a1, expected)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="process_args",
            args=["foo", "bar"],
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_process_validates(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_input_output.h"
            #include <stdio.h>
            int main(int argc, char **argv) {
                prove_runtime_init();
                prove_io_init_args(argc, argv);
                Prove_String *yes = prove_string_from_cstr("--flag");
                Prove_String *no = prove_string_from_cstr("--missing");
                if (!prove_io_process_validates(yes)) return 1;
                if (prove_io_process_validates(no)) return 2;
                printf("OK\\n");
                prove_runtime_cleanup();
                return 0;
            }
        """)
        result = compile_and_run(
            runtime_dir, tmp_path, code, name="process_val",
            args=["--flag"],
        )
        assert result.returncode == 0
        assert "OK" in result.stdout
