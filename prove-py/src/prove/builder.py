"""Full build pipeline: .prv source -> native binary."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import Module, ModuleDecl
from prove.c_compiler import CompileCError, compile_c, find_c_compiler
from prove.c_emitter import CEmitter
from prove.c_runtime import copy_runtime
from prove.checker import Checker
from prove.config import ProveConfig
from prove.errors import CompileError, Diagnostic, Severity
from prove.lexer import Lexer
from prove.parser import Parser
from prove.symbols import SymbolTable


@dataclass
class BuildResult:
    """Outcome of a build."""

    ok: bool
    binary: Path | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    c_error: str | None = None


def build_project(
    project_dir: Path,
    config: ProveConfig,
    *,
    debug: bool = False,
) -> BuildResult:
    """Run the full pipeline: discover -> lex -> parse -> check -> emit -> compile."""
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        return BuildResult(ok=False, diagnostics=[], c_error="no .prv files found")

    all_diags: list[Diagnostic] = []
    modules_and_symbols = []

    # Build local module registry for cross-file imports
    from prove.module_resolver import build_module_registry

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)

        # Lex + parse
        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            all_diags.extend(e.diagnostics)
            continue

        # Format (type-infer and rewrite), then re-parse the canonical source
        from prove.formatter import ProveFormatter

        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)
        formatter = ProveFormatter(symbols=symbols)
        formatted = formatter.format(module)
        if formatted != source:
            prv_file.write_text(formatted)

        # Re-parse the formatted source for a clean check
        try:
            tokens = Lexer(formatted, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            all_diags.extend(e.diagnostics)
            continue

        # Check
        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)
        all_diags.extend(checker.diagnostics)

        if checker.has_errors():
            continue

        modules_and_symbols.append((module, symbols))

    # Check for errors
    has_errors = any(d.severity == Severity.ERROR for d in all_diags)
    if has_errors:
        return BuildResult(ok=False, diagnostics=all_diags)

    return _build_c(project_dir, config, modules_and_symbols, all_diags, debug=debug)


def _build_c(
    project_dir: Path,
    config: ProveConfig,
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
    *,
    debug: bool = False,
) -> BuildResult:
    """C backend: emit C, compile with gcc/clang."""
    c_sources: list[str] = []
    for module, symbols in modules_and_symbols:
        memo_info = None
        if config.build.optimize:
            from prove.optimizer import Optimizer

            optimizer = Optimizer(module, symbols)
            module = optimizer.optimize()
            memo_info = optimizer.get_memo_info()
        emitter = CEmitter(module, symbols, memo_info)
        c_sources.append(emitter.emit())

    # Set up build directory
    build_dir = project_dir / "build"
    gen_dir = build_dir / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)

    # Write generated C
    gen_c_files: list[Path] = []
    for i, c_src in enumerate(c_sources):
        c_path = gen_dir / f"module_{i}.c"
        c_path.write_text(c_src)
        gen_c_files.append(c_path)

    # Copy runtime
    runtime_c_files = copy_runtime(build_dir)

    # Find compiler
    cc = find_c_compiler()
    if cc is None:
        return BuildResult(
            ok=False,
            diagnostics=all_diags,
            c_error="no C compiler found (install gcc or clang)",
        )

    # Collect foreign library names for linker flags
    extra_flags: list[str] = list(config.build.c_flags)
    link_flags: list[str] = list(config.build.link_flags)
    # Math runtime always needs libm
    link_flags.append("-lm")
    for module, _symbols in modules_and_symbols:
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                for fb in decl.foreign_blocks:
                    lib = fb.library
                    if lib.startswith("lib"):
                        link_flags.append(f"-l{lib[3:]}")
                    else:
                        link_flags.append(f"-l{lib}")
                # Add stdlib-required linker flags
                from prove.stdlib_loader import stdlib_link_flags

                for imp in decl.imports:
                    for flag in stdlib_link_flags(imp.module):
                        if flag not in link_flags:
                            link_flags.append(flag)

    # Compile
    runtime_dir = build_dir / "runtime"
    binary_name = config.package.name or "a.out"
    binary_path = build_dir / binary_name

    try:
        compile_c(
            c_files=runtime_c_files + gen_c_files,
            output=binary_path,
            compiler=cc,
            optimize=config.build.optimize and not debug,
            debug=debug,
            include_dirs=[runtime_dir],
            extra_flags=extra_flags + link_flags,
        )
    except CompileCError as e:
        return BuildResult(
            ok=False,
            diagnostics=all_diags,
            c_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
        )

    return BuildResult(ok=True, binary=binary_path, diagnostics=all_diags)
