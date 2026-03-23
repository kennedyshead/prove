# Prove Package Manager v1 — Implementation Plan

## Context

Prove needs a package manager to share pure-Prove libraries. Packages are distributed as pre-checked AST in SQLite files (`.prvpkg`), with no git dependency — just HTTP + Python stdlib. AST is tied to the Prove compiler version; cross-version support uses SQL migrations.

## Architecture Overview

```
prove.toml [dependencies]
  → resolve (registry HTTP) → prove.lock (pinned versions + SHA-256)
  → download .prvpkg to ~/.prove/cache/packages/
  → checker loads exports table (fast, no AST deser)
  → emitter loads module_ast blob (full deser for C emission)
```

A `.prvpkg` file IS a SQLite database:
- `meta` — name, version, prove_version
- `exports` — function/type/constant signatures (checker fast path)
- `strings` — string intern table for compact AST
- `module_ast` — binary AST blobs per module
- `dependencies` — declared package deps
- `assets` — comptime-resolved data (CSV, embedded text)

## Design Decisions

1. **No git dependency** — the package manager is self-contained, no shelling out to git. Pure Python stdlib only (`sqlite3`, `urllib`, `hashlib`, `json`, `struct`).
2. **AST tied to Prove version** — each package is built for a specific compiler version. Cross-version support via SQL migration files shipped with each Prove release.
3. **SQLite as the package file** — queryable, inspectable with standard tools, migration-friendly. The `.prvpkg` file IS a SQLite database.
4. **String-interned binary for AST blobs** — compact tagged-tuple format using `struct.pack`. Strings stored once in a `strings` table, referenced by ID. ~50% smaller than keyed JSON before compression.
5. **Static HTTP registry** — no API server needed. Can be hosted on any CDN, S3 bucket, or local directory.
6. **Flat dependency resolution** — each dependency name resolves to exactly one version across the entire tree. No diamond dependencies. Simple and predictable for v1.
7. **IO verbs allowed** — packages can use `inputs`/`outputs`. The safety boundary is `foreign` blocks (arbitrary C code), not IO.
8. **Comptime fully resolved at publish time** — all `comptime` expressions are evaluated before packaging. CSV data from `file("data.csv")` in binary lookup types is already materialized into `LookupEntry` AST nodes during parsing (`Parser._load_csv_entries`). `ComptimeExpr` bodies are evaluated during check/emit. By the time the AST is serialized, all comptime results are baked into the tree. The `assets` table stores any large raw data blobs that store-backed types need at runtime (e.g., pre-populated store tables). The publish step must: (a) run the full check+emit pipeline to resolve all comptime, (b) collect any store data files referenced by the module, (c) serialize the post-evaluation AST. Consumers never re-evaluate comptime — they get the final result.

---

## Phase 1: AST Serialization

**New file**: `prove-py/src/prove/ast_serial.py`

Serialize/deserialize `Module` AST to compact binary using string interning. Follows the recursive dataclass walk pattern from `cli.py:_dump_ast` (line 573).

**Key components**:
- `StringIntern` — bidirectional string table, serializes to/from bytes
- `_TAG_MAP: dict[type, int]` — one tag per concrete AST node (~45 types from `ast_nodes.py`)
- `serialize_module(module) → (bytes, StringIntern)` — walk dataclass fields, strip spans, intern strings, emit tagged tuples via `struct.pack`
- `deserialize_module(data, strings) → Module` — reconstruct with dummy `Span("<package>", 0, 0, 0, 0)`
- Lists: `(uint32 count, elements...)`, None: `TAG_NONE = 0xFF`, bools: `uint8`

**Tests**: `prove-py/tests/test_ast_serial.py`
- Roundtrip simple module, complex module (types, match, contracts)
- All node types have tag assignments (assert against ast_nodes unions)
- Spans stripped in output

---

## Phase 2: Package Format (`.prvpkg` SQLite)

**New file**: `prove-py/src/prove/package.py`

Create and read `.prvpkg` SQLite databases.

**SQLite schema**:
```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE exports (
    module TEXT, kind TEXT, name TEXT, verb TEXT,
    params TEXT, return_type TEXT, can_fail INTEGER, doc TEXT
);
CREATE TABLE strings (id INTEGER PRIMARY KEY, value TEXT);
CREATE TABLE module_ast (module TEXT PRIMARY KEY, data BLOB);
CREATE TABLE dependencies (name TEXT, version_constraint TEXT);
CREATE TABLE assets (key TEXT PRIMARY KEY, data BLOB);
```

**Key functions**:
- `create_package(output_path, meta, modules, dependencies, assets) → Path`
  - Creates SQLite DB, serializes each module's AST, extracts exports from parsed AST, stores everything
- `read_package(pkg_path) → PackageInfo` — metadata + exports, no AST deser
- `load_package_module(pkg_path, module_name) → Module` — full AST deser for emit
- `extract_signatures(pkg_path, module_name) → list[FunctionSignature]` — fast path from exports table
- `extract_types(pkg_path, module_name) → dict[str, Type]` — types from exports

