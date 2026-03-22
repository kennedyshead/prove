"""Tests for the Graphic stdlib module (checker and stdlib_loader integration)."""

from __future__ import annotations

from tests.helpers import check, check_fails


class TestGraphicModuleImport:
    """Graphic module provides GraphicAppEvent and widget functions."""

    def test_import_graphic_types(self):
        check("""\
module TestGraphicTypes
  Graphic types GraphicAppEvent
""")

    def test_import_graphic_functions(self):
        check("""\
module TestGraphicFuncs
  Graphic outputs window button label text_input checkbox slider progress quit types GraphicAppEvent
""")

    def test_graphic_app_event_extends_app_event(self):
        """GraphicAppEvent can be used as a base for custom event types."""
        check("""\
module TestGraphicEvent
  Graphic types GraphicAppEvent

  type MyApp is GraphicAppEvent
""")

    def test_graphic_app_event_with_custom_variants(self):
        """User can add custom variants to GraphicAppEvent subtypes."""
        check("""\
module TestGraphicCustom
  Graphic types GraphicAppEvent

  type MyApp is GraphicAppEvent
    AddItem
    | RemoveItem(index Integer)
""")


class TestGraphicRendersAnnotations:
    """The renders verb annotation rules apply with Graphic backend."""

    def test_renders_requires_event_type_graphic(self):
        check_fails(
            """\
module TestRendersNoEvent
  Graphic outputs window label types GraphicAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    state_init 0
  from
      Exit(state) => Unit
""",
            "E406",
        )

    def test_renders_requires_state_init_graphic(self):
        check_fails(
            """\
module TestRendersNoState
  Graphic outputs window label types GraphicAppEvent

  type MyApp is GraphicAppEvent

  renders interface(registered_attached_verbs List<Attached>)
    event_type MyApp
  from
      Exit(state) => Unit
""",
            "E408",
        )


class TestGraphicStdlibLoader:
    """stdlib_loader correctly registers the Graphic module."""

    def test_graphic_in_stdlib_link_flags(self):
        from prove.stdlib_loader import stdlib_link_flags

        flags = stdlib_link_flags("graphic")
        # Should return some flags (SDL2 + OpenGL)
        assert len(flags) > 0

    def test_graphic_binary_c_name(self):
        from prove.stdlib_loader import binary_c_name

        assert binary_c_name("graphic", "outputs", "window") == "prove_gui_window"
        assert binary_c_name("graphic", "outputs", "button") == "prove_gui_button"
        assert binary_c_name("graphic", "outputs", "label") == "prove_gui_label"
        assert binary_c_name("graphic", "outputs", "text_input") == "prove_gui_text_input"
        assert binary_c_name("graphic", "outputs", "checkbox") == "prove_gui_checkbox"
        assert binary_c_name("graphic", "outputs", "slider") == "prove_gui_slider"
        assert binary_c_name("graphic", "outputs", "progress") == "prove_gui_progress"
        assert binary_c_name("graphic", "outputs", "quit") == "prove_gui_quit"

    def test_graphic_in_stdlib_runtime_libs(self):
        from prove.c_runtime import STDLIB_RUNTIME_LIBS

        assert "graphic" in STDLIB_RUNTIME_LIBS
        assert "prove_gui" in STDLIB_RUNTIME_LIBS["graphic"]

    def test_graphic_load_stdlib_signatures(self):
        from prove.stdlib_loader import load_stdlib

        sigs = load_stdlib("graphic")
        names = {s.name for s in sigs}
        assert names == {
            "window",
            "button",
            "label",
            "text_input",
            "checkbox",
            "slider",
            "progress",
            "quit",
        }

    def test_graphic_function_return_types(self):
        from prove.stdlib_loader import load_stdlib

        sigs = {s.name: s for s in load_stdlib("graphic")}
        assert sigs["button"].return_type.name == "Boolean"
        assert sigs["text_input"].return_type.name == "String"
        assert sigs["checkbox"].return_type.name == "Boolean"
        assert sigs["slider"].return_type.name == "Float"

    def test_graphic_is_stdlib_module(self):
        from prove.stdlib_loader import is_stdlib_module

        assert is_stdlib_module("Graphic")
        assert is_stdlib_module("graphic")
