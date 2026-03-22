"""Tests for stdlib module integrity.

Ensures every module registered in _STDLIB_MODULES actually exists,
parses successfully, has a proper module declaration, and exposes
at least one function signature or constant.
"""

import pytest

from prove.ast_nodes import ModuleDecl
from prove.stdlib_loader import (
    _ALIAS_KEYS,
    _MODULE_DISPLAY_NAMES,
    _STDLIB_MODULES,
    _parse_stdlib_module,
    load_stdlib,
    load_stdlib_constants,
)

# Canonical modules (exclude alias keys like "listutils" → "list_utils.prv")
_CANONICAL = [k for k in _STDLIB_MODULES if k not in _ALIAS_KEYS]


@pytest.mark.parametrize("module_name", _CANONICAL)
def test_stdlib_module_loads(module_name: str):
    """Every registered stdlib module must load with at least one signature, constant, or type."""
    sigs = load_stdlib(module_name)
    consts = load_stdlib_constants(module_name)
    # Type-only modules (e.g. UI) have no functions or constants but export types
    has_types = False
    module = _parse_stdlib_module(module_name)
    if module:
        from prove.ast_nodes import TypeDef

        has_types = any(
            isinstance(d, TypeDef)
            or (
                isinstance(d, ModuleDecl)
                and (any(isinstance(b, TypeDef) for b in d.body) or bool(getattr(d, "types", [])))
            )
            for d in module.declarations
        )
    assert sigs or consts or has_types, (
        f"stdlib module '{module_name}' "
        f"(file: {_STDLIB_MODULES[module_name]}) "
        f"returned no signatures, constants, or types — file missing or unparseable"
    )


@pytest.mark.parametrize("module_name", _CANONICAL)
def test_stdlib_module_has_module_decl(module_name: str):
    """Every stdlib file must contain a module declaration with the correct name."""
    module = _parse_stdlib_module(module_name)
    assert module is not None, f"stdlib module '{module_name}' failed to parse"

    expected_name = _MODULE_DISPLAY_NAMES.get(module_name)
    assert expected_name is not None, (
        f"stdlib module '{module_name}' missing from _MODULE_DISPLAY_NAMES"
    )

    mod_decls = [d for d in module.declarations if isinstance(d, ModuleDecl)]
    assert mod_decls, (
        f"stdlib file '{_STDLIB_MODULES[module_name]}' "
        f"has no module declaration — expected 'module {expected_name}'"
    )
    assert mod_decls[0].name == expected_name, (
        f"stdlib file '{_STDLIB_MODULES[module_name]}' "
        f"declares 'module {mod_decls[0].name}' "
        f"but expected 'module {expected_name}'"
    )


class TestLoadStdlibConstants:
    """Test load_stdlib_constants() for pure-Prove stdlib modules."""

    def test_log_returns_constants(self):
        consts = load_stdlib_constants("log")
        assert len(consts) >= 10
        names = {c.name for c in consts}
        assert "RED" in names
        assert "GREEN" in names
        assert "RESET" in names

    def test_log_constant_types(self):
        consts = load_stdlib_constants("log")
        for c in consts:
            assert c.type_name == "String"

    def test_log_constant_values_contain_escape(self):
        consts = load_stdlib_constants("log")
        by_name = {c.name: c for c in consts}
        assert "\x1b[31m" in by_name["RED"].raw_value
        assert "\x1b[0m" in by_name["RESET"].raw_value

    def test_nonexistent_module_returns_empty(self):
        consts = load_stdlib_constants("nonexistent")
        assert consts == []

    def test_function_module_returns_empty(self):
        """Modules with only functions should return no constants."""
        consts = load_stdlib_constants("math")
        assert consts == []
