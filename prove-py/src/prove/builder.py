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
from prove.parse import parse as parse_source
from prove.symbols import SymbolTable

_FOREIGN_PKG_CONFIG: dict[str, str] = {
    "libpython3": "python3-embed",
    "libjvm": "jni",
}


def _resolve_foreign_flags(
    library: str, *, standalone: bool = False
) -> tuple[list[str], list[str]]:
    """Resolve compiler and linker flags for a foreign library.

    Returns (c_flags, link_flags).  Resolution order:
      1. Environment variables (PROVE_<LIB>_CFLAGS / PROVE_<LIB>_LDFLAGS)
      2. Standalone static link (when standalone=True and library is known)
      3. pkg-config when a mapping exists
      4. Plain -l<name> fallback

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
        # For libpython3: derive PYTHON_HOME from the include path so the
        # embedded interpreter finds its stdlib (critical when build Python
        # differs from the target Python).
        if library == "libpython3":
            import re

            m = re.search(r"-I(.+?/python\d+\.\d+)", cflags_env)
            if m:
                # include dir is .../include/python3.X → home is two levels up
                python_home = str(Path(m.group(1)).parent.parent)
                c_flags.append(f'-DPYTHON_HOME="{python_home}"')
        return c_flags, l_flags

    # Step 2: Standalone static linking
    if standalone and library == "libpython3":
        return _resolve_python_static()

    # Step 3: Try pkg-config
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

    # Step 4: Fallback — plain -l<name>
    name = library[3:] if library.startswith("lib") else library
    return [], [f"-l{name}"]


def _resolve_python_static() -> tuple[list[str], list[str]]:
    """Return flags to statically link libpython3 for a standalone binary.

    Finds libpython3.x.a via sysconfig, then pulls transitive link deps from
    python3-config --ldflags --embed (stripping -lpython* since we supply the
    archive directly).  Falls back to dynamic linking if the static archive
    cannot be found.
    """
    import subprocess
    import sys
    import sysconfig

    c_flags: list[str] = []
    link_flags: list[str] = []

    # Include flags (same as dynamic)
    try:
        result = subprocess.run(
            ["python3-config", "--includes"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            c_flags.extend(result.stdout.strip().split())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Locate the static archive: libpython3.x.a
    version = sysconfig.get_config_var("VERSION") or ""  # e.g. "3.12"
    static_lib: Path | None = None
    for config_key in ("LIBPL", "LIBDIR"):
        d = sysconfig.get_config_var(config_key)
        if d:
            candidate = Path(d) / f"libpython{version}.a"
            if candidate.exists():
                static_lib = candidate
                break

    if static_lib is None:
        # Could not find static archive — warn and fall back to dynamic
        print(
            f"libpython{version}.a not found; "
            "falling back to dynamic linking. "
            "Install a Python build with static libraries to produce a truly standalone binary."
        )
        try:
            result = subprocess.run(
                ["pkg-config", "--cflags", "--libs", "python3-embed"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                flags = result.stdout.strip().split()
                c_flags.extend(f for f in flags if f.startswith("-I"))
                link_flags.extend(f for f in flags if not f.startswith("-I"))
                return c_flags, link_flags
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        link_flags.append("-lpython3")
        return c_flags, link_flags

    print(f"linking libpython{version} statically ({static_lib})")

    # Pull transitive deps from python3-config --ldflags --embed,
    # dropping -lpython* since we supply the archive directly.
    search_dirs: list[str] = []
    extra_libs: list[str] = []
    try:
        result = subprocess.run(
            ["python3-config", "--ldflags", "--embed"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for flag in result.stdout.strip().split():
                if flag.startswith("-lpython"):
                    continue  # replaced by static archive
                if flag.startswith("-L"):
                    search_dirs.append(flag)
                else:
                    extra_libs.append(flag)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Order: -L dirs first, then the archive (by path), then transitive libs
    link_flags.extend(search_dirs)
    link_flags.append(str(static_lib))
    link_flags.extend(extra_libs)

    # Platform-specific transitive requirements
    if sys.platform == "darwin":
        if not any("-framework" in f for f in link_flags):
            link_flags += ["-framework", "CoreFoundation"]
    else:
        for lib in ("-ldl", "-lutil"):
            if lib not in link_flags:
                link_flags.append(lib)

    return c_flags, link_flags


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
    return parse_source(source, filename)


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

    # Load installed packages from lockfile
    package_modules = None
    lockfile_path = project_dir / "prove.lock"
    if lockfile_path.exists():
        from prove.lockfile import read_lockfile
        from prove.package_loader import load_installed_packages

        lockfile = read_lockfile(lockfile_path)
        if lockfile:
            package_modules = load_installed_packages(project_dir, lockfile)

    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)

        # Lex + parse
        try:
            module = lex_and_parse(source, filename)
        except CompileError as e:
            all_diags.extend(e.diagnostics)
            continue

        # Surface parse diagnostics (E2xx) from tree-sitter conversion
        if module.parse_diagnostics:
            all_diags.extend(module.parse_diagnostics)
            if any(d.severity == Severity.ERROR for d in module.parse_diagnostics):
                continue

        # Format (type-infer and rewrite), then re-parse only if source changed
        from prove.formatter import ProveFormatter

        checker = Checker(local_modules=local_modules, package_modules=package_modules)
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
            if module.parse_diagnostics:
                all_diags.extend(module.parse_diagnostics)
                if any(d.severity == Severity.ERROR for d in module.parse_diagnostics):
                    continue
            checker = Checker(local_modules=local_modules, package_modules=package_modules)
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

    # Compile package modules that are imported by the project
    if package_modules:
        _compile_package_modules(package_modules, modules_and_symbols, all_diags)

    standalone = not (debug or config.build.debug)
    return _build_c(
        project_dir,
        config,
        modules_and_symbols,
        all_diags,
        debug=debug,
        user_module_count=user_module_count,
        standalone=standalone,
        local_modules=local_modules,
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
            stdlib_module = parse_source(source, filename)
        except CompileError as e:
            all_diags.extend(e.diagnostics)
            continue

        checker = Checker()
        symbols = checker.check(stdlib_module)
        all_diags.extend(checker.diagnostics)
        if checker.has_errors():
            continue

        modules_and_symbols.append((stdlib_module, symbols))


def _compile_package_modules(
    package_modules: dict[str, object],
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
) -> None:
    """Compile package modules imported by the project."""
    from prove.package_loader import load_package_for_emit

    # Collect all imported module names from the project
    imported: set[str] = set()
    for module, _symbols in modules_and_symbols:
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                for imp in decl.imports:
                    if imp.module in package_modules:
                        imported.add(imp.module)

    for mod_name in imported:
        pkg_info = package_modules[mod_name]
        try:
            pkg_module, pkg_symbols = load_package_for_emit(pkg_info)
            modules_and_symbols.append((pkg_module, pkg_symbols))
        except Exception as e:
            all_diags.append(
                Diagnostic(
                    code="E317",
                    message=f"failed to load package module '{mod_name}': {e}",
                    severity=Severity.ERROR,
                )
            )


def _build_c(
    project_dir: Path,
    config: ProveConfig,
    modules_and_symbols: list[tuple[Module, SymbolTable]],
    all_diags: list[Diagnostic],
    *,
    debug: bool = False,
    user_module_count: int | None = None,
    standalone: bool = False,
    local_modules: dict[str, object] | None = None,
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
        emitter = CEmitter(
            module,
            symbols,
            memo_info,
            escape_info,
            optimize=optimized,
            local_modules=local_modules,
        )
        c_sources.append(emitter.emit())
        comptime_deps.update(emitter.comptime_dependencies)
        if runtime_deps:
            stdlib_libs.update(runtime_deps.get_libs())

    # Generate type definitions and forward declarations for pure stdlib functions
    if user_module_count is not None and user_module_count < len(c_sources):
        stdlib_sources = c_sources[user_module_count:]
        forward_decls = _extract_forward_decls(stdlib_sources)
        type_defs = _extract_type_defs(stdlib_sources)
        if forward_decls or type_defs:
            fwd_header = "\n".join(forward_decls) + "\n" if forward_decls else ""
            type_header = "\n".join(type_defs) if type_defs else ""
            for i in range(user_module_count):
                c_sources[i] = _inject_forward_decls(c_sources[i], fwd_header, type_header)

    # Set up build directory
    build_dir = project_dir / "build"
    gen_dir = build_dir / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)

    if debug:
        (gen_dir / ".clangd").write_text("CompileFlags:\n  Add: -I../runtime\n")

    # Write generated C
    # Unity build: when optimizing, concatenate all generated modules into a
    # single translation unit so the C compiler can inline and propagate
    # constants across module boundaries without relying solely on LTO.
    gen_c_files: list[Path] = []
    if config.optimize.enabled and not debug and len(c_sources) > 1:
        unity_path = gen_dir / "unity.c"
        unity_path.write_text(_build_unity_source(c_sources))
        gen_c_files.append(unity_path)
    else:
        for i, c_src in enumerate(c_sources):
            c_path = gen_dir / f"module_{i}.c"
            c_path.write_text(c_src)
            gen_c_files.append(c_path)

    # Auto-bundle Python packages if the project embeds libpython3
    from prove._python_bundle import maybe_generate_bundle

    maybe_generate_bundle(modules_and_symbols, comptime_deps, gen_dir, standalone=standalone)

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
    runtime_c_files = copy_runtime(
        build_dir,
        c_sources=c_sources,
        stdlib_libs=stdlib_libs or None,
        force_libs=config.build.vendor_libs or None,
    )

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
    seen_foreign: set[str] = set()
    for module, _symbols in modules_and_symbols:
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                for fb in decl.foreign_blocks:
                    if fb.library in seen_foreign:
                        continue
                    seen_foreign.add(fb.library)
                    cf, lf = _resolve_foreign_flags(fb.library, standalone=standalone)
                    extra_flags.extend(cf)
                    link_flags.extend(lf)
                # Add stdlib-required linker flags
                from prove.stdlib_loader import stdlib_c_flags, stdlib_link_flags

                for imp in decl.imports:
                    for flag in stdlib_link_flags(imp.module):
                        if flag not in link_flags:
                            link_flags.append(flag)
                    for flag in stdlib_c_flags(imp.module):
                        if flag not in extra_flags:
                            extra_flags.append(flag)

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
        include_dirs=[
            d
            for d in [
                runtime_dir,
                gen_dir,
                runtime_dir / "vendor" / "tree_sitter_prove",
            ]
            if d.exists()
        ],
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


_FORWARD_DECL_RE = re.compile(
    r"^(?:__attribute__\(\([^)]*\)\)\s+)?"
    r"(?:void|int64_t|double|bool|Prove_\w+\*?)\s+prv_\w+\([^)]*\);$"
)


def _extract_forward_decls(stdlib_c_sources: list[str]) -> list[str]:
    """Extract function forward declarations from pure stdlib C sources."""
    decls: list[str] = []
    for src in stdlib_c_sources:
        for line in src.splitlines():
            line = line.strip()
            if _FORWARD_DECL_RE.match(line):
                decls.append(line)
    return decls


def _extract_type_defs(stdlib_c_sources: list[str]) -> list[str]:
    """Extract type definitions (typedef, enum, struct, constructors) from pure stdlib C.

    Collects everything between the #include block and the first function
    forward declaration or non-static function definition.
    """
    type_lines: list[str] = []
    for src in stdlib_c_sources:
        past_includes = False
        for line in src.splitlines():
            stripped = line.strip()
            if not past_includes:
                if stripped.startswith("#include"):
                    continue
                past_includes = True
            # Stop at first function forward declaration or non-static function
            if _FORWARD_DECL_RE.match(stripped):
                break
            # Stop at non-static, non-inline function definitions (actual implementations)
            if (
                stripped
                and not stripped.startswith("static")
                and not stripped.startswith("typedef")
                and not stripped.startswith("enum")
                and not stripped.startswith("struct")
                and not stripped.startswith("}")
                and not stripped.startswith("union")
                and not stripped.startswith("uint8_t")
                and not stripped.startswith("int64_t")
                and not stripped.startswith("double")
                and not stripped.startswith("bool")
                and not stripped.startswith("Prove_")
                and not stripped.startswith("/*")
                and not stripped.startswith("//")
                and not stripped.startswith("return")
                and not stripped.startswith("_v.")
                and not stripped == ""
                and not stripped == "{"
                and not stripped == "};"
                and not stripped == "},"
                and "prv_" in stripped
            ):
                break
            type_lines.append(line)
    return type_lines


def _inject_forward_decls(c_source: str, decls: str, type_defs: str = "") -> str:
    """Insert type definitions and forward declarations after the last #include line."""
    lines = c_source.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("#include"):
            insert_at = i + 1

    # Find Prove_XXX type names already typedef'd in this module
    existing_types: set[str] = set()
    for line in lines:
        m = re.match(r"\s*typedef\s+(?:struct|enum)\s+(Prove_\w+)\s+\1\s*;", line)
        if m:
            existing_types.add(m.group(1))
        m = re.match(r"\s*enum\s+(Prove_\w+)\s*\{", line)
        if m:
            existing_types.add(m.group(1))
    # Types defined in runtime headers — always skip injection
    existing_types.add("Prove_Position")

    # Find insertion point after the emitter's type section:
    # scan forward past the last typedef/struct/static-inline/enum block
    inject_at = insert_at
    i = insert_at
    while i < len(lines):
        stripped = lines[i].strip()
        if (
            stripped.startswith("typedef struct Prove_")
            or stripped.startswith("typedef enum Prove_")
            or stripped.startswith("struct Prove_")
            or stripped.startswith("enum Prove_")
            or stripped.startswith("static inline Prove_")
            or stripped.startswith("static inline " + "Prove_")  # constructors
            or (stripped.startswith("enum {") and i > insert_at)
        ):
            # Skip past this block (find closing brace)
            brace = stripped.count("{") - stripped.count("}")
            i += 1
            while brace > 0 and i < len(lines):
                brace += lines[i].count("{") - lines[i].count("}")
                i += 1
            inject_at = i
            continue
        elif stripped == "" and inject_at > insert_at:
            inject_at = i + 1
            i += 1
            continue
        elif inject_at > insert_at:
            break
        i += 1

    parts = []
    if type_defs:
        # Filter out type definitions already present in this module.
        # Parse into blocks: single-line typedefs are individual blocks,
        # multi-line constructs (brace-delimited) are grouped.
        if existing_types:
            blocks: list[list[str]] = []
            current: list[str] = []
            brace_depth = 0
            for td_line in type_defs.splitlines():
                stripped = td_line.strip()
                if not stripped and brace_depth == 0:
                    if current:
                        blocks.append(current)
                        current = []
                    continue
                # Single-line typedef: treat as its own block
                if stripped.startswith("typedef") and stripped.endswith(";") and brace_depth == 0:
                    if current:
                        blocks.append(current)
                        current = []
                    blocks.append([td_line])
                    continue
                current.append(td_line)
                brace_depth += stripped.count("{") - stripped.count("}")
                if brace_depth <= 0 and current:
                    brace_depth = 0
                    blocks.append(current)
                    current = []
            if current:
                blocks.append(current)

            # Track types seen across injected blocks to deduplicate
            # when the same type is imported by multiple stdlib modules.
            injected_types: set[str] = set()

            def _block_type_name(block: list[str]) -> str | None:
                """Extract the Prove_XXX type name from a block, if any."""
                first = block[0].strip() if block else ""
                m = re.match(r"typedef\s+(?:struct|enum)\s+(Prove_\w+)\s+\1\s*;", first)
                if m:
                    return m.group(1)
                m = re.match(r"(?:enum|struct)\s+(Prove_\w+)\s*\{", first)
                if m:
                    return m.group(1)
                m = re.match(r"static\s+(?:inline\s+|const\s+)?(Prove_\w+)\s", first)
                if m:
                    return m.group(1)
                if first == "enum {":
                    # Anonymous tag enum — extract type from TAG names
                    content = "\n".join(block)
                    m2 = re.search(r"(Prove_\w+)_TAG_", content)
                    if m2:
                        return m2.group(1)
                return None

            def _block_is_duplicate(block: list[str]) -> bool:
                """Check if a block is a duplicate definition for an existing type."""
                first = block[0].strip() if block else ""
                all_types = existing_types | injected_types
                for t in all_types:
                    # Typedef forward declarations
                    if first == f"typedef struct {t} {t};":
                        return True
                    if first == f"typedef enum {t} {t};":
                        return True
                    # Full type body definitions
                    if first == f"enum {t} {{" or first == f"struct {t} {{":
                        return True
                    # Anonymous tag enum for this type
                    if first == "enum {" and f"{t}_TAG_" in "\n".join(block):
                        return True
                    # Constructor/function returning this type (already emitted
                    # by the target module's _emit_imported_type_defs)
                    if first.startswith(f"static inline {t} "):
                        return True
                    # Static const arrays for this type (lookup tables)
                    if first.startswith("static const ") and f" {t}_" in first:
                        return True
                    if first.startswith("static ") and f" {t}_col_" in first:
                        return True
                return False

            filtered_blocks: list[list[str]] = []
            for b in blocks:
                if _block_is_duplicate(b):
                    continue
                filtered_blocks.append(b)
                # Track the type name so later blocks for the same type
                # (from a different stdlib module) are also filtered.
                tname = _block_type_name(b)
                if tname:
                    injected_types.add(tname)
            type_defs = "\n\n".join("\n".join(b) for b in filtered_blocks)

        if type_defs.strip():
            parts.append("\n// Type definitions from pure stdlib modules")
            parts.append(type_defs)
            # Add prove_lookup.h if injected content uses lookup table types
            if "Prove_LookupEntry" in type_defs or "Prove_IntLookupEntry" in type_defs:
                if '#include "prove_lookup.h"' not in c_source:
                    # Insert after last #include
                    for idx in range(insert_at - 1, -1, -1):
                        if lines[idx].startswith("#include"):
                            lines.insert(idx + 1, '#include "prove_lookup.h"')
                            inject_at += 1
                            break

    parts.append("\n// Forward declarations for pure stdlib modules")
    parts.append(decls)
    for j, part in enumerate(parts):
        lines.insert(inject_at + j, part)
    return "\n".join(lines)


