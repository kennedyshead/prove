"""Full build pipeline: .prv source -> native binary."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import Module
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
    asm_error: str | None = None


def build_project(
    project_dir: Path, config: ProveConfig, *, asm: bool = False,
) -> BuildResult:
    """Run the full pipeline: discover -> lex -> parse -> check -> emit -> compile.

    If *asm* is True, emit x86-64 assembly and assemble/link instead of C.
    """
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        return BuildResult(ok=False, diagnostics=[], c_error="no .prv files found")

    all_diags: list[Diagnostic] = []
    modules_and_symbols = []

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

        # Check
        checker = Checker()
        symbols = checker.check(module)
        all_diags.extend(checker.diagnostics)

        if checker.has_errors():
            continue

        modules_and_symbols.append((module, symbols))

    # Check for errors
    has_errors = any(d.severity == Severity.ERROR for d in all_diags)
    if has_errors:
        return BuildResult(ok=False, diagnostics=all_diags)

    if asm:
        return _build_asm(project_dir, config, modules_and_symbols, all_diags)
    return _build_c(project_dir, config, modules_and_symbols, all_diags)


def _build_c(
    project_dir: Path,
    config: ProveConfig,
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
) -> BuildResult:
    """C backend: emit C, compile with gcc/clang."""
    c_sources: list[str] = []
    for module, symbols in modules_and_symbols:
        emitter = CEmitter(module, symbols)
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
            ok=False, diagnostics=all_diags,
            c_error="no C compiler found (install gcc or clang)",
        )

    # Compile
    runtime_dir = build_dir / "runtime"
    binary_name = config.package.name or "a.out"
    binary_path = build_dir / binary_name

    try:
        compile_c(
            c_files=runtime_c_files + gen_c_files,
            output=binary_path,
            compiler=cc,
            optimize=config.build.optimize,
            include_dirs=[runtime_dir],
        )
    except CompileCError as e:
        return BuildResult(
            ok=False, diagnostics=all_diags,
            c_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
        )

    return BuildResult(ok=True, binary=binary_path, diagnostics=all_diags)


def _build_asm(
    project_dir: Path,
    config: ProveConfig,
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
) -> BuildResult:
    """ASM backend: emit x86-64 assembly, assemble, link with C runtime."""
    from prove.asm_assembler import CompileAsmError, assemble, find_assembler, link
    from prove.asm_emitter import AsmEmitter
    from prove.asm_runtime import AsmRuntimeError, compile_runtime_objects

    asm_sources: list[str] = []
    for module, symbols in modules_and_symbols:
        emitter = AsmEmitter(module, symbols)
        asm_sources.append(emitter.emit())

    # Set up build directory
    build_dir = project_dir / "build"
    gen_dir = build_dir / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)

    # Write generated ASM
    asm_files: list[Path] = []
    for i, asm_src in enumerate(asm_sources):
        asm_path = gen_dir / f"module_{i}.s"
        asm_path.write_text(asm_src)
        asm_files.append(asm_path)

    # Find assembler
    assembler = find_assembler()
    if assembler is None:
        return BuildResult(
            ok=False, diagnostics=all_diags,
            asm_error="no assembler found (install gcc or binutils)",
        )

    # Compile C runtime to .o files
    try:
        runtime_objects = compile_runtime_objects(build_dir)
    except AsmRuntimeError as e:
        return BuildResult(
            ok=False, diagnostics=all_diags,
            asm_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
        )

    # Assemble generated .s files to .o
    gen_objects: list[Path] = []
    for asm_file in asm_files:
        obj_file = asm_file.with_suffix(".o")
        try:
            assemble(asm_file, obj_file, assembler=assembler)
        except CompileAsmError as e:
            return BuildResult(
                ok=False, diagnostics=all_diags,
                asm_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
            )
        gen_objects.append(obj_file)

    # Link everything
    binary_name = config.package.name or "a.out"
    binary_path = build_dir / binary_name

    try:
        link(runtime_objects + gen_objects, binary_path, linker=assembler)
    except CompileAsmError as e:
        return BuildResult(
            ok=False, diagnostics=all_diags,
            asm_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
        )

    return BuildResult(ok=True, binary=binary_path, diagnostics=all_diags)
