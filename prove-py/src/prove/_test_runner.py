"""Test command logic — click-free.

Called by both the click CLI (cli.py) and the proof binary (via PyRun_SimpleString).
Keep this file free of click imports so it remains embeddable.
"""

from __future__ import annotations

import sys
from pathlib import Path


def run_test(path: str = ".", *, property_rounds: int | None = None) -> int:
    """Run contract tests for a Prove project. Returns 0 on success, 1 on failure."""
    from prove.checker import Checker
    from prove.config import discover_prv_files, find_config, load_config
    from prove.errors import CompileError, DiagnosticRenderer, Severity
    from prove.parse import parse
    from prove.testing import run_tests

    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        rounds = property_rounds or config.test.property_rounds
        project_dir = config_path.parent
        print(f"testing {config.package.name} (property rounds: {rounds})...")

        src_dir = project_dir / "src"
        if not src_dir.is_dir():
            src_dir = project_dir

        prv_files = discover_prv_files(src_dir)
        if not prv_files:
            sys.stderr.write("warning: no .prv files found\n")
            return 0

        from prove.module_resolver import build_module_registry

        local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

        renderer = DiagnosticRenderer(color=True)
        modules = []
        had_errors = False

        for prv_file in prv_files:
            source = prv_file.read_text()
            filename = str(prv_file)
            try:
                module = parse(source, filename)
            except CompileError as e:
                had_errors = True
                for diag in e.diagnostics:
                    sys.stderr.write(renderer.render(diag) + "\n")
                continue

            checker = Checker(local_modules=local_modules)
            symbols = checker.check(module)
            for diag in checker.diagnostics:
                sys.stderr.write(renderer.render(diag) + "\n")
                if diag.severity == Severity.ERROR:
                    had_errors = True

            if not checker.has_errors():
                modules.append((module, symbols))

        if had_errors:
            return 1

        result = run_tests(project_dir, modules, property_rounds=rounds)

        if result.output:
            print(result.output)

        if result.c_error:
            sys.stderr.write(f"error: {result.c_error}\n")
            return 1

        if result.test_details:
            print("\nTested functions:")
            type_labels = {
                "property": "property-based",
                "near_miss": "near-miss case",
                "boundary": "boundary values",
                "believe": "adversarial",
            }
            for tc in result.test_details:
                type_label = type_labels.get(tc.test_type, tc.test_type)
                verb_display = f"[{tc.verb}] " if tc.verb else ""
                print(f"  \u2022 {verb_display}{tc.function_name} ({type_label})")
            print(f"  rounds per test: {rounds}")
            print("")

        if result.ok:
            print(f"tested {config.package.name} — {result.tests_passed}/{result.tests_run} passed")
            return 0
        else:
            sys.stderr.write(
                f"tested {config.package.name} — "
                f"{result.tests_passed}/{result.tests_run} passed, "
                f"{result.tests_failed} failed\n"
            )
            return 1

    except FileNotFoundError:
        sys.stderr.write("error: no prove.toml found\n")
        return 1
