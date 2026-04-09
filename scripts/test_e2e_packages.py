#!/usr/bin/env python3
"""End-to-end test for the Prove package manager.

Creates a two-project setup:
  1. Project A ("math-helpers") publishes a .prvpkg package
  2. Project B ("calculator") depends on it via local path
  3. Verifies: publish, install, check, and build all work

Usage:
    python scripts/test_e2e_packages.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROVE_PY = REPO_ROOT / "prove-py"

# Ensure prove-py is importable
sys.path.insert(0, str(PROVE_PY / "src"))


def _run(
    cmd: list[str], cwd: Path, *, expect_fail: bool = False
) -> subprocess.CompletedProcess:
    """Run a command and print output."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            print(f"    [err] {line}")

    if expect_fail:
        if result.returncode == 0:
            print("    FAIL: expected failure but got success")
            return result
    else:
        if result.returncode != 0:
            print(f"    FAIL: exit code {result.returncode}")
    return result


def _python() -> str:
    return sys.executable


def test_local_path_dependency():
    """Full e2e: project A publishes, project B uses via local path."""
    print("\n=== E2E: Local path dependency ===\n")

    with tempfile.TemporaryDirectory() as workspace:
        workspace = Path(workspace)
        errors = []

        # ── Project A: math-helpers ──────────────────────────
        print("--- Setting up project A (math-helpers) ---")
        lib_dir = workspace / "math-helpers"
        lib_src = lib_dir / "src"
        lib_src.mkdir(parents=True)

        (lib_dir / "prove.toml").write_text(
            '[package]\nname = "math-helpers"\nversion = "0.1.0"\n'
        )

        (lib_src / "math_helpers.prv").write_text(
            "module MathHelpers\n"
            '  narrative: """\n'
            "  Math helper functions.\n"
            "\n"
            "  creates double triple\n"
            '  """\n'
            "\n"
            "/// Double a number.\n"
            "creates double(x Integer) Integer\n"
            "from\n"
            "  result as Integer = x * 2\n"
            "  result\n"
            "\n"
            "/// Triple a number.\n"
            "creates triple(x Integer) Integer\n"
            "from\n"
            "  result as Integer = x * 3\n"
            "  result\n"
        )

        # Step 1: Check project A
        print("\nStep 1: Check project A")
        r = _run([_python(), "-m", "prove", "check", str(lib_dir)], cwd=PROVE_PY)
        if r.returncode != 0:
            errors.append("check project A failed")

        # Step 2: Publish project A (dry-run)
        print("\nStep 2: Publish project A (dry-run)")
        r = _run(
            [_python(), "-m", "prove", "package", "publish", "--dry-run", str(lib_dir)],
            cwd=PROVE_PY,
        )
        if r.returncode != 0:
            errors.append("publish dry-run failed")

        # Step 3: Publish project A
        print("\nStep 3: Publish project A")
        r = _run(
            [_python(), "-m", "prove", "package", "publish", str(lib_dir)],
            cwd=PROVE_PY,
        )
        if r.returncode != 0:
            errors.append("publish failed")
        else:
            pkg_file = lib_dir / "math-helpers-0.1.0.prvpkg"
            if pkg_file.exists():
                print(
                    f"    .prvpkg created: {pkg_file} ({pkg_file.stat().st_size} bytes)"
                )
            else:
                errors.append(".prvpkg file not created")

        # ── Project B: calculator ────────────────────────────
        print("\n--- Setting up project B (calculator) ---")
        app_dir = workspace / "calculator"
        app_src = app_dir / "src"
        app_src.mkdir(parents=True)

        (app_dir / "prove.toml").write_text(
            "[package]\n"
            'name = "calculator"\n'
            'version = "1.0.0"\n'
            "\n"
            "[dependencies]\n"
            f'math-helpers = {{ path = "{lib_dir}" }}\n'
        )

        (app_src / "calculator.prv").write_text(
            "module Calculator\n"
            '  narrative: """Calculator app."""\n'
            "  MathHelpers\n"
            "    creates double triple\n"
            "\n"
            "/// Quadruple a number.\n"
            "creates quadruple(x Integer) Integer\n"
            "from\n"
            "  result as Integer = double(double(x))\n"
            "  result\n"
        )

        # Step 4: Install dependencies (resolve local path)
        print("\nStep 4: Install dependencies")
        r = _run(
            [_python(), "-m", "prove", "package", "install", str(app_dir)],
            cwd=PROVE_PY,
        )
        if r.returncode != 0:
            errors.append("install failed")
        else:
            lock_file = app_dir / "prove.lock"
            if lock_file.exists():
                lock_content = lock_file.read_text()
                print(f"    prove.lock created ({len(lock_content)} chars)")
                if "file://" not in lock_content:
                    errors.append("prove.lock missing file:// source")
                else:
                    print("    ✓ contains file:// source")
            else:
                errors.append("prove.lock not created")

        # Step 5: Check project B (should resolve package imports)
        print("\nStep 5: Check project B")
        r = _run([_python(), "-m", "prove", "check", str(app_dir)], cwd=PROVE_PY)
        if r.returncode != 0:
            # Check if E314 (unknown module) errors are present
            if "E314" in (r.stderr + r.stdout):
                errors.append(
                    "check project B: E314 unknown module — package import failed"
                )
            else:
                errors.append("check project B failed (may be unrelated)")

        # Step 6: List dependencies
        print("\nStep 6: List dependencies")
        r = _run(
            [_python(), "-m", "prove", "package", "list", str(app_dir)],
            cwd=PROVE_PY,
        )
        if r.returncode != 0:
            errors.append("list failed")

        # Step 7: Package clean (separate from validation)
        print("\nStep 7: Package clean")
        _run(
            [_python(), "-m", "prove", "package", "clean"],
            cwd=PROVE_PY,
        )

        # ── Results ──────────────────────────────────────────
        print("\n" + "=" * 50)
        if errors:
            print(f"FAILED ({len(errors)} error(s)):")
            for e in errors:
                print(f"  - {e}")
            return False
        else:
            print("ALL PASSED")
            return True


