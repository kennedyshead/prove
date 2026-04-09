"""Prove compiler CLI.

Root commands are development tools (compiler, export, generate, index, intent,
setup, setup-nlp, view).  build/check/format/test are available as Python
fallbacks when optimize.enabled=false (no compiled ``proof`` binary needed).
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from prove import __version__
from prove.errors import CompileError, DiagnosticRenderer
from prove.parse import parse


def _apply_nlp_override(enabled: bool) -> None:
    """Force NLP backend on or off for the current process."""
    import prove.nlp as nlp_mod

    if enabled:
        if not nlp_mod.has_nlp_backend():
            click.echo("error: --nlp requested but no NLP backend available", err=True)
            click.echo("  run: pip install 'prove[nlp]'", err=True)
            raise SystemExit(1)
    else:
        # Disable by marking both backends as checked but unavailable
        nlp_mod._spacy_checked = True
        nlp_mod._spacy_available = False
        nlp_mod._nlp_model = None
        nlp_mod._wordnet_checked = True
        nlp_mod._wordnet_available = False


@click.group()
@click.version_option(__version__, prog_name="prove")
def main() -> None:
    """The Prove programming language compiler."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--debug", is_flag=True, help="Debug build (no optimizations, keeps .c files).")
@click.option("--no-mutate", is_flag=True, help="Skip mutation testing.")
def build(path: str, debug: bool, no_mutate: bool) -> None:
    """Compile project to native binary (Python fallback)."""
    from prove.builder import build_project
    from prove.config import load_config
    from prove.errors import DiagnosticRenderer

    project_dir = Path(path).resolve()
    config = load_config(project_dir / "prove.toml")
    result = build_project(project_dir, config, debug=debug)

    renderer = DiagnosticRenderer(color=True)
    for diag in result.diagnostics:
        click.echo(renderer.render(diag), err=True)

    if result.ok:
        click.echo(f"built {result.binary}")
    else:
        if result.c_error:
            click.echo(result.c_error, err=True)
        raise SystemExit(1)


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--md", is_flag=True, help="Markdown output.")
@click.option("--strict", is_flag=True, help="Treat warnings as errors.")
@click.option("--no-intent", is_flag=True, help="Skip intent coverage check.")
def check(path: str, md: bool, strict: bool, no_intent: bool) -> None:
    """Type-check and lint project (Python fallback)."""
    from prove.checker import Checker
    from prove.errors import DiagnosticRenderer
    from prove.module_resolver import build_module_registry

    project_dir = Path(path).resolve()
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.glob("*.prv"))
    if not prv_files:
        click.echo("no .prv files found", err=True)
        raise SystemExit(1)

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    # Load installed packages from lockfile
    package_modules = None
    lockfile_path = project_dir / "prove.lock"
    if lockfile_path.exists():
        from prove.lockfile import read_lockfile
        from prove.package_loader import load_installed_packages

        lockfile = read_lockfile(lockfile_path)
        if lockfile:
            package_modules = load_installed_packages(project_dir, lockfile)

    renderer = DiagnosticRenderer(color=not md)
    has_errors = False
    for prv_file in prv_files:
        source = prv_file.read_text()
        try:
            module = parse(source, str(prv_file))
        except CompileError as e:
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            has_errors = True
            continue

        checker = Checker(local_modules=local_modules, package_modules=package_modules)
        checker.check(module)
        for diag in checker.diagnostics:
            click.echo(renderer.render(diag), err=True)
        if checker.has_errors():
            has_errors = True

    if has_errors:
        raise SystemExit(1)
    click.echo(f"checked {len(prv_files)} file(s) — no errors")


