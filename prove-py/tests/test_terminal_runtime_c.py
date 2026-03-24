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

    def test_color_ansi_known(self, tmp_path, runtime_dir):
        """prove_terminal_color_ansi() returns correct ANSI escape for known colors."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include "prove_string.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                Prove_String *name = prove_string_from_cstr("red");
                Prove_String *esc = prove_terminal_color_ansi(name);
                if (esc->length == 5 && memcmp(esc->data, "\\033[31m", 5) == 0) {
                    printf("RED OK\\n");
                } else {
                    printf("RED FAIL len=%zu\\n", esc->length);
                    return 1;
                }
                Prove_String *def = prove_string_from_cstr("default");
                Prove_String *reset = prove_terminal_color_ansi(def);
                if (reset->length == 4 && memcmp(reset->data, "\\033[0m", 4) == 0) {
                    printf("DEFAULT OK\\n");
                } else {
                    printf("DEFAULT FAIL len=%zu\\n", reset->length);
                    return 1;
                }
                Prove_String *unk = prove_string_from_cstr("unknown");
                Prove_String *empty = prove_terminal_color_ansi(unk);
                if (empty->length == 0) {
                    printf("UNKNOWN OK\\n");
                } else {
                    printf("UNKNOWN FAIL len=%zu\\n", empty->length);
                    return 1;
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_color_ansi")
        assert result.returncode == 0
        assert "RED OK" in result.stdout
        assert "DEFAULT OK" in result.stdout
        assert "UNKNOWN OK" in result.stdout

    def test_style_ansi_known(self, tmp_path, runtime_dir):
        """prove_terminal_color_ansi() also handles TextStyle names."""
        code = textwrap.dedent("""\
            #include "prove_terminal.h"
            #include "prove_string.h"
            #include <stdio.h>
            #include <string.h>

            int main(void) {
                Prove_String *bold = prove_terminal_color_ansi(prove_string_from_cstr("bold"));
                if (bold->length == 4 && memcmp(bold->data, "\\033[1m", 4) == 0) {
                    printf("BOLD OK\\n");
                } else {
                    printf("BOLD FAIL len=%zu\\n", bold->length);
                    return 1;
                }
                Prove_String *ul = prove_terminal_color_ansi(prove_string_from_cstr("underline"));
                if (ul->length == 4 && memcmp(ul->data, "\\033[4m", 4) == 0) {
                    printf("UNDERLINE OK\\n");
                } else {
                    printf("UNDERLINE FAIL len=%zu\\n", ul->length);
                    return 1;
                }
                Prove_String *st = prove_terminal_color_ansi(
                    prove_string_from_cstr("strikethrough"));
                if (st->length == 4 && memcmp(st->data, "\\033[9m", 4) == 0) {
                    printf("STRIKETHROUGH OK\\n");
                } else {
                    printf("STRIKETHROUGH FAIL len=%zu\\n", st->length);
                    return 1;
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="terminal_style_ansi")
        assert result.returncode == 0
        assert "BOLD OK" in result.stdout
        assert "UNDERLINE OK" in result.stdout
        assert "STRIKETHROUGH OK" in result.stdout

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
