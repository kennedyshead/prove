#!/usr/bin/env python3
"""End-to-end test script that runs the Prove CLI over all examples."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

PROVE_CLI = [sys.executable, "-m", "prove"]


def parse_intent_directives(prv_file: Path) -> set[str]:
    """Parse 'narrative:' docstrings from a .prv file to get expected failures.

    Looks for lines like:
      narrative: Some description.
      Expected to fail: check, build, view.

    Returns a set of command names that are expected to fail.
    """
    expected_failures: set[str] = set()

    if not prv_file.exists():
        return expected_failures

    try:
        content = prv_file.read_text()
    except Exception:
        return expected_failures

    for line in content.splitlines():
        line = line.strip()
        match = re.search(r"Expected to fail:\s*([\w,\s]+)", line)
        if match:
            commands = match.group(1).replace(" ", "").split(",")
            expected_failures.update(commands)

    return expected_failures


def get_expected_failures(target: Path) -> set[str]:
    """Get expected failures for a project or single file."""
    expected = set()

    if target.is_dir():
        main_prv = target / "src" / "main.prv"
        if not main_prv.exists():
            main_prv = target / "main.prv"
        expected.update(parse_intent_directives(main_prv))
    elif target.is_file() and target.suffix == ".prv":
        expected.update(parse_intent_directives(target))

    return expected


def run_command(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "command timed out"
    except Exception as e:
        return -1, "", str(e)


def test_single_file(prv_file: Path) -> tuple[dict, set[str]]:
    """Test a single .prv file with CLI commands.

    Returns (results, expected_failures).
    """
    results = {}
    expected_failures = get_expected_failures(prv_file)
    parent = prv_file.parent

    # prove check <file>
    cmd = PROVE_CLI + ["check", str(prv_file)]
    rc, stdout, stderr = run_command(cmd, cwd=parent)
    results["check"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove check --strict <file>
    cmd = PROVE_CLI + ["check", "--strict", str(prv_file)]
    rc, stdout, stderr = run_command(cmd, cwd=parent)
    results["check_strict"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove format --status <file>
    cmd = PROVE_CLI + ["format", "--status", str(prv_file)]
    rc, stdout, stderr = run_command(cmd, cwd=parent)
    results["format_check"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove view <file>
    cmd = PROVE_CLI + ["view", str(prv_file)]
    rc, stdout, stderr = run_command(cmd, cwd=parent)
    results["view"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    return results, expected_failures


def test_project(project_dir: Path) -> tuple[dict, set[str]]:
    """Test a project directory with prove.toml.

    Returns (results, expected_failures).
    """
    results = {}
    expected_failures = get_expected_failures(project_dir)

    # prove check <project>
    cmd = PROVE_CLI + ["check", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir)
    results["check"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove check --md <project>
    cmd = PROVE_CLI + ["check", "--md", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir)
    results["check_md"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove check --strict <project>
    cmd = PROVE_CLI + ["check", "--strict", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir)
    results["check_strict"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove build <project>
    cmd = PROVE_CLI + ["build", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir, timeout=180)
    results["build"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove build --debug <project>
    cmd = PROVE_CLI + ["build", "--debug", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir, timeout=180)
    results["build_debug"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove build --no-mutate <project> (build without mutation testing, only if build passes)
    if results["build"]["returncode"] == 0:
        cmd = PROVE_CLI + ["build", "--no-mutate", str(project_dir)]
        rc, stdout, stderr = run_command(cmd, cwd=project_dir, timeout=300)
        results["build_no_mutate"] = {
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
        }

    # prove test <project> (only if test passes check)
    if results["check"]["returncode"] == 0:
        cmd = PROVE_CLI + ["test", str(project_dir)]
        rc, stdout, stderr = run_command(cmd, cwd=project_dir, timeout=180)
        results["test"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

        # prove test --property-rounds <project>
        cmd = PROVE_CLI + ["test", "--property-rounds", "10", str(project_dir)]
        rc, stdout, stderr = run_command(cmd, cwd=project_dir, timeout=180)
        results["test_property_rounds"] = {
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
        }

    # prove format --status <project>
    cmd = PROVE_CLI + ["format", "--status", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir)
    results["format_check"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # prove format --status --md <project>
    cmd = PROVE_CLI + ["format", "--status", "--md", str(project_dir)]
    rc, stdout, stderr = run_command(cmd, cwd=project_dir)
    results["format_check_md"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    # Find main.prv for view command
    main_prv = project_dir / "src" / "main.prv"
    if not main_prv.exists():
        main_prv = project_dir / "main.prv"

    if main_prv.exists():
        cmd = PROVE_CLI + ["view", str(main_prv)]
        rc, stdout, stderr = run_command(cmd, cwd=project_dir)
        results["view"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    return results, expected_failures


def main() -> int:
    """Run e2e tests on all examples."""
    print(f"Testing examples in: {EXAMPLES_DIR}")
    print("-" * 60)

    failed_example: Path | None = None
    failed_command: str = ""
    failed_result: dict | None = None
    failed_name: str = ""
    all_results: dict[str, dict] = {}

    # Find all prove.toml files (projects)
    project_dirs = sorted(EXAMPLES_DIR.rglob("prove.toml"))
    projects = [f.parent for f in project_dirs]

    # Find single .prv files that are not in projects
    all_prv_files = sorted(EXAMPLES_DIR.rglob("*.prv"))
    project_prv_files = set()
    for proj in projects:
        for prv in proj.rglob("*.prv"):
            project_prv_files.add(prv)

    single_files = [f for f in all_prv_files if f not in project_prv_files]

    # Test projects
    for project_dir in projects:
        name = project_dir.relative_to(EXAMPLES_DIR)
        print(f"\nTesting project: {name}")
        try:
            results, expected_failures = test_project(project_dir)
            all_results[str(name)] = results

            for cmd, result in results.items():
                rc = result["returncode"]
                expected = cmd in expected_failures
                if expected and rc != 0:
                    status = "EXPECTED FAIL"
                elif rc == 0:
                    status = "OK"
                else:
                    status = f"FAIL ({rc})"
                    failed_example = project_dir
                    failed_command = cmd
                    failed_result = result
                    failed_name = str(name)
                print(f"  prove {cmd}: {status}")

            if failed_example:
                print("\n" + "=" * 60)
                print(f"FAILED: {failed_name}")
                print(f"Command: prove {failed_command}")
                print(f"File: {failed_example}")
                print("-" * 60)
                print("STDOUT:")
                print(failed_result["stdout"])
                print("STDERR:")
                print(failed_result["stderr"])
                print("=" * 60)
                return 1

        except Exception as e:
            print(f"  ERROR: {e}")
            print("\n" + "=" * 60)
            print(f"ERROR in: {name}")
            print(f"File: {project_dir}")
            print("Traceback:")
            traceback.print_exc()
            print("=" * 60)
            return 1

    # Test single files
    for prv_file in single_files:
        name = prv_file.relative_to(EXAMPLES_DIR)
        print(f"\nTesting single file: {name}")
        try:
            results, expected_failures = test_single_file(prv_file)
            all_results[str(name)] = results

            for cmd, result in results.items():
                rc = result["returncode"]
                expected = cmd in expected_failures
                if expected and rc != 0:
                    status = "EXPECTED FAIL"
                elif rc == 0:
                    status = "OK"
                else:
                    status = f"FAIL ({rc})"
                    failed_example = prv_file
                    failed_command = cmd
                    failed_result = result
                    failed_name = str(name)
                print(f"  prove {cmd}: {status}")

            if failed_example:
                print("\n" + "=" * 60)
                print(f"FAILED: {failed_name}")
                print(f"Command: prove {failed_command}")
                print(f"File: {failed_example}")
                print("-" * 60)
                print("STDOUT:")
                print(failed_result["stdout"])
                print("STDERR:")
                print(failed_result["stderr"])
                print("=" * 60)
                return 1

        except Exception as e:
            print(f"  ERROR: {e}")
            print("\n" + "=" * 60)
            print(f"ERROR in: {name}")
            print(f"File: {prv_file}")
            print("Traceback:")
            traceback.print_exc()
            print("=" * 60)
            return 1

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_expected_fail = 0

    # Re-parse expected failures for summary
    expected_map: dict[str, set[str]] = {}
    for proj in projects:
        name = str(proj.relative_to(EXAMPLES_DIR))
        expected_map[name] = get_expected_failures(proj)
    for prv_file in single_files:
        name = str(prv_file.relative_to(EXAMPLES_DIR))
        expected_map[name] = get_expected_failures(prv_file)

    for name, results in all_results.items():
        if "error" in results:
            print(f"  {name}: ERROR")
            total_failed += 1
            continue

        expected = expected_map.get(name, set())
        for cmd, result in results.items():
            total_tests += 1
            if result["returncode"] == 0:
                total_passed += 1
            elif cmd in expected:
                total_expected_fail += 1
            else:
                total_failed += 1

    print(
        f"Total: {total_tests} tests, {total_passed} passed, {total_expected_fail} expected failures, {total_failed} unexpected failures"
    )

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