@main.command("format")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--status", is_flag=True, help="Check only, don't rewrite.")
@click.option("--md", is_flag=True, help="Markdown output.")
def format_cmd(path: str, status: bool, md: bool) -> None:
    """Format .prv source files (Python fallback)."""
    from prove.checker import Checker
    from prove.formatter import ProveFormatter
    from prove.module_resolver import build_module_registry

    project_dir = Path(path).resolve()
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.glob("*.prv"))
    if not prv_files:
        click.echo("no .prv files found", err=True)
        raise SystemExit(1)

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    changed = 0
    for prv_file in prv_files:
        source = prv_file.read_text()
        try:
            module = parse(source, str(prv_file))
        except CompileError:
            continue

        # Skip files where tree-sitter has parse errors — formatting
        # a broken parse tree produces mangled output.
        from prove.parse import has_parse_errors

        if has_parse_errors(source):
            continue

        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)
        if checker.has_errors():
            continue
        formatter = ProveFormatter(symbols=symbols, diagnostics=checker.diagnostics)
        formatted = formatter.format(module)

        if formatted != source:
            changed += 1
            if status:
                click.echo(f"  needs format: {prv_file}")
            else:
                prv_file.write_text(formatted)
                click.echo(f"  formatted: {prv_file}")

    if status and changed:
        raise SystemExit(1)
    click.echo(f"{len(prv_files)} file(s) checked, {changed} formatted")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--property-rounds", type=int, default=1000, help="Property test rounds.")
