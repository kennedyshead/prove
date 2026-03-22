"""Tests for the renders verb and UI/Terminal stdlib modules."""

from __future__ import annotations

from tests.helpers import check, check_fails


class TestUIModuleImport:
    """UI module provides Key, Color, AppEvent, Position types."""

    def test_import_ui_types(self):
        check("""\
module TestUI
  UI types Key Color AppEvent Position
""")

    def test_import_terminal_types(self):
        check("""\
module TestTerminal
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent
""")


class TestRendersVerb:
    """The renders verb follows the listens pattern with state_init/state_type."""

    def test_renders_requires_event_type(self):
        check_fails(
            """\
module TestRendersNoEvent
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    state_init 0
  from
      Exit(state) => Unit
""",
            "E406",
        )

    def test_renders_requires_state_init(self):
        check_fails(
            """\
module TestRendersNoState
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    event_type MyEvent
  from
      Exit(state) => Unit
""",
            "E408",
        )

    def test_renders_requires_list_attached_param(self):
        check_fails(
            """\
module TestRendersNoAttached
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  renders interface()
    event_type MyEvent
    state_init 0
  from
      Exit(state) => Unit
""",
            "E402",
        )

    def test_renders_cannot_have_return_type(self):
        check_fails(
            """\
module TestRendersReturn
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  renders interface(registered_attached_verbs List<Attached>) Integer
    event_type MyEvent
    state_init 0
  from
      Exit(state) => Unit
""",
            "E374",
        )

    def test_state_init_only_on_renders(self):
        check_fails(
            """\
module TestStateInitWrong
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  listens interface(registered_attached_verbs List<Attached>)
    event_type MyEvent
    state_init 0
  from
      Exit(state) => Unit
""",
            "E407",
        )

    def test_state_type_only_on_attached(self):
        check_fails(
            """\
module TestStateTypeWrong
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    event_type MyEvent
    state_init 0
    state_type Integer
  from
      Exit(state) => Unit
""",
            "E409",
        )


class TestRendersBodyValidation:
    """Renders body must be a single match expression with an Exit arm."""

    def test_renders_body_must_be_match(self):
        import pytest

        from prove.errors import CompileError
        from prove.lexer import Lexer
        from prove.parser import Parser

        with pytest.raises(CompileError, match="single match expression"):
            tokens = Lexer(
                """\
module TestRendersNoMatch
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    event_type MyEvent
    state_init 0
  from
      x as Integer = 1
""",
                "<test>",
            ).lex()
            Parser(tokens, "<test>").parse()

    def test_renders_must_have_exit_arm(self):
        import pytest

        from prove.errors import CompileError
        from prove.lexer import Lexer
        from prove.parser import Parser

        with pytest.raises(CompileError, match="Exit"):
            tokens = Lexer(
                """\
module TestRendersNoExit
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyEvent is TerminalAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    event_type MyEvent
    state_init 0
  from
      Draw(state) => Unit
""",
                "<test>",
            ).lex()
            Parser(tokens, "<test>").parse()