**Comptime handling**: The `create_package` function receives **post-evaluation** AST — all `ComptimeExpr` nodes have been resolved, all `file("data.csv")` calls in `LookupTypeDef` have been materialized into `LookupEntry` lists. Any store-backed type data files (from `is_store_backed = True` lookup types) are collected and stored in the `assets` table as raw blobs keyed by their original path. During `load_package_module`, assets are extracted to a temp directory so the emitter can reference them.

**Reuses**: `FunctionSignature` from `symbols.py` (line 35), type resolution patterns from `stdlib_loader.py:load_stdlib` (line 940)

**Tests**: `prove-py/tests/test_package.py`
- Create → read roundtrip, signature extraction matches checker output, assets stored/retrieved
- Package with CSV-backed lookup type preserves all entries
- Package with store-backed type preserves asset data

**Depends on**: Phase 1

---

## Phase 3: Config & Lockfile

**Modified file**: `prove-py/src/prove/config.py`
- Add `DependencyConfig(name, version_constraint)` dataclass
- Add `dependencies: list[DependencyConfig]` to `ProveConfig` (default: `[]`)
- Parse `[dependencies]` section in `load_config()` (after line 140)
- Add `write_dependency()` / `remove_dependency()` helpers for CLI commands

**New file**: `prove-py/src/prove/lockfile.py`
- `LockedPackage(name, version, checksum, source)` dataclass
- `Lockfile(prove_version, packages)` dataclass
- `read_lockfile(path) → Lockfile | None` — parse TOML
- `write_lockfile(path, lockfile)` — emit TOML via string template (no writer lib needed)
- `lockfile_is_stale(lockfile, dependencies) → bool`

**Manifest** (`prove.toml`):
```toml
[dependencies]
json-utils = "0.3.0"
text-helpers = ">=0.2.0"
```

**Lockfile** (`prove.lock`):
```toml
prove_version = "1.1.0"

[[package]]
name = "json-utils"
version = "0.3.0"
checksum = "sha256:abc123..."
source = "https://registry.prove-lang.org/packages/json-utils/0.3.0.prvpkg"
```

**Tests**: `prove-py/tests/test_lockfile.py` + additions to `test_cli.py`

---

## Phase 4: Registry Client

**New file**: `prove-py/src/prove/registry.py`

HTTP client following `nlp_store.py:download_stores` pattern (urllib, no exceptions, returns None on failure).

**Key functions**:
- `fetch_package_info(name, registry_url) → RegistryPackageInfo | None`
- `download_package(name, version, registry_url) → Path | None` — downloads to `~/.prove/cache/packages/{name}/{version}.prvpkg`
- `verify_checksum(pkg_path, expected_sha256) → bool`
- `compute_checksum(pkg_path) → str`
- `cache_dir() → Path` (`~/.prove/cache/packages/`)
- `clear_cache() → int`

**Registry layout** (static HTTP):
```
{registry}/packages/{name}/index.json
{registry}/packages/{name}/{version}.prvpkg
```

**Tests**: `prove-py/tests/test_registry.py` — mock `urllib.request.urlopen`

**Depends on**: Phase 2, 3

---

## Phase 5: Dependency Resolution

**New file**: `prove-py/src/prove/resolver.py`

Flat resolver — each dependency name resolves to exactly one version across the entire tree.

**Key components**:
- `VersionConstraint` — parses `"0.3.0"`, `">=0.2.0"`, `">=0.1.0,<1.0.0"`, `"^0.2.0"`
- `resolve(dependencies, registry_url, existing_lock) → Lockfile | list[ResolveError]`
  - For each dep: if locked version satisfies constraint, keep it; else fetch index, pick latest match
  - Read transitive deps from downloaded `.prvpkg`'s dependencies table
  - Conflict = same name, incompatible versions → error

**Tests**: `prove-py/tests/test_resolver.py`

**Depends on**: Phase 3, 4

---

## Phase 6: Import Resolution Integration

This is the critical phase connecting packages to the compiler.

**New file**: `prove-py/src/prove/package_loader.py`
- `PackageModuleInfo(package_name, package_version, module_name, types, functions, constants, pkg_path)`
- `load_installed_packages(project_dir, lockfile) → dict[str, PackageModuleInfo]` — reads exports tables only
- `load_package_for_emit(pkg_info) → tuple[Module, SymbolTable]` — full AST deser for C emission

**Modified file**: `prove-py/src/prove/checker.py`
- Add `package_modules: dict[str, PackageModuleInfo] | None = None` param to `Checker.__init__`
- In `_register_import()` (line 994-1007), insert package resolution between local and "unknown":
  ```python
  # Line ~998, after local check fails:
  if self._package_modules and imp.module in self._package_modules:
      self._register_package_import(imp)
      return
  ```
