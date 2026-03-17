"""Shared build command logic.

Called by both the click CLI (cli.py) and the proof binary (via PyRun_SimpleString
in build.py). Keep this file free of click imports so it remains embeddable.
"""

from __future__ import annotations

import sys
from pathlib import Path


def mutate(project_dir: Path):
    print("running mutation testing...")
    from prove.checker import Checker
    from prove.errors import CompileError
    from prove.lexer import Lexer
    from prove.module_resolver import build_module_registry
    from prove.mutator import run_mutation_tests
    from prove.parser import Parser

    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir
    from prove.config import discover_prv_files

    prv_files = discover_prv_files(src_dir)

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None
    modules = []
    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)
        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
            checker = Checker(local_modules=local_modules)
            symbols = checker.check(module)
            if not checker.has_errors():
                modules.append((module, symbols))
        except CompileError:
            continue

    mutation_result = run_mutation_tests(
        project_dir,
        modules,
        max_mutants=50,
        property_rounds=100,
    )

    from prove.mutator import get_survivors_path, save_survivors

    get_survivors_path(project_dir).unlink(missing_ok=True)
    save_survivors(project_dir, mutation_result)

    if mutation_result.total_mutants == 0:
        print("no mutants generated")
    else:
        print(
            f"mutation score: {mutation_result.mutation_score:.1%} "
            f"({mutation_result.killed_mutants}/{mutation_result.total_mutants} killed)"
        )
        if mutation_result.survivors:
            print(f"\nsurviving mutants ({len(mutation_result.survivors)}):")
            for s in mutation_result.survivors:
                print(f"  {s['id']}: {s['description']} at {s['location']}")
                print("    suggestion: add contract to kill this mutant")


def run_build(path: str = ".", *, debug: bool | None = None, no_mutate: bool = False) -> int:
    """Compile a Prove project. Returns 0 on success, 1 on failure."""

    from prove.builder import build_project
    from prove.config import find_config, load_config
    from prove.errors import DiagnosticRenderer

    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        print(f"building {config.package.name}...")
        project_dir = config_path.parent

        # CLI flags override config values
        effective_debug = debug if debug is not None else config.build.debug
        effective_mutate = not no_mutate and config.build.mutate

        renderer = DiagnosticRenderer(color=True)
        result = build_project(project_dir, config, debug=effective_debug)

        for diag in result.diagnostics:
            sys.stderr.write(renderer.render(diag) + "\n")

        if not result.ok:
            if result.c_error:
                sys.stderr.write(f"error: {result.c_error}\n")
            return 1

        if effective_mutate:
            mutate(project_dir)

        print(f"built {config.package.name} -> {result.binary}")
        return 0

    except FileNotFoundError:
        sys.stderr.write("error: no prove.toml found\n")
        return 1