# ── Unity build merging ──────────────────────────────────────────────


def _collect_brace_block(lines: list[str], start: int) -> tuple[list[str], int]:
    """Collect lines from *start* until braces balance.  Returns (block, next_index)."""
    block = [lines[start]]
    depth = lines[start].count("{") - lines[start].count("}")
    i = start + 1
    while i < len(lines) and depth > 0:
        block.append(lines[i])
        depth += lines[i].count("{") - lines[i].count("}")
        i += 1
    return block, i


_RE_STRUCT_DEF = re.compile(r"^struct\s+(\w+)\s*\{")
_RE_ENUM_DEF = re.compile(r"^enum\s+(\w+)\s*\{")
_RE_ANON_ENUM = re.compile(r"^enum\s*\{")
_RE_STATIC_INLINE = re.compile(r"^static\s+inline\s+\S+\s+(\w+)\s*\(")
# typedef forward declarations:  typedef struct Foo Foo;  /  typedef enum Foo Foo;
_RE_TYPEDEF_FWD = re.compile(r"^typedef\s+(?:struct|enum)\s+(\w+)\s+\w+\s*;$")
# typedef anonymous struct block:  typedef struct { ... } Name;
_RE_TYPEDEF_STRUCT_BLOCK = re.compile(r"^typedef\s+struct\s*\{")


