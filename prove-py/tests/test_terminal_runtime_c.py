"""Tests for the prove_terminal C runtime."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestTerminalRuntime:
    def test_size_returns_valid(self, tmp_path, runtime_dir):
        """prove_terminal_size() returns a valid Position with positive dimensions."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include <stdio.h>

            int main(void) {
                Prove_Position pos = prove_terminal_size();
                /* When running in a pipe, ioctl may fail — defaults to 80x24 */
                if (pos.x <= 0 || pos.y <= 0) return 1;
                printf("OK %lld %lld\\n", (long long)pos.x, (long long)pos.y);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_size")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_validates_in_pipe(self, tmp_path, runtime_dir):
        """prove_terminal_validates() returns false when stdout is piped."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include <stdio.h>

            int main(void) {
                /* Running under pytest, stdout is piped — should return false */
                bool is_tty = prove_terminal_validates();
                printf("is_tty=%d\\n", is_tty);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_validates")
        assert result.returncode == 0
        assert "is_tty=0" in result.stdout

    def test_clear_does_not_crash(self, tmp_path, runtime_dir):
        """prove_terminal_clear() emits ANSI escape without crashing."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include <stdio.h>

            int main(void) {
                prove_terminal_clear();
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_clear")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_cursor_does_not_crash(self, tmp_path, runtime_dir):
        """prove_terminal_cursor() emits ANSI escape without crashing."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include <stdio.h>

            int main(void) {
                prove_terminal_cursor(5, 10);
                printf("OK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_cursor")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_write_does_not_crash(self, tmp_path, runtime_dir):
        """prove_terminal_write() outputs text without crashing."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include "prove_string.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("hello");
                prove_terminal_write(s);
                printf("\\nOK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_write")
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_write_at_does_not_crash(self, tmp_path, runtime_dir):
        """prove_terminal_write_at() outputs text at position without crashing."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include "prove_string.h"
            #include <stdio.h>

            int main(void) {
                Prove_String *s = prove_string_from_cstr("test");
                prove_terminal_write_at(0, 0, s);
                printf("\\nOK\\n");
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_write_at")
        assert result.returncode == 0
        assert "OK" in result.stdout
