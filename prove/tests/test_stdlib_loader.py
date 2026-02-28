"""Tests for stdlib module integrity.

Ensures every module registered in _STDLIB_MODULES actually exists,
parses successfully, and exposes at least one function signature.
"""

import pytest

from prove.stdlib_loader import (
    _ALIAS_KEYS,
    _STDLIB_MODULES,
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
