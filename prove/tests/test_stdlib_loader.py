"""Tests for stdlib module integrity.

Ensures every module registered in _STDLIB_MODULES actually exists,
parses successfully, has a proper module declaration, and exposes
at least one function signature.
"""

import pytest

from prove.ast_nodes import ModuleDecl
from prove.stdlib_loader import (
    _ALIAS_KEYS,
    _MODULE_DISPLAY_NAMES,
    _STDLIB_MODULES,
    _parse_stdlib_module,
    load_stdlib,
)


# Canonical modules (exclude alias keys like "listutils" → "list_utils.prv")
_CANONICAL = [k for k in _STDLIB_MODULES if k not in _ALIAS_KEYS]


@pytest.mark.parametrize("module_name", _CANONICAL)
def test_stdlib_module_loads(module_name: str):
    """Every registered stdlib module must load with at least one signature."""
    sigs = load_stdlib(module_name)
    assert sigs, (
        f"stdlib module '{module_name}' "
        f"(file: {_STDLIB_MODULES[module_name]}) "
        f"returned no signatures — file missing or unparseable"
    )


@pytest.mark.parametrize("module_name", _CANONICAL)
def test_stdlib_module_has_module_decl(module_name: str):
    """Every stdlib file must contain a module declaration with the correct name."""
    module = _parse_stdlib_module(module_name)
    assert module is not None, (
        f"stdlib module '{module_name}' failed to parse"
    )

    expected_name = _MODULE_DISPLAY_NAMES.get(module_name)
    assert expected_name is not None, (
        f"stdlib module '{module_name}' missing from _MODULE_DISPLAY_NAMES"
    )

    mod_decls = [
        d for d in module.declarations if isinstance(d, ModuleDecl)
    ]
    assert mod_decls, (
        f"stdlib file '{_STDLIB_MODULES[module_name]}' "
        f"has no module declaration — expected 'module {expected_name}'"
    )
    assert mod_decls[0].name == expected_name, (
        f"stdlib file '{_STDLIB_MODULES[module_name]}' "
        f"declares 'module {mod_decls[0].name}' "
        f"but expected 'module {expected_name}'"
    )
