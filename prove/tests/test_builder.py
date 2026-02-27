"""Integration tests for the build pipeline."""

import subprocess
from pathlib import Path

import pytest

from prove.builder import build_project
from prove.c_compiler import find_c_compiler
from prove.config import load_config

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def hello_project():
    return _EXAMPLES_DIR / "hello"


@pytest.fixture
def needs_cc():
    """Skip test if no C compiler is available."""
    if find_c_compiler() is None:
        pytest.skip("no C compiler available")


class TestBuildHello:
    def test_build_produces_binary(self, hello_project, needs_cc):
        config = load_config(hello_project / "prove.toml")
        result = build_project(hello_project, config)
        assert result.ok, f"Build failed: {result.c_error or result.diagnostics}"
        assert result.binary is not None
        assert result.binary.exists()

    def test_binary_runs_hello(self, hello_project, needs_cc):
        config = load_config(hello_project / "prove.toml")
        result = build_project(hello_project, config)
        assert result.ok, f"Build failed: {result.c_error or result.diagnostics}"

        proc = subprocess.run(
            [str(result.binary)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert proc.returncode == 0
        assert "Hello from Prove!" in proc.stdout


class TestBuildErrors:
    def test_no_prv_files(self, tmp_path, needs_cc):
        from prove.config import ProveConfig
        result = build_project(tmp_path, ProveConfig())
        assert not result.ok
