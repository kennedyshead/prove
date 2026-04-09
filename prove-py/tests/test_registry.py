"""Tests for the registry client (mocked HTTP)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from prove.registry import (
    compute_checksum,
    download_package,
    fetch_package_info,
    verify_checksum,
)


def _mock_urlopen(data: bytes, status: int = 200):
    """Create a mock for urllib.request.urlopen."""
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_fetch_package_info():
    index_data = json.dumps(
        {
            "name": "json-utils",
            "description": "JSON utilities",
            "versions": [
                {"version": "0.3.0", "checksum": "sha256:abc123", "prove_version": "1.0.0"},
                {"version": "0.2.0", "checksum": "sha256:def456", "prove_version": "1.0.0"},
            ],
        }
    ).encode()

    with patch("prove.registry.urlopen", return_value=_mock_urlopen(index_data)):
        info = fetch_package_info("json-utils", "https://example.com")

    assert info is not None
    assert info.name == "json-utils"
    assert info.description == "JSON utilities"
    assert len(info.versions) == 2
    assert info.versions[0].version == "0.3.0"
    assert info.versions[0].checksum == "sha256:abc123"


def test_fetch_package_info_failure():
    from urllib.error import URLError

    with patch("prove.registry.urlopen", side_effect=URLError("nope")):
        info = fetch_package_info("nonexistent", "https://example.com")
    assert info is None


def test_download_package():
    pkg_data = b"SQLite format 3\x00..."  # fake package data

    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch("prove.registry.cache_dir", return_value=Path(tmpdir)),
        patch("prove.registry.urlopen", return_value=_mock_urlopen(pkg_data)),
    ):
        result = download_package("json-utils", "0.3.0", "https://example.com")
        assert result is not None
        assert result.exists()
        assert result.read_bytes() == pkg_data

        # Second call should use cache (not re-download)
        with patch("prove.registry.urlopen", side_effect=Exception("should not be called")):
            result2 = download_package("json-utils", "0.3.0", "https://example.com")
            assert result2 == result


def test_download_package_failure():
    from urllib.error import URLError

    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch("prove.registry.cache_dir", return_value=Path(tmpdir)),
        patch("prove.registry.urlopen", side_effect=URLError("nope")),
    ):
        result = download_package("bad-pkg", "1.0.0", "https://example.com")
        assert result is None


def test_checksum():
    with tempfile.NamedTemporaryFile(suffix=".prvpkg", delete=False) as f:
        f.write(b"test data for checksum")
        f.flush()
        path = Path(f.name)

    try:
        checksum = compute_checksum(path)
        assert checksum.startswith("sha256:")
        assert len(checksum) > 10

        assert verify_checksum(path, checksum) is True
        assert verify_checksum(path, "sha256:wrong") is False
    finally:
        path.unlink()