- New method `_register_package_import(imp)` — mirrors `_register_local_import` but reads from `PackageModuleInfo`

**Modified file**: `prove-py/src/prove/builder.py`
- After `build_module_registry()` (line 258), load packages:
  ```python
  lockfile = read_lockfile(project_dir / "prove.lock")
  package_modules = load_installed_packages(project_dir, lockfile) if lockfile else None
  ```
- Pass `package_modules=package_modules` to both `Checker()` calls (lines 274, 286)
- After `_compile_pure_stdlib()` (line 303), add `_compile_package_modules()` — deserializes package ASTs, runs checker+emitter, adds to modules_and_symbols

**Resolution order**: local → package → stdlib (package takes priority over stdlib to allow overrides; stdlib shadowing warning via E316 extended to packages)

**Tests**: `prove-py/tests/test_package_loader.py`
- Checker resolves package imports, package type imports, full build with mock .prvpkg

**Depends on**: Phase 2, 3, 5

---

## Phase 7: CLI Commands

**Modified file**: `prove-py/src/prove/cli.py`

Add `prove package` Click group:

```
prove package init                  — add [dependencies] to prove.toml
prove package add <name> [version]  — add dep, resolve, download, update lock
prove package remove <name>         — remove dep, re-resolve, update lock
prove package install               — fetch all deps from lockfile
prove package publish [--dry-run]   — validate purity, create .prvpkg
prove package list                  — show dependency tree
prove package clean                 — clear ~/.prove/cache/packages/
```

**Publish pipeline**:
1. Run `prove check` on the project (ensures all comptime is evaluable, types check)
2. Run `prove build --dry-run` equivalent to fully resolve comptime expressions and materialize CSV/store data
3. Validate purity: no `ForeignBlock` nodes in any `ModuleDecl.foreign_blocks`
4. Validate imports: all resolve to stdlib or declared `[dependencies]`
5. IO verbs allowed
6. Collect store-backed data files for the `assets` table
7. Serialize post-evaluation AST into `.prvpkg`

**Tests**: additions to `prove-py/tests/test_cli.py`

**Depends on**: All previous phases

---

## Phase 8: AST Migrations

**New directory**: `prove-py/src/prove/migrations/`
- `__init__.py` with `MIGRATIONS: dict[str, list[str]]` mapping `from_version → SQL statements`
- `get_migration_path(from_version, to_version) → list[str]`
- `migrate_package(pkg_path, target_version) → bool`

Each Prove release adds migration entries. Migrations are SQL `ALTER TABLE` / `UPDATE` on the `.prvpkg` SQLite schema.

**Modified**: `package_loader.py` checks `prove_version` on load, applies migrations if needed.

**Tests**: `prove-py/tests/test_migrations.py`

**Depends on**: Phase 2, 6

---

## File Summary

### New files (8 source + 6 test)
| File | Phase |
|------|-------|
| `prove-py/src/prove/ast_serial.py` | 1 |
| `prove-py/src/prove/package.py` | 2 |
| `prove-py/src/prove/lockfile.py` | 3 |
| `prove-py/src/prove/registry.py` | 4 |
| `prove-py/src/prove/resolver.py` | 5 |
| `prove-py/src/prove/package_loader.py` | 6 |
| `prove-py/src/prove/migrations/__init__.py` | 8 |
| `prove-py/tests/test_ast_serial.py` | 1 |
| `prove-py/tests/test_package.py` | 2 |
| `prove-py/tests/test_lockfile.py` | 3 |
| `prove-py/tests/test_registry.py` | 4 |
| `prove-py/tests/test_resolver.py` | 5 |
| `prove-py/tests/test_package_loader.py` | 6 |
| `prove-py/tests/test_migrations.py` | 8 |

### Modified files (4)
| File | Phase | Change |
|------|-------|--------|
| `prove-py/src/prove/config.py` | 3 | `DependencyConfig`, `[dependencies]` parsing |
| `prove-py/src/prove/checker.py` | 6 | `package_modules` param, `_register_package_import()` |
| `prove-py/src/prove/builder.py` | 6 | Load packages, pass to checker, compile package ASTs |
| `prove-py/src/prove/cli.py` | 7 | `prove package` command group (7 subcommands) |

## What's NOT in v1

- C-extension packages (need a separate `[native]` section)
- Private registries with auth
- Workspaces / monorepo support
- Semver constraint solver (just flat resolution)
- Package yanking / deprecation
- Signed packages

## Verification

After each phase, run:
```bash
cd prove-py && python -m pytest tests/ -v -k "test_ast_serial or test_package or test_lockfile or test_registry or test_resolver or test_package_loader or test_migrations"
```

After Phase 7 (full integration):
```bash
python -m pytest tests/ -v          # all unit tests
python scripts/test_e2e.py          # e2e (ensure no regressions)
```

Manual smoke test: create a two-project setup where project A publishes a package and project B depends on it, then `prove build` project B.
