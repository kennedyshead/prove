"""Shared pytest fixtures for the Prove compiler test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from prove.c_compiler import find_c_compiler
from prove.c_runtime import copy_runtime


@pytest.fixture(scope="session")
def _cc() -> str | None:
    """Discover C compiler once per session."""
    return find_c_compiler()


@pytest.fixture
def needs_cc(_cc: str | None) -> None:
    """Skip test if no C compiler is available."""
    if _cc is None:
        pytest.skip("no C compiler available")


@pytest.fixture(scope="session")
def _runtime_dir_session(tmp_path_factory: pytest.TempPathFactory, _cc: str | None) -> Path | None:
    """Copy runtime files once per session. Returns None when no compiler."""
    if _cc is None:
        return None
    tmp = tmp_path_factory.mktemp("runtime")
    copy_runtime(tmp)
    return tmp / "runtime"


@pytest.fixture
def runtime_dir(_runtime_dir_session: Path | None, needs_cc: None) -> Path | None:
    """Return the session-scoped runtime directory (skips if no compiler)."""
    return _runtime_dir_session