def test(path: str, property_rounds: int) -> None:
    """Run contract tests for a Prove project (Python fallback)."""
    from prove.checker import Checker
    from prove.module_resolver import build_module_registry
    from prove.testing import TestGenerator

    project_dir = Path(path).resolve()
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.glob("*.prv"))
    if not prv_files:
        click.echo("no .prv files found", err=True)
        raise SystemExit(1)

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    total_tests = 0
    for prv_file in prv_files:
        source = prv_file.read_text()
        try:
            module = parse(source, str(prv_file))
        except CompileError as e:
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            raise SystemExit(1)

        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)
        gen = TestGenerator(module, symbols, property_rounds=property_rounds)
        suite = gen.generate()
        total_tests += len(suite.cases)

        if suite.cases:
            test_c = gen.emit_test_c(suite)
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".c", mode="w", delete=False) as f:
                f.write(test_c)
                test_src = f.name

            test_bin = test_src.replace(".c", "")
            runtime_dir = Path(__file__).parent / "runtime"
            include_flags = ["-I", str(runtime_dir)]

            # Link runtime .c files needed by the test (skip gui/graphics)
            from prove.c_runtime import _CORE_FILES

            skip = {"prove_gui", "prove_graphic", "prove_prove"}
            core_files = [
                str(runtime_dir / f"{base}.c")
                for base in _CORE_FILES
                if base not in skip and (runtime_dir / f"{base}.c").exists()
            ]
            # Also link non-core runtime files referenced by the test
            for c_file in sorted(runtime_dir.glob("prove_*.c")):
                base = c_file.stem
                if base not in skip and str(c_file) not in core_files:
                    core_files.append(str(c_file))

            result = subprocess.run(
                ["cc", "-o", test_bin, test_src, *core_files, *include_flags, "-lm"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                click.echo(f"test compilation failed: {result.stderr}", err=True)
                raise SystemExit(1)

            result = subprocess.run([test_bin], capture_output=True, text=True, timeout=60)
            click.echo(result.stdout, nl=False)
            if result.returncode != 0:
                click.echo(result.stderr, err=True)
                raise SystemExit(1)

            # Cleanup
            import os

            os.unlink(test_src)
            os.unlink(test_bin)

    click.echo(f"{total_tests} test(s) passed")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def index(path: str) -> None:
    """Rebuild the .prove/cache ML completion index."""
    from prove.config import find_config
    from prove.lsp import _ProjectIndexer

    config_path = find_config(Path(path))
    project_dir = config_path.parent
    click.echo("indexing...")
    indexer = _ProjectIndexer(project_dir)
    indexer.index_all_files()
    click.echo(f"indexed {len(indexer._file_ngrams)} files -> {project_dir / '.prove' / 'cache'}")


def _generate_from_intent(target: Path, dry_run: bool) -> None:
    """Generate .prv files from a .intent project file."""
    from prove.intent_generator import generate_project
    from prove.intent_parser import parse_intent

    source = target.read_text(encoding="utf-8")
    result = parse_intent(source, str(target))

    for diag in result.diagnostics:
        severity = diag.severity.upper()
        code = f" {diag.code}" if diag.code else ""
        click.echo(f"{target}:{diag.line}: {severity}{code}: {diag.message}", err=True)

    if result.project is None:
        click.echo("error: failed to parse intent file", err=True)
        raise SystemExit(1)

    generated = generate_project(result.project, target.parent, dry_run=dry_run)
    for filename, src in generated:
        if dry_run:
            click.echo(f"--- {filename} ---")
            click.echo(src)
        else:
            click.echo(f"generated {filename}")


def _generate_from_narrative(target: Path, update: bool, dry_run: bool) -> None:
    """Generate function stubs from module narrative prose in a .prv file."""
    from prove._body_gen import generate_function_source, has_generated_marker
    from prove._nl_intent import extract_nouns, implied_verbs, pair_verbs_nouns
    from prove.ast_nodes import FunctionDef, ModuleDecl, TodoStmt

    source = target.read_text()
    filename = str(target)

    try:
        module = parse(source, filename)
    except CompileError as e:
        renderer = DiagnosticRenderer(color=True)
        for diag in e.diagnostics:
            click.echo(renderer.render(diag), err=True)
        raise SystemExit(1)

    # Find narrative
    mod_decl = None
    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            mod_decl = decl
            break

    if mod_decl is None or not mod_decl.narrative:
        click.echo("error: file has no module declaration with narrative", err=True)
        raise SystemExit(1)

    # Extract verbs and nouns from narrative
    verbs = implied_verbs(mod_decl.narrative)
    nouns = extract_nouns(mod_decl.narrative)

    if not verbs:
        click.echo("warning: no verbs implied by narrative", err=True)
        return
    if not nouns:
        click.echo("warning: no nouns extracted from narrative", err=True)
        return

    # Generate stubs
    stubs = pair_verbs_nouns(verbs, nouns)

    # Collect existing function names and check for @generated markers
    existing_fns = [d for d in module.declarations if isinstance(d, FunctionDef)]
    if mod_decl:
        existing_fns.extend(d for d in mod_decl.body if isinstance(d, FunctionDef))
    existing_names = {fn.name for fn in existing_fns}

    # On --update: also regenerate @generated functions that still have todos
    updatable_names: set[str] = set()
    if update:
        for fn in existing_fns:
            if has_generated_marker(fn.doc_comment) and any(
                isinstance(s, TodoStmt) for s in fn.body
            ):
                updatable_names.add(fn.name)

    new_stubs = [s for s in stubs if s.name not in existing_names or s.name in updatable_names]

    if not new_stubs:
        click.echo("no new stubs to generate — all verb+noun pairs already have functions")
        return

    # Try body generation for each stub, fall back to simple stub
    generated_lines: list[str] = []
    body_count = 0
    stub_count = 0
    for stub in new_stubs:
        if stub.confidence < 0.3:
            continue
        generated_lines.append("")

        # Attempt body generation using stdlib knowledge base
        result = generate_function_source(
            verb=stub.verb,
            name=stub.name,
            param_names=[p[0] for p in stub.params],
            param_types=[p[1] for p in stub.params],
            return_type=stub.return_type,
            declaration_text=f"{stub.verb} {stub.name}",
        )
        if "todo" not in result.lower() or "chosen:" in result:
            body_count += 1
        else:
            stub_count += 1
        generated_lines.append(result)

    generated_text = "\n".join(generated_lines) + "\n"

    if dry_run:
        click.echo(generated_text)
    else:
        with open(target, "a") as f:
            f.write(generated_text)
        click.echo(f"generated {body_count} body(ies) + {stub_count} stub(s) in {target}")

    # Report completeness
    todo_count = sum(1 for fn in existing_fns if any(isinstance(s, TodoStmt) for s in fn.body))
    complete = len(existing_fns) - todo_count
    total = len(existing_fns) + len(new_stubs)
    click.echo(
        f"  {complete}/{total} functions complete ({100 * complete // total if total else 0}%)"
    )


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--update", is_flag=True, help="Regenerate @generated functions with todos.")
@click.option("--dry-run", is_flag=True, help="Preview without writing.")
@click.option("--nlp/--no-nlp", default=None, help="Force NLP backend on/off.")
def generate(path: str, update: bool, dry_run: bool, nlp: bool | None) -> None:
    """Generate function stubs from narrative or intent."""
    if nlp is not None:
        _apply_nlp_override(nlp)

    target = Path(path)
    if target.suffix == ".intent":
        _generate_from_intent(target, dry_run)
    elif target.suffix == ".prv":
        _generate_from_narrative(target, update, dry_run)
    else:
        click.echo("error: expected .prv or .intent file", err=True)
        raise SystemExit(1)


@main.command()
@click.argument("path", default="project.intent", type=click.Path(exists=True))
@click.option("--status", is_flag=True, help="Show completeness report.")
@click.option("--drift", is_flag=True, help="Show only mismatches between intent and code.")
@click.option("--generate", "gen", is_flag=True, help="Generate .prv files from intent.")
@click.option("--dry-run", is_flag=True, help="Preview generated files without writing.")
@click.option("--nlp/--no-nlp", default=None, help="Force NLP backend on/off.")
def intent(
    path: str, status: bool, drift: bool, gen: bool, dry_run: bool, nlp: bool | None
) -> None:
    """Work with .intent project declaration files."""
    if nlp is not None:
        _apply_nlp_override(nlp)

    from prove.intent_generator import check_intent_coverage, generate_project
    from prove.intent_parser import parse_intent

    target = Path(path)
    source = target.read_text(encoding="utf-8")
    result = parse_intent(source, str(target))

    # Print parse diagnostics
    for diag in result.diagnostics:
        severity = diag.severity.upper()
        code = f" {diag.code}" if diag.code else ""
        click.echo(f"{target}:{diag.line}: {severity}{code}: {diag.message}", err=True)

    if result.project is None:
        click.echo("error: failed to parse intent file", err=True)
        raise SystemExit(1)

    project = result.project
    project_dir = target.parent
    # Intent file at project root → generate into src/; inside src/ → in-place
    src_dir = project_dir / "src"
    source_dir = src_dir if src_dir.is_dir() else project_dir

    if gen:
        source_dir.mkdir(parents=True, exist_ok=True)
        generated = generate_project(project, source_dir, dry_run=dry_run)
        for filename, src in generated:
            if dry_run:
                click.echo(f"--- {filename} ---")
                click.echo(src)
            else:
                click.echo(f"generated {filename}")
        return

    # Default: show status/drift
    statuses = check_intent_coverage(project, source_dir)

    if drift:
        statuses = [s for s in statuses if s["status"] != "implemented"]

    if not statuses:
        click.echo("all intent declarations have matching implementations")
        return

    for s in statuses:
        icon = {"implemented": "+", "todo": "~", "missing": "-"}.get(s["status"], "?")
        click.echo(f"  [{icon}] {s['module']}.{s['noun']} ({s['verb']}) — {s['status']}")

    # Summary
    impl = sum(1 for s in statuses if s["status"] == "implemented")
    total = len(statuses)
    click.echo(f"\n  {impl}/{total} declarations implemented")


@main.command("export")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["treesitter", "pygments", "chroma"]),
    help="Target format (default: all).",
)
@click.option(
    "--build",
    is_flag=True,
    help="Run build steps after generating.",
)
@click.option(
    "-w",
    "--workspace",
    "workspace_path",
    type=click.Path(exists=True),
    help="Workspace root (default: parent of prove-py).",
)
def export_cmd(fmt: str | None, build: bool, workspace_path: str | None) -> None:
    """Export syntax highlighting data to companion lexer projects."""
    from prove.export import (
        build_chroma,
        build_pygments,
        build_treesitter,
        generate_chroma,
        generate_pygments,
        read_canonical_lists,
        validate_treesitter,
    )

    if workspace_path:
        workspace = Path(workspace_path)
    else:
        # Default: assume prove-py is a sibling directory under workspace
        workspace = Path(__file__).resolve().parent.parent.parent.parent

    lists = read_canonical_lists()
    targets = [fmt] if fmt else ["treesitter", "pygments", "chroma"]

    for target in targets:
        if target == "treesitter":
            click.echo("export: tree-sitter-prove (validate)")
            ok = validate_treesitter(lists, workspace)
            if ok and build:
                build_treesitter(workspace)
        elif target == "pygments":
            click.echo("export: pygments-prove")
            ok = generate_pygments(lists, workspace)
            if ok and build:
                build_pygments(workspace)
        elif target == "chroma":
            click.echo("export: chroma-lexer-prove")
            ok = generate_chroma(lists, workspace)
            if ok and build:
                build_chroma(workspace)


