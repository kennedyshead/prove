"""Shared pytest fixtures for the Prove compiler test suite."""

from __future__ import annotations

import pytest

from prove.c_compiler import find_c_compiler


@pytest.fixture
def needs_cc():
    """Skip test if no C compiler is available."""
    if find_c_compiler() is None:
        pytest.skip("no C compiler available")
