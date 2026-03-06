"""Shared pytest fixtures for the Prove compiler test suite."""

from __future__ import annotations

import pytest

from prove.c_compiler import find_c_compiler
from prove.c_runtime import copy_runtime


@pytest.fixture
def needs_cc():
    """Skip test if no C compiler is available."""
    if find_c_compiler() is None:
        pytest.skip("no C compiler available")


@pytest.fixture
def runtime_dir(tmp_path, needs_cc):
    """Copy runtime files to tmp_path and return the runtime directory."""
    copy_runtime(tmp_path)
    return tmp_path / "runtime"
