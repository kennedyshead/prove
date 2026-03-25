#!/usr/bin/env python3
"""End-to-end test script that runs the Prove CLI over all examples."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

EXAMPLES_DIR = (Path(__file__).parent.parent / "examples").resolve()


def _find_prove_cli() -> list[str]:
    """Find the prove CLI: prefer the compiled proof binary, fall back to python -m prove."""
    # Check for compiled binary in proof/dist/proof
    proof_bin = (Path(__file__).parent.parent / "proof" / "dist" / "proof").resolve()
    if proof_bin.exists() and os.access(proof_bin, os.X_OK):
        return [str(proof_bin)]
    # Fall back to python -m prove (only has advanced/setup commands)
    return [sys.executable, "-m", "prove"]


PROVE_CLI = _find_prove_cli()


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


def parse_expected_diagnostics(target: Path) -> set[str]:
    """Parse 'Expected diagnostics: E101, W302' from all .prv files in target."""
    expected_diags = set()

    files_to_check = []
    if target.is_dir():
        files_to_check = list(target.rglob("*.prv"))
    elif target.is_file() and target.suffix == ".prv":
        files_to_check = [target]

    for prv_file in files_to_check:
        try:
            content = prv_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                match = re.search(r"Expected diagnostics:\s*([\w,\s]+)", line)
                if match:
                    codes = match.group(1).replace(" ", "").split(",")
                    expected_diags.update(codes)
        except Exception:
            pass

    return expected_diags


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

    # prove advanced view <file>
    cmd = PROVE_CLI + ["advanced", "view", str(prv_file)]
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
        cmd = PROVE_CLI + ["advanced", "view", str(main_prv)]
        rc, stdout, stderr = run_command(cmd, cwd=project_dir)
        results["view"] = {"returncode": rc, "stdout": stdout, "stderr": stderr}

    return results, expected_failures


def _run_project(project_dir: Path) -> tuple[str, str, dict, set[str], set[str]]:
    """Worker: test one project, return (kind, name, results, expected_failures, expected_diags)."""
    name = str(project_dir.relative_to(EXAMPLES_DIR))
    results, expected_failures = test_project(project_dir)
    expected_diags = parse_expected_diagnostics(project_dir)
    return "project", name, results, expected_failures, expected_diags


def _run_single_file(prv_file: Path) -> tuple[str, str, dict, set[str], set[str]]:
    """Worker: test one file, return (kind, name, results, expected_failures, expected_diags)."""
    name = str(prv_file.relative_to(EXAMPLES_DIR))
    results, expected_failures = test_single_file(prv_file)
    expected_diags = parse_expected_diagnostics(prv_file)
    return "file", name, results, expected_failures, expected_diags


def _evaluate_results(
    name: str,
    results: dict,
    expected_failures: set[str],
    expected_diags: set[str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str, dict]]]:
    """Evaluate test results for one example.

    Returns (lines, failures) where lines are (cmd, status) pairs for display
    and failures are (name, cmd, result) tuples.
    """
    lines: list[tuple[str, str]] = []
    failures: list[tuple[str, str, dict]] = []

    for cmd, result in results.items():
        rc = result["returncode"]
        # Treat mode variants as covered by base command:
        # check_md/check_strict → check, build_debug → build
        _MODE_VARIANTS = {
            "check_md": "check",
            "check_strict": "check",
            "build_debug": "build",
        }
        base_cmd = _MODE_VARIANTS.get(cmd)
        expected = cmd in expected_failures or (
            base_cmd is not None and base_cmd in expected_failures
        )

        missing_diags = []
        if cmd == "check" and expected_diags:
            stderr = result.get("stderr", "")
            for diag in expected_diags:
                if f"[{diag}]" not in stderr:
                    missing_diags.append(diag)

        if missing_diags and not expected:
            status = f"FAIL (missing diags: {', '.join(missing_diags)})"
            failures.append((name, cmd, result))
        elif missing_diags and expected:
            status = f"EXPECTED FAIL (missing diags: {', '.join(missing_diags)})"
        elif expected and rc != 0:
            status = "EXPECTED FAIL"
        elif rc == 0:
            status = "OK"
        else:
            status = f"FAIL ({rc})"
            failures.append((name, cmd, result))

        lines.append((cmd, status))

    return lines, failures


def _find_tree_sitter() -> str | None:
    """Find tree-sitter binary."""
    import shutil

    return shutil.which("tree-sitter")


def _run_ts_parse(prv_file: Path) -> tuple[str, list[str]]:
    """Run tree-sitter parse on a .prv file.

    Returns (relative_name, error_lines).
    """
    name = str(prv_file.relative_to(EXAMPLES_DIR))
    ts = _find_tree_sitter()
    if ts is None:
        return name, ["tree-sitter not found"]
    try:
        result = subprocess.run(
            [ts, "parse", str(prv_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        errors = [
            line.strip()
            for line in output.splitlines()
            if "ERROR" in line or "MISSING" in line
        ]
        return name, errors
    except Exception as e:
        return name, [str(e)]


def run_tree_sitter_tests(
    prv_files: list[Path], jobs: int
) -> tuple[int, int, list[tuple[str, list[str]]]]:
    """Run tree-sitter parse on all .prv files.

    Returns (total, failed, failures).
    """
    if not _find_tree_sitter():
        print("  tree-sitter not found, skipping parse tests")
        return 0, 0, []

    failures: list[tuple[str, list[str]]] = []
    completed = 0
    total = len(prv_files)

    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_run_ts_parse, f): f for f in prv_files}
        for future in as_completed(futures):
            completed += 1
            name, errors = future.result()
            if errors:
                failures.append((name, errors))

    return total, len(failures), failures


def main() -> int:
    """Run e2e tests on all examples.

    Usage:
        python scripts/test_e2e.py                  # run all examples
        python scripts/test_e2e.py hello_world       # filter by name substring
        python scripts/test_e2e.py comptime_demo     # run a single project
        python scripts/test_e2e.py -j1               # run sequentially
        python scripts/test_e2e.py -j8               # run with 8 workers
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run e2e tests on Prove examples")
    parser.add_argument(
        "filter", nargs="?", default=None, help="Filter examples by name substring"
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count() or 4,
        help="Number of parallel workers (default: cpu count, -j1 for sequential)",
    )
    args = parser.parse_args()

    jobs: int = max(1, args.jobs)

    print(f"Testing examples in: {EXAMPLES_DIR}")
    if args.filter:
        print(f"Filter: {args.filter}")
    print(f"Workers: {jobs}")
    print("-" * 60)

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

    # Apply filter if specified
    if args.filter:
        projects = [
            p for p in projects if args.filter in str(p.relative_to(EXAMPLES_DIR))
        ]
        single_files = [
            f for f in single_files if args.filter in str(f.relative_to(EXAMPLES_DIR))
        ]

    total = len(projects) + len(single_files)
    if total == 0:
        print("No examples found.")
        return 0

    # Collect all results: name -> (kind, results, expected_failures, expected_diags)
    collected: dict[str, tuple[str, dict, set[str], set[str]]] = {}
    errors: dict[str, str] = {}
    completed = 0

    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {}
        for p in projects:
            futures[pool.submit(_run_project, p)] = p
        for f in single_files:
            futures[pool.submit(_run_single_file, f)] = f

        for future in as_completed(futures):
            completed += 1
            try:
                kind, name, results, expected_failures, expected_diags = future.result()
                collected[name] = (kind, results, expected_failures, expected_diags)
                print(f"  [{completed}/{total}] {name}")
            except Exception as e:
                target = futures[future]
                name = str(target.relative_to(EXAMPLES_DIR))
                errors[name] = str(e)
                print(f"  [{completed}/{total}] {name} ERROR: {e}")
                traceback.print_exc()

    # Print per-example details sorted by name
    all_failures: list[tuple[str, str, dict]] = []

    for name in sorted(collected):
        kind, results, expected_failures, expected_diags = collected[name]
        label = "project" if kind == "project" else "single file"
        print(f"\nTesting {label}: {name}")

        lines, failures = _evaluate_results(
            name, results, expected_failures, expected_diags
        )
        for cmd, status in lines:
            print(f"  prove {cmd}: {status}")
        all_failures.extend(failures)

    for name in sorted(errors):
        print(f"\n{name}: ERROR - {errors[name]}")

    # Print all failures
    if all_failures:
        print("\n" + "=" * 60)
        print(f"ALL FAILURES ({len(all_failures)}):")
        print("=" * 60)
        for fname, fcmd, fresult in all_failures:
            print(f"\n--- {fname} :: prove {fcmd} ---")
            stderr = fresult.get("stderr", "")
            # Print first 5 lines of stderr
            for line in stderr.strip().splitlines()[:5]:
                print(f"  {line}")
        print("=" * 60)

    # ── Tree-sitter parse tests ────────────────────────────────
    print("\n" + "=" * 60)
    print("TREE-SITTER PARSE TESTS")
    print("=" * 60)

    all_prv = sorted(EXAMPLES_DIR.rglob("*.prv"))
    ts_total, ts_failed, ts_failures = run_tree_sitter_tests(all_prv, jobs)

    if ts_failures:
        for ts_name, ts_errors in sorted(ts_failures):
            print(f"\n  FAIL: {ts_name}")
            for err in ts_errors[:3]:
                print(f"    {err}")
    if ts_total > 0:
        print(
            f"\nTree-sitter: {ts_total} files, {ts_total - ts_failed} clean, {ts_failed} with errors"
        )

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_expected_fail = 0

    _MODE_VARIANTS = {
        "check_md": "check",
        "check_strict": "check",
        "build_debug": "build",
    }
    for name in collected:
        _, results, expected_failures, _ = collected[name]
        for cmd, result in results.items():
            total_tests += 1
            if result["returncode"] == 0:
                total_passed += 1
            else:
                base_cmd = _MODE_VARIANTS.get(cmd)
                is_expected = cmd in expected_failures or (
                    base_cmd is not None and base_cmd in expected_failures
                )
                if is_expected:
                    total_expected_fail += 1
                else:
                    total_failed += 1

    total_failed += len(errors) + ts_failed

    print(
        f"Total: {total_tests + ts_total} tests, {total_passed + ts_total - ts_failed} passed, {total_expected_fail} expected failures, {total_failed} unexpected failures"
    )

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