def _build_unity_source(c_sources: list[str]) -> str:
    """Merge multiple C module sources into a single translation unit.

    Deduplicates #include directives, typedef forward declarations,
    struct/enum definitions, static-inline constructors, and extern
    declarations.  Static error-string names (``_err_str_N``) are made
    unique per module to avoid symbol collisions.
    """
    # 1. Make _err_str_ and _lambda_ names unique per module *before*
    #    merging so that both the definition and all references within
    #    each module agree.
    prefixed: list[str] = []
    for idx, src in enumerate(c_sources):
        src = src.replace("_err_str_", f"_err_str_m{idx}_")
        src = src.replace("_str_lit_", f"_str_lit_m{idx}_")
        src = src.replace("_lambda_", f"_lambda_m{idx}_")
        prefixed.append(src)

    seen_lines: set[str] = set()  # single-line dedup (includes, externs)
    seen_names: set[str] = set()  # typedef forward decl dedup by type name
    seen_blocks: set[str] = set()  # multi-line dedup key (struct/enum/inline name or content)
    out: list[str] = []

    for source in prefixed:
        lines = source.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # ── single-line dedup ────────────────────────────────
            if stripped.startswith("#include"):
                if stripped not in seen_lines:
                    seen_lines.add(stripped)
                    out.append(line)
                i += 1
                continue

            # typedef forward declarations — dedup by type name so
            # `typedef struct X X;` and `typedef enum X X;` don't clash.
            # Wrapped in guards to avoid conflict with runtime headers.
            m = _RE_TYPEDEF_FWD.match(stripped)
            if m:
                tname = m.group(1)
                if tname not in seen_names:
                    seen_names.add(tname)
                    guard = f"_PROVE_UNITY_{tname}"
                    out.append(f"#ifndef {guard}")
                    out.append(line)
                    out.append("#endif")
                i += 1
                continue

            # typedef struct { ... } Name;  (multi-line anonymous struct)
            if _RE_TYPEDEF_STRUCT_BLOCK.match(stripped):
                block, i = _collect_brace_block(lines, i)
                # Extract the typedef name after the closing brace
                last_line = block[-1].strip()
                # e.g.  "} _prv_detached_debug_String_args;"
                td_m = re.match(r"\}\s*(\w+)\s*;", last_line)
                key = td_m.group(1) if td_m else "\n".join(block)
                if key not in seen_blocks:
                    seen_blocks.add(key)
                    out.extend(block)
                continue

            if stripped.startswith("extern "):
                if stripped not in seen_lines:
                    seen_lines.add(stripped)
                    out.append(line)
                i += 1
                continue

            # ── multi-line struct definition ─────────────────────
            m = _RE_STRUCT_DEF.match(stripped)
            if m:
                name = m.group(1)
                block, i = _collect_brace_block(lines, i)
                if name not in seen_blocks:
                    seen_blocks.add(name)
                    guard = f"_PROVE_UNITY_{name}"
                    out.append(f"#ifndef {guard}")
                    out.append(f"#define {guard}")
                    out.extend(block)
                    out.append("#endif")
                continue

            # ── named enum definition ────────────────────────────
            m = _RE_ENUM_DEF.match(stripped)
            if m:
                name = m.group(1)
                block, i = _collect_brace_block(lines, i)
                if name not in seen_blocks:
                    seen_blocks.add(name)
                    guard = f"_PROVE_UNITY_{name}"
                    out.append(f"#ifndef {guard}")
                    out.append(f"#define {guard}")
                    out.extend(block)
                    out.append("#endif")
                continue

            # ── anonymous enum (algebraic type tags) ─────────────
            if _RE_ANON_ENUM.match(stripped):
                block, i = _collect_brace_block(lines, i)
                content_key = "\n".join(b.strip() for b in block)
                if content_key not in seen_blocks:
                    seen_blocks.add(content_key)
                    out.extend(block)
                continue

            # ── static inline constructors ───────────────────────
            m = _RE_STATIC_INLINE.match(stripped)
            if m:
                name = m.group(1)
                block, i = _collect_brace_block(lines, i)
                if name not in seen_blocks:
                    seen_blocks.add(name)
                    out.extend(block)
                continue

            # ── everything else passes through ───────────────────
            out.append(line)
            i += 1

    return "\n".join(out)