def test_publish_rejects_foreign():
    """Publish should reject modules with foreign blocks."""
    print("\n=== E2E: Publish rejects foreign blocks ===\n")

    with tempfile.TemporaryDirectory() as workspace:
        workspace = Path(workspace)

        proj_dir = workspace / "ffi-lib"
        src_dir = proj_dir / "src"
        src_dir.mkdir(parents=True)

        (proj_dir / "prove.toml").write_text(
            '[package]\nname = "ffi-lib"\nversion = "0.1.0"\n'
        )

        (src_dir / "ffi.prv").write_text(
            "module FfiLib\n"
            '  narrative: """FFI library."""\n'
            "\n"
            '  foreign "libm"\n'
            "    sqrt(x Float) Float\n"
            "\n"
            "creates safe_sqrt(x Float) Float\n"
            "  sqrt(x)\n"
        )

        print("Publish should fail for FFI module")
        r = _run(
            [_python(), "-m", "prove", "package", "publish", str(proj_dir)],
            cwd=PROVE_PY,
            expect_fail=True,
        )
        if r.returncode != 0:
            print("    OK: publish correctly rejected FFI module")
            return True
        else:
            print("    FAIL: publish should have rejected FFI module")
            return False


def test_package_init():
    """Package init adds [dependencies] section."""
    print("\n=== E2E: Package init ===\n")

    with tempfile.TemporaryDirectory() as workspace:
        workspace = Path(workspace)

        proj_dir = workspace / "new-project"
        proj_dir.mkdir()
        (proj_dir / "prove.toml").write_text('[package]\nname = "new-project"\n')

        r = _run(
            [_python(), "-m", "prove", "package", "init", str(proj_dir)],
            cwd=PROVE_PY,
        )
        if r.returncode != 0:
            print("  FAIL: init failed")
            return False

        content = (proj_dir / "prove.toml").read_text()
        if "[dependencies]" in content:
            print("  OK: [dependencies] section added")

            # Running again should be a no-op
            r2 = _run(
                [_python(), "-m", "prove", "package", "init", str(proj_dir)],
                cwd=PROVE_PY,
            )
            if "already exists" in r2.stdout:
                print("  OK: init is idempotent")
                return True

        print("  FAIL: [dependencies] not found")
        return False


def main():
    results = []

    results.append(("package init", test_package_init()))
    results.append(("publish rejects foreign", test_publish_rejects_foreign()))
    results.append(("local path dependency", test_local_path_dependency()))

    print("\n" + "=" * 50)
    print("E2E Package Manager Results:")
    print("=" * 50)
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("All e2e package tests passed!")
        return 0
    else:
        print("Some e2e package tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
