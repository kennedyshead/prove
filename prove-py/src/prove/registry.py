"""HTTP client for the Prove package registry.

Follows a static HTTP layout — no API server needed, can be hosted on
any CDN, S3 bucket, or local directory.

Registry layout:
    {registry}/packages/{name}/index.json
    {registry}/packages/{name}/{version}.prvpkg
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_REGISTRY = "https://registry.prove-lang.org"


@dataclass
class RegistryVersionInfo:
    version: str
    checksum: str  # sha256:...
    prove_version: str = ""


@dataclass
class RegistryPackageInfo:
    name: str
    description: str = ""
    versions: list[RegistryVersionInfo] = field(default_factory=list)


def cache_dir() -> Path:
    """Return the package cache directory (~/.prove/cache/packages/)."""
    d = Path.home() / ".prove" / "cache" / "packages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_package_info(
    name: str,
    registry_url: str = DEFAULT_REGISTRY,
) -> RegistryPackageInfo | None:
    """Fetch package index from registry. Returns None on failure."""
    url = f"{registry_url}/packages/{name}/index.json"
    try:
        with urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, OSError, json.JSONDecodeError):
        return None

    versions = []
    for v in data.get("versions", []):
        versions.append(
            RegistryVersionInfo(
                version=v["version"],
                checksum=v.get("checksum", ""),
                prove_version=v.get("prove_version", ""),
            )
        )

    return RegistryPackageInfo(
        name=data.get("name", name),
        description=data.get("description", ""),
        versions=versions,
    )


def download_package(
    name: str,
    version: str,
    registry_url: str = DEFAULT_REGISTRY,
) -> Path | None:
    """Download a .prvpkg to the cache. Returns path or None on failure.

    Skips download if already cached.
    """
    pkg_dir = cache_dir() / name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    dest = pkg_dir / f"{version}.prvpkg"

    if dest.exists():
        return dest

    url = f"{registry_url}/packages/{name}/{version}.prvpkg"
    try:
        with urlopen(url, timeout=60) as resp:
            dest.write_bytes(resp.read())
    except (URLError, OSError):
        return None

    return dest


def compute_checksum(pkg_path: Path) -> str:
    """Compute SHA-256 checksum of a .prvpkg file."""
    h = hashlib.sha256()
    with open(pkg_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def verify_checksum(pkg_path: Path, expected_sha256: str) -> bool:
    """Verify that a package file matches the expected checksum."""
    actual = compute_checksum(pkg_path)
    return actual == expected_sha256


def clear_cache() -> int:
    """Remove all cached packages. Returns number of files removed."""
    d = cache_dir()
    count = 0
    if d.exists():
        for f in d.rglob("*.prvpkg"):
            f.unlink()
            count += 1
        # Clean up empty dirs
        for sub in sorted(d.iterdir(), reverse=True):
            if sub.is_dir():
                try:
                    sub.rmdir()
                except OSError:
                    pass
    return count
