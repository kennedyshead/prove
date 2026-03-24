"""Prove compiler CLI.

Root commands are development tools (compiler, export, generate, index, intent,
setup, setup-nlp, view).  build/check/format/test are available as Python
fallbacks when optimize.enabled=false (no compiled ``proof`` binary needed).
"""

from __future__ import annotations

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
@click.option("--no-mutate", is_flag=True, help="Don't rewrite source files during format.")
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

        checker = Checker(local_modules=local_modules)
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
def format_cmd(path: str, status: bool) -> None:
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

        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)
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
        generate_treesitter,
        read_canonical_lists,
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
            click.echo("export: tree-sitter-prove")
            ok = generate_treesitter(lists, workspace)
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


@main.command()
@click.argument("file", type=click.Path(exists=True))
def view(file: str) -> None:
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


@main.command()
def setup() -> None:
    """Re-download ML stores to ~/.prove/.

    Downloads pre-trained LSP ML completion stores from the latest release.
    Stores are also downloaded automatically on first use — run this if
    something is wrong with your stores and you want a clean reinstall.

    For developers building stores from scratch:
        pip install 'prove[nlp]' && python scripts/build_stores.py
    """
    from prove.nlp_store import download_stores

    ok = download_stores()
    if ok:
        click.echo("Setup complete.")
    else:
        click.echo("Setup failed — check your internet connection.", err=True)
        raise SystemExit(1)


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