@main.group()
def advanced() -> None:
    """Advanced development tools."""


# ── Package manager commands ─────────────────────────────────────


@main.group()
def package() -> None:
    """Manage Prove packages."""


@package.command("init")
@click.argument("path", default=".", type=click.Path(exists=True))
def package_init(path: str) -> None:
    """Add [dependencies] section to prove.toml."""
    from prove.config import find_config

    try:
        config_path = find_config(Path(path))
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)

    text = config_path.read_text()
    if "[dependencies]" in text:
        click.echo("[dependencies] section already exists")
        return

    config_path.write_text(text.rstrip() + "\n\n[dependencies]\n")
    click.echo(f"added [dependencies] to {config_path}")


@package.command("add")
@click.argument("name")
@click.argument("version", default="")
@click.option(
    "--path",
    "dep_path",
    default=None,
    type=click.Path(exists=True),
    help="Local path to package project directory.",
)
def package_add(name: str, version: str, dep_path: str | None) -> None:
    """Add a dependency and resolve it."""
    from prove.config import find_config, load_config, write_dependency
    from prove.lockfile import read_lockfile, write_lockfile
    from prove.resolver import resolve

    try:
        config_path = find_config()
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)

    project_dir = config_path.parent

    if dep_path:
        # Local path dependency
        abs_path = str(Path(dep_path).resolve())
        # Make path relative to prove.toml for portability
        try:
            rel_path = os.path.relpath(abs_path, project_dir)
        except ValueError:
            rel_path = abs_path
        write_dependency(config_path, name, version or "*", dep_path=rel_path)
    elif not version:
        # Fetch latest from registry
        from prove.registry import fetch_package_info

        info = fetch_package_info(name)
        if info and info.versions:
            version = info.versions[0].version
            click.echo(f"using latest: {name} {version}")
        else:
            click.echo(f"error: package '{name}' not found in registry", err=True)
            raise SystemExit(1)
        write_dependency(config_path, name, version)
    else:
        write_dependency(config_path, name, version)

    # Re-read config and resolve
    config = load_config(config_path)
    deps = [(d.name, d.version_constraint) for d in config.dependencies]
    local_paths = {d.name: d.path for d in config.dependencies if d.path}
    existing = read_lockfile(project_dir / "prove.lock")

    result = resolve(deps, existing_lock=existing, local_paths=local_paths)
    if isinstance(result, list):
        for err in result:
            click.echo(f"error: {err.message}", err=True)
        raise SystemExit(1)

    write_lockfile(project_dir / "prove.lock", result)
    click.echo(f"added {name} {version}")


