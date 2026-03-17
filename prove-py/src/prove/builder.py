"""Full build pipeline: .prv source -> native binary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import Module, ModuleDecl
from prove.c_compiler import (
    CompileCError,
    _compiler_family,
    compile_c,
    find_c_compiler,
    find_ccache,
)
from prove.c_emitter import CEmitter
from prove.c_runtime import copy_runtime
from prove.checker import Checker
from prove.config import ProveConfig, discover_prv_files
from prove.errors import CompileError, Diagnostic, Severity
from prove.lexer import Lexer
from prove.parser import Parser
from prove.symbols import SymbolTable

_FOREIGN_PKG_CONFIG: dict[str, str] = {
    "libpython3": "python3-embed",
    "libjvm": "jni",
}


def _resolve_foreign_flags(library: str) -> tuple[list[str], list[str]]:
    """Resolve compiler and linker flags for a foreign library.

    Returns (c_flags, link_flags).  Resolution order:
      1. Environment variables (PROVE_<LIB>_CFLAGS / PROVE_<LIB>_LDFLAGS)
      2. pkg-config when a mapping exists
      3. Plain -l<name> fallback

    For libpython3 the env vars are PROVE_PYTHON_CFLAGS and PROVE_PYTHON_LDFLAGS.
    """
    import os
    import subprocess

    # Step 1: Check environment variables.
    # Derive env key: "libpython3" -> "PYTHON", "libjvm" -> "JVM"
    env_key = library.upper()
    if env_key.startswith("LIB"):
        env_key = env_key[3:]
    # Normalise: "python3" -> "PYTHON" (strip trailing digits for cleaner names)
    env_key = env_key.rstrip("0123456789")
    cflags_env = os.environ.get(f"PROVE_{env_key}_CFLAGS", "").strip()
    ldflags_env = os.environ.get(f"PROVE_{env_key}_LDFLAGS", "").strip()
    if cflags_env or ldflags_env:
        c_flags = cflags_env.split() if cflags_env else []
        l_flags = ldflags_env.split() if ldflags_env else []
        return c_flags, l_flags

    # Step 2: Try pkg-config
    pc_name = _FOREIGN_PKG_CONFIG.get(library)
    if pc_name:
        try:
            result = subprocess.run(
                ["pkg-config", "--cflags", "--libs", pc_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                flags = result.stdout.strip().split()
                c_flags = [f for f in flags if f.startswith("-I")]
                l_flags = [f for f in flags if not f.startswith("-I")]
                return c_flags, l_flags
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # Step 3: Fallback — plain -l<name>
    name = library[3:] if library.startswith("lib") else library
    return [], [f"-l{name}"]


def _find_llvm_profdata() -> str | None:
    """Find llvm-profdata: plain name, versioned, or via xcrun (macOS)."""
    import shutil
    import subprocess

    if shutil.which("llvm-profdata"):
        return "llvm-profdata"
    # Versioned names (llvm-profdata-18, etc.)
    for v in range(20, 13, -1):
        name = f"llvm-profdata-{v}"
        if shutil.which(name):
            return name
    # macOS: Xcode bundles LLVM tools behind xcrun
    try:
        result = subprocess.run(
            ["xcrun", "--find", "llvm-profdata"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


@dataclass
class BuildResult:
    """Outcome of a build."""

    ok: bool
    binary: Path | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    c_error: str | None = None
    comptime_dependencies: set[Path] = field(default_factory=set)


def lex_and_parse(source: str, filename: str):
    """Lexes and parses the source"""
    tokens = Lexer(source, filename).lex()
    return Parser(tokens, filename).parse()


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

    prv_files = discover_prv_files(src_dir)
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
            module = lex_and_parse(source, filename)
        except CompileError as e:
            all_diags.extend(e.diagnostics)
            continue

        # Format (type-infer and rewrite), then re-parse only if source changed
        from prove.formatter import ProveFormatter

        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)
        formatter = ProveFormatter(symbols=symbols)
        formatted = formatter.format(module)
        if formatted != source:
            prv_file.write_text(formatted)
            # Re-parse the formatted source for a clean check
            try:
                module = lex_and_parse(formatted, filename)
            except CompileError as e:
                all_diags.extend(e.diagnostics)
                continue
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

    # Compile pure stdlib modules that are imported by the project
    user_module_count = len(modules_and_symbols)
    _compile_pure_stdlib(modules_and_symbols, all_diags)

    return _build_c(
        project_dir,
        config,
        modules_and_symbols,
        all_diags,
        debug=debug,
        user_module_count=user_module_count,
    )


def _compile_pure_stdlib(
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
) -> None:
    """Find and compile pure stdlib modules imported by the project."""
    from prove.stdlib_loader import load_stdlib_prv_source

    # Collect all imported module names
    seen: set[str] = set()
    for module, _symbols in modules_and_symbols:
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                for imp in decl.imports:
                    seen.add(imp.module)

    # For each imported module, check if it's a pure stdlib module
    for mod_name in seen:
        source = load_stdlib_prv_source(mod_name)
        if source is None:
            continue

        filename = f"<stdlib:{mod_name}>"
        try:
            tokens = Lexer(source, filename).lex()
            stdlib_module = Parser(tokens, filename).parse()
        except CompileError as e:
            all_diags.extend(e.diagnostics)
            continue

        checker = Checker()
        symbols = checker.check(stdlib_module)
        all_diags.extend(checker.diagnostics)
        if checker.has_errors():
            continue

        modules_and_symbols.append((stdlib_module, symbols))


def _build_c(
    project_dir: Path,
    config: ProveConfig,
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
    *,
    debug: bool = False,
    user_module_count: int | None = None,
) -> BuildResult:
    """C backend: emit C, compile with gcc/clang."""
    c_sources: list[str] = []
    stdlib_libs: set[str] = set()
    comptime_deps: set[Path] = set()
    for module, symbols in modules_and_symbols:
        memo_info = None
        runtime_deps = None
        escape_info = None
        if config.optimize.enabled:
            from prove.optimizer import Optimizer

            optimizer = Optimizer(module, symbols)
            module = optimizer.optimize()
            memo_info = optimizer.get_memo_info()
            runtime_deps = optimizer.get_runtime_deps()
            escape_info = optimizer.get_escape_info()
        else:
            from prove.optimizer import RuntimeDeps

            runtime_deps = RuntimeDeps()
            for decl in module.declarations:
                if isinstance(decl, ModuleDecl):
                    for imp in decl.imports:
                        runtime_deps.add_module(imp.module)
        optimized = config.optimize.enabled and not debug
        emitter = CEmitter(module, symbols, memo_info, escape_info, optimize=optimized)
        c_sources.append(emitter.emit())
        comptime_deps.update(emitter.comptime_dependencies)
        if runtime_deps:
            stdlib_libs.update(runtime_deps.get_libs())

    # Generate forward declarations for pure stdlib functions
    if user_module_count is not None and user_module_count < len(c_sources):
        forward_decls = _extract_forward_decls(c_sources[user_module_count:])
        if forward_decls:
            header = "\n".join(forward_decls) + "\n"
            for i in range(user_module_count):
                # Insert forward declarations after the last #include
                c_sources[i] = _inject_forward_decls(c_sources[i], header)

    # Set up build directory
    build_dir = project_dir / "build"
    gen_dir = build_dir / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)

    if debug:
        (gen_dir / ".clangd").write_text("CompileFlags:\n  Add: -I../runtime\n")

    # Write generated C
    gen_c_files: list[Path] = []
    for i, c_src in enumerate(c_sources):
        c_path = gen_dir / f"module_{i}.c"
        c_path.write_text(c_src)
        gen_c_files.append(c_path)

    # Auto-bundle Python packages if the project embeds libpython3
    from prove._python_bundle import maybe_generate_bundle

    maybe_generate_bundle(modules_and_symbols, comptime_deps, gen_dir)

    # Run pre-build commands (e.g. generating C headers from scripts)
    if config.build.pre_build:
        import subprocess as _sp

        for cmd in config.build.pre_build:
            result = _sp.run(cmd, cwd=project_dir, capture_output=True, text=True)
            if result.returncode != 0:
                return BuildResult(
                    ok=False,
                    diagnostics=all_diags,
                    c_error=f"pre_build command failed: {' '.join(cmd)}\n{result.stderr}",
                )

    # Add user-specified extra C sources (thin wrappers for foreign libraries, etc.)
    for src_rel in config.build.c_sources:
        src_path = project_dir / src_rel
        if src_path.exists():
            gen_c_files.append(src_path)

    # Copy runtime
    runtime_c_files = copy_runtime(build_dir, c_sources=c_sources, stdlib_libs=stdlib_libs or None)

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
    # Math runtime always needs libm; par_map needs pthreads
    link_flags.append("-lm")
    link_flags.append("-lpthread")
    for module, _symbols in modules_and_symbols:
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                for fb in decl.foreign_blocks:
                    cf, lf = _resolve_foreign_flags(fb.library)
                    extra_flags.extend(cf)
                    link_flags.extend(lf)
                # Add stdlib-required linker flags
                from prove.stdlib_loader import stdlib_link_flags

                for imp in decl.imports:
                    for flag in stdlib_link_flags(imp.module):
                        if flag not in link_flags:
                            link_flags.append(flag)

    # Release mode: enable PROVE_RELEASE define for runtime check elision
    if config.optimize.enabled and not debug:
        extra_flags.append("-DPROVE_RELEASE")

    # Compile
    runtime_dir = build_dir / "runtime"
    binary_name = config.package.name or "a.out"
    binary_path = build_dir / binary_name
    optimize = config.optimize.enabled and not debug
    all_c_files = runtime_c_files + gen_c_files
    compile_kwargs: dict = dict(
        c_files=all_c_files,
        output=binary_path,
        compiler=cc,
        optimize=optimize,
        debug=debug,
        include_dirs=[runtime_dir, gen_dir],
        extra_flags=extra_flags + link_flags,
        strip=config.optimize.strip,
        tune_host=config.optimize.tune_host,
        gc_sections=config.optimize.gc_sections,
        use_ccache=config.build.ccache and find_ccache() is not None,
    )

    use_pgo = config.optimize.pgo and optimize
    if use_pgo:
        family = _compiler_family(cc)
        if family == "msvc":
            import warnings

            warnings.warn("PGO not supported with MSVC; building without PGO")
            use_pgo = False

    try:
        if use_pgo:
            import os
            import subprocess

            pgo_dir = build_dir / "pgo_data"
            pgo_dir.mkdir(exist_ok=True)

            # Clean stale profile data
            for f in pgo_dir.glob("*.gcda"):
                f.unlink()
            for f in pgo_dir.glob("*.profraw"):
                f.unlink()
            profdata = pgo_dir / "default.profdata"
            if profdata.exists():
                profdata.unlink()

            # Step 1: Build with profile-generate
            print("pgo: building instrumented binary...")
            compile_c(**compile_kwargs, pgo_phase="generate", pgo_dir=pgo_dir)

            # Step 2: Run the binary to collect profile data.
            # Feed empty stdin so programs that read input exit promptly.
            # The training run exercises startup, init, and teardown paths
            # which is enough for PGO branch-prediction and layout hints.
            print("pgo: running training pass...")
            env = {**os.environ, "LLVM_PROFILE_FILE": str(pgo_dir / "default_%m.profraw")}
            try:
                subprocess.run(
                    [str(binary_path)],
                    timeout=10,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    env=env,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass  # best-effort profiling

            # Step 2b: Clang needs profraw → profdata merge
            if family == "clang":
                profraw_files = list(pgo_dir.glob("*.profraw"))
                if profraw_files:
                    llvm_profdata = _find_llvm_profdata()
                    if llvm_profdata:
                        subprocess.run(
                            [llvm_profdata, "merge", "-output", str(profdata)]
                            + [str(f) for f in profraw_files],
                            capture_output=True,
                            timeout=30,
                        )
                    else:
                        print("pgo: llvm-profdata not found; cannot merge profiles")

            # Step 3: Rebuild with profile-use (fall back to normal if no data)
            has_profile = any(pgo_dir.glob("*.gcda")) or profdata.exists()
            if has_profile:
                print("pgo: rebuilding with profile data...")
                compile_c(**compile_kwargs, pgo_phase="use", pgo_dir=pgo_dir)
            else:
                print("pgo: no profile data collected; building without PGO")
                compile_c(**compile_kwargs)
        else:
            compile_c(**compile_kwargs)
    except CompileCError as e:
        return BuildResult(
            ok=False,
            diagnostics=all_diags,
            c_error=f"{e}\n{e.stderr}" if e.stderr else str(e),
        )

    # Copy final binary to dist/
    import shutil as _shutil

    dist_dir = project_dir / "dist"
    dist_dir.mkdir(exist_ok=True)
    dist_path = dist_dir / binary_name
    _shutil.copy2(binary_path, dist_path)

    return BuildResult(
        ok=True,
        binary=dist_path,
        diagnostics=all_diags,
        comptime_dependencies=comptime_deps,
    )


_FORWARD_DECL_RE = re.compile(r"^(?:void|int64_t|double|bool|Prove_\w+\*?)\s+prv_\w+\([^)]*\);$")


def _extract_forward_decls(stdlib_c_sources: list[str]) -> list[str]:
    """Extract function forward declarations from pure stdlib C sources."""
    decls: list[str] = []
    for src in stdlib_c_sources:
        for line in src.splitlines():
            line = line.strip()
            if _FORWARD_DECL_RE.match(line):
                decls.append(line)
    return decls


def _inject_forward_decls(c_source: str, decls: str) -> str:
    """Insert forward declarations after the last #include line."""
    lines = c_source.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("#include"):
            insert_at = i + 1
    lines.insert(insert_at, "\n// Forward declarations for pure stdlib modules")
    lines.insert(insert_at + 1, decls)
    return "\n".join(lines)