@package.command("remove")
@click.argument("name")
def package_remove(name: str) -> None:
    """Remove a dependency."""
    from prove.config import find_config, load_config, remove_dependency
    from prove.lockfile import read_lockfile, write_lockfile
    from prove.resolver import resolve

    try:
        config_path = find_config()
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)

    project_dir = config_path.parent

    if not remove_dependency(config_path, name):
        click.echo(f"error: '{name}' not found in dependencies", err=True)
        raise SystemExit(1)

    # Re-resolve
    config = load_config(config_path)
    deps = [(d.name, d.version_constraint) for d in config.dependencies]
    local_paths = {d.name: d.path for d in config.dependencies if d.path}
    existing = read_lockfile(project_dir / "prove.lock")

    if deps:
        result = resolve(deps, existing_lock=existing, local_paths=local_paths)
        if isinstance(result, list):
            for err in result:
                click.echo(f"error: {err.message}", err=True)
            raise SystemExit(1)
        write_lockfile(project_dir / "prove.lock", result)
    else:
        # No deps left, write empty lockfile
        from prove import __version__
        from prove.lockfile import Lockfile

        write_lockfile(project_dir / "prove.lock", Lockfile(prove_version=__version__))

    click.echo(f"removed {name}")


@package.command("install")
@click.argument("path", default=".", type=click.Path(exists=True))
def package_install(path: str) -> None:
    """Fetch all dependencies from lockfile."""
    from prove.config import find_config, load_config
    from prove.lockfile import read_lockfile, write_lockfile
    from prove.registry import download_package, verify_checksum
    from prove.resolver import resolve

    try:
        config_path = find_config(Path(path))
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)

    project_dir = config_path.parent
    lockfile = read_lockfile(project_dir / "prove.lock")

    config = load_config(config_path)

    if lockfile is None:
        # No lockfile — resolve from config
        if not config.dependencies:
            click.echo("no dependencies to install")
            return

        deps = [(d.name, d.version_constraint) for d in config.dependencies]
        local_paths = {d.name: d.path for d in config.dependencies if d.path}
        result = resolve(deps, local_paths=local_paths)
        if isinstance(result, list):
            for err in result:
                click.echo(f"error: {err.message}", err=True)
            raise SystemExit(1)
        lockfile = result
        write_lockfile(project_dir / "prove.lock", lockfile)

    installed = 0
    for pkg in lockfile.packages:
        # Local packages are already in place
        if pkg.source.startswith("file://"):
            local_path = Path(pkg.source[7:])
            if local_path.exists():
                installed += 1
                click.echo(f"  {pkg.name} {pkg.version} (local: {local_path})")
                continue
            else:
                click.echo(f"error: local package missing: {local_path}", err=True)
                continue

        pkg_path = download_package(
            pkg.name,
            pkg.version,
            pkg.source.rsplit("/packages/", 1)[0] if "/packages/" in pkg.source else "",
        )
        if pkg_path is None:
            click.echo(f"error: failed to download {pkg.name} {pkg.version}", err=True)
            continue
        if pkg.checksum and not verify_checksum(pkg_path, pkg.checksum):
            click.echo(f"warning: checksum mismatch for {pkg.name} {pkg.version}", err=True)
        installed += 1
        click.echo(f"  installed {pkg.name} {pkg.version}")

    click.echo(f"\n{installed} package(s) installed")


@package.command("publish")
@click.option("--dry-run", is_flag=True, help="Validate without creating .prvpkg.")
@click.argument("path", default=".", type=click.Path(exists=True))
def package_publish(path: str, dry_run: bool) -> None:
    """Validate and create a .prvpkg file."""
    from prove import __version__
    from prove.builder import lex_and_parse
    from prove.checker import Checker
    from prove.config import discover_prv_files, find_config, load_config
    from prove.package import create_package

    try:
        config_path = find_config(Path(path))
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)

    project_dir = config_path.parent
    config = load_config(config_path)
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = discover_prv_files(src_dir)
    if not prv_files:
        click.echo("error: no .prv files found", err=True)
        raise SystemExit(1)

    # Parse and check all modules
    modules = {}
    has_errors = False
    for prv_file in prv_files:
        source = prv_file.read_text()
        try:
            module = lex_and_parse(source, str(prv_file))
        except Exception as e:
            click.echo(f"error: {e}", err=True)
            has_errors = True
            continue

        checker = Checker()
        checker.check(module)
        if checker.has_errors():
            renderer = DiagnosticRenderer(color=True)
            for diag in checker.diagnostics:
                click.echo(renderer.render(diag), err=True)
            has_errors = True
            continue

        # Validate purity: no foreign blocks
        from prove.ast_nodes import ModuleDecl

        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                if decl.foreign_blocks:
                    click.echo(
                        f"error: module '{decl.name}' has foreign blocks — "
                        "packages cannot contain FFI code",
                        err=True,
                    )
                    has_errors = True

        # Use module name from ModuleDecl
        mod_name = None
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                mod_name = decl.name
                break
        if mod_name:
            modules[mod_name] = module

    if has_errors:
        raise SystemExit(1)

    if dry_run:
        click.echo(f"dry run: {len(modules)} module(s) validated")
        for name in sorted(modules):
            click.echo(f"  {name}")
        return

    # Build dependencies list
    deps = [(d.name, d.version_constraint) for d in config.dependencies]

    output = project_dir / f"{config.package.name}-{config.package.version}.prvpkg"
    create_package(
        output,
        name=config.package.name,
        version=config.package.version,
        prove_version=__version__,
        modules=modules,
        dependencies=deps,
    )
    click.echo(f"published {output}")


@package.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
def package_list(path: str) -> None:
    """Show dependency tree."""
    from prove.config import find_config, load_config
    from prove.lockfile import read_lockfile

    try:
        config_path = find_config(Path(path))
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)

    project_dir = config_path.parent
    config = load_config(config_path)
    lockfile = read_lockfile(project_dir / "prove.lock")

    if not config.dependencies:
        click.echo("no dependencies")
        return

    locked = {}
    if lockfile:
        locked = {pkg.name: pkg for pkg in lockfile.packages}

    for dep in config.dependencies:
        pkg = locked.get(dep.name)
        if pkg:
            click.echo(f"  {dep.name} {pkg.version} (locked)")
        else:
            click.echo(f"  {dep.name} {dep.version_constraint} (not installed)")


@package.command("clean")
def package_clean() -> None:
    """Clear the package cache (~/.prove/cache/packages/)."""
    from prove.registry import clear_cache

    count = clear_cache()
    click.echo(f"removed {count} cached package(s)")


def _view_impl(file: str) -> None:
    """View the AST of a Prove source file."""
    source = Path(file).read_text()
    filename = str(file)

    try:
        module = parse(source, filename)
    except CompileError as e:
        renderer = DiagnosticRenderer(color=True)
        for diag in e.diagnostics:
            click.echo(renderer.render(diag), err=True)
        raise SystemExit(1)

    _dump_ast(module, 0)


@advanced.command("view")
@click.argument("file", type=click.Path(exists=True))
def advanced_view(file: str) -> None:
    """View the AST of a Prove source file."""
    _view_impl(file)


@main.command("view")
@click.argument("file", type=click.Path(exists=True))
def view(file: str) -> None:
    """View the AST of a Prove source file (shortcut for 'advanced view')."""
    _view_impl(file)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--load", "mode", flag_value="load", help="Compile .prv lookup to PDAT binary.")
@click.option("--dump", "mode", flag_value="dump", help="Dump PDAT binary to .prv source.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output path.")
def compiler(file: str, mode: str | None, output: str | None) -> None:
    """Convert between .prv lookup types and PDAT binary format."""
    from prove.store_binary import pdat_to_prv, prv_to_pdat

    if mode is None:
        # Auto-detect from file extension
        if file.endswith(".prv"):
            mode = "load"
        elif file.endswith(".dat") or file.endswith(".bin"):
            mode = "dump"
        else:
            click.echo("Error: specify --load or --dump, or use .prv/.dat extension.", err=True)
            raise SystemExit(1)

    if mode == "load":
        try:
            out = prv_to_pdat(file, output)
        except CompileError as e:
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            raise SystemExit(1)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)
        click.echo(f"Wrote {out}")
    else:
        try:
            source = pdat_to_prv(file, output)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)
        if output:
            click.echo(f"Wrote {output}")
        else:
            click.echo(source, nl=False)


def _setup_impl() -> None:
    """Re-download ML stores to ~/.prove/."""
    from prove.nlp_store import download_stores

    ok = download_stores()
    if ok:
        click.echo("Setup complete.")
    else:
        click.echo("Setup failed — check your internet connection.", err=True)
        raise SystemExit(1)


@advanced.command("setup")
def advanced_setup() -> None:
    """Re-download ML stores to ~/.prove/."""
    _setup_impl()


@main.command("setup")
def setup() -> None:
    """Re-download ML stores (shortcut for 'advanced setup')."""
    _setup_impl()


@main.command("setup-nlp")
def setup_nlp() -> None:
    """Build NLP data stores from scratch (requires: pip install 'prove[nlp]')."""
    import importlib.util
    from pathlib import Path

    click.echo("Building NLP data stores from scratch...")
    try:
        import nltk  # noqa: F401
        import spacy  # noqa: F401
    except ImportError:
        click.echo("  NLP deps not installed. Run: pip install 'prove[nlp]'")
        return

    script = Path(__file__).parent.parent / "scripts" / "build_stores.py"
    if script.exists():
        spec = importlib.util.spec_from_file_location("build_stores", script)
        if spec and spec.loader:
            build = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(build)
            build.build_verb_synonyms()
            build.build_synonym_cache()
            build.build_similarity_matrix()
            build.build_semantic_features()
            build.build_stdlib_index()
            click.echo("  NLP stores built.")
    else:
        click.echo("  build_stores.py not found.")


def _dump_ast(node: object, depth: int) -> None:
    """Print a readable AST dump."""
    indent = "  " * depth
    name = type(node).__name__

    if hasattr(node, "__dataclass_fields__"):
        fields = node.__dataclass_fields__
        click.echo(f"{indent}{name}")
        for field_name in fields:
            if field_name == "span":
                continue
            value = getattr(node, field_name)
            if isinstance(value, list):
                if value:
                    click.echo(f"{indent}  {field_name}:")
                    for item in value:
                        _dump_ast(item, depth + 2)
                else:
                    click.echo(f"{indent}  {field_name}: []")
            elif hasattr(value, "__dataclass_fields__"):
                click.echo(f"{indent}  {field_name}:")
                _dump_ast(value, depth + 2)
            elif value is not None:
                click.echo(f"{indent}  {field_name}: {value!r}")
    else:
        click.echo(f"{indent}{name}: {node!r}")
