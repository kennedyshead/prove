# Cache Indexing & Reindexing

Reliable `.prove_cache` lifecycle across LSP, `check`, `build`, and `format` commands.
Today the cache is written but never read back, staleness is never detected, and CLI
commands know nothing about it.

---

## Background: what exists today

### Cache location and format

`<project-root>/.prove_cache/`
```
bigrams/current.bin       PDAT file: prev1 | next | count
completions/current.bin   PDAT file: prev2 | prev1 | top_completions_pipe_separated
```

Written by `_ProjectIndexer.save()` → `_write_bigrams_cache()` / `_write_completions_cache()`
using `store_binary.write_pdat` (PDAT magic `0x50444154`, format version `1`).

### What the indexer does today

**`_ProjectIndexer` in `lsp.py`:**
- `index_all_files()` — walks all `.prv` files, calls `index_file()` for each, then `save()`
- `patch_file(path, source)` — removes file's old contribution, re-extracts, saves
- `save()` — writes PDAT files; silently swallows all errors (`pass`)
- **Never reads the cache back.** The in-memory tables are rebuilt from scratch every LSP
  session from source files. The PDAT files are written but ignored by the indexer itself
  (they exist for the global model loader at startup, not for session reuse).

### LSP session flow (`lsp.py`)

```python
# did_open (line 862):
_analyze(uri, source)            # lex → parse → check
_ensure_project_indexed(uri)     # create indexer + index_all_files() if empty

# did_change (line 879):
_analyze(uri, source)            # re-check; does NOT patch indexer

# did_save (line 898):
_project_indexer.patch_file(...)  # incremental re-index on save
```

**Gap:** `did_change` never patches the indexer, so completions lag one save behind edits.

### CLI commands today

| Command | Knows about cache | Triggers indexing |
|---|---|---|
| `check` | No | No |
| `build` | No | No |
| `format` | No | No |

`_compile_project` in `cli.py` (line 97) walks `.prv` files, runs lex→parse→check per file,
and has no connection to `_ProjectIndexer`.

---

## Problems to solve

1. **Cold start** — `.prove_cache` missing (fresh clone, first run, `.gitignore`d). LSP
   calls `index_all_files()` which re-parses everything synchronously on `did_open`.
   CLI commands do nothing.

2. **Stale cache** — `.prv` files have been modified since the cache was written (e.g.
   after a `git pull` with the editor closed). The indexer never compares file mtimes
   against cache mtime, so it may serve stale completions.

3. **Corrupt / incompatible cache** — PDAT magic or version mismatch (format change),
   truncated write, or disk error. Currently `save()` silently ignores write errors and
   the global model loader's `_parse_lookup_rows` silently skips malformed lines.

4. **CLI blind spot** — `check` and `build` parse every `.prv` file but throw away the
   parse results without updating the cache. A developer who only uses the CLI never gets
   a warm cache for the LSP.

5. **`did_change` lag** — completions don't reflect unsaved edits.

---

## What to build

### Part 1 — Cache validity metadata

Add a manifest file alongside the PDAT files:

```
.prove_cache/
  manifest.json          ← new
  bigrams/current.bin
  completions/current.bin
```

**`manifest.json` schema:**
```json
{
  "cache_version": 2,
  "indexed_at": 1741612800,
  "files": {
    "src/main.prv":   { "mtime": 1741612700, "size": 4096 },
    "src/helpers.prv": { "mtime": 1741612650, "size": 1024 }
  }
}
```

`cache_version` is bumped whenever the PDAT schema or indexer extraction logic changes.
Current format version (`PDAT_VERSION = 1` in `store_binary.py`) stays independent —
`cache_version` tracks indexer semantics, not binary format.

#### New helpers in `_ProjectIndexer` (lsp.py)

```python
_CACHE_VERSION = 2   # bump when extraction logic changes

def _manifest_path(self) -> Path:
    return self.cache_dir / "manifest.json"

def _write_manifest(self) -> None:
    import json, time
    files = {}
    for path_str in self._file_ngrams:
        p = Path(path_str)
        try:
            st = p.stat()
            files[str(p.relative_to(self.project_root))] = {
                "mtime": int(st.st_mtime),
                "size": st.st_size,
            }
        except OSError:
            pass
    manifest = {
        "cache_version": _CACHE_VERSION,
        "indexed_at": int(time.time()),
        "files": files,
    }
    self._manifest_path().write_text(json.dumps(manifest, indent=2), encoding="utf-8")

def _read_manifest(self) -> dict | None:
    import json
    try:
        data = json.loads(self._manifest_path().read_text(encoding="utf-8"))
        if data.get("cache_version") != _CACHE_VERSION:
            return None   # incompatible version → treat as missing
        return data
    except Exception:
        return None

def is_cache_valid(self) -> bool:
    """True if manifest exists, version matches, and all tracked files are unchanged."""
    manifest = self._read_manifest()
    if manifest is None:
        return False
    files = manifest.get("files", {})
    if not files:
        return False
    for rel, info in files.items():
        p = self.project_root / rel
        try:
            st = p.stat()
            if int(st.st_mtime) != info["mtime"] or st.st_size != info["size"]:
                return False
        except OSError:
            return False   # file deleted → stale
    # Also check for new .prv files not in manifest
    for prv in self.project_root.rglob("*.prv"):
        if ".prove_cache" in prv.parts:
            continue
        rel = str(prv.relative_to(self.project_root))
        if rel not in files:
            return False   # new file → stale
    return True
```

Update `save()` to also call `_write_manifest()`:

```python
def save(self) -> None:
    try:
        self._write_bigrams_cache()
        self._write_completions_cache()
        self._write_manifest()
    except Exception:
        pass
```

---

### Part 2 — Cache load-back (warm start)

Currently the indexer never reads the PDAT files back. When the cache is valid we should
restore in-memory tables from disk instead of re-parsing all source files.

```python
def load(self) -> bool:
    """Restore in-memory tables from cache. Returns True on success."""
    try:
        from prove.store_binary import read_pdat   # needs a new reader (see below)
        bigrams_path = self.cache_dir / "bigrams" / "current.bin"
        completions_path = self.cache_dir / "completions" / "current.bin"
        if not bigrams_path.exists() or not completions_path.exists():
            return False
        for _, row in read_pdat(bigrams_path):
            prev1, nxt, count = row[0], row[1], int(row[2])
            self._bigrams[prev1][nxt] = count
        for _, row in read_pdat(completions_path):
            p2, p1, top = row[0], row[1], row[2]
            for tok in top.split("|"):
                if tok:
                    self._completions[(p2, p1)][tok] += 1
        # Rebuild symbol table from manifest file list (re-parse symbols only — cheap)
        manifest = self._read_manifest()
        if manifest:
            for rel in manifest["files"]:
                p = self.project_root / rel
                _, symbols = self._extract_file(p)
                for sym in symbols:
                    self._symbols[sym["name"]] = sym
                self._file_ngrams[str(p)] = []   # mark as indexed (no ngrams needed)
                self._file_symbols[str(p)] = symbols
        return True
    except Exception:
        return False
```

`read_pdat` is a new function in `store_binary.py` — symmetric with `write_pdat`:

```python
def read_pdat(path: str | Path) -> list[tuple[str, list[str]]]:
    """Read a PDAT file and return [(variant_name, [col_values...]), ...]."""
    with open(path, "rb") as f:
        magic, version = struct.unpack("<II", f.read(8))
        if magic != PDAT_MAGIC:
            raise ValueError(f"bad PDAT magic: {magic:#x}")
        _data_version = struct.unpack("<q", f.read(8))[0]
        col_count = struct.unpack("<q", f.read(8))[0]
        columns = []
        for _ in range(col_count):
            n = struct.unpack("<I", f.read(4))[0]
            columns.append(f.read(n).decode("utf-8"))
        variant_count = struct.unpack("<q", f.read(8))[0]
        rows = []
        for _ in range(variant_count):
            n = struct.unpack("<I", f.read(4))[0]
            name = f.read(n).decode("utf-8")
            values = []
            for _ in columns:
                vn = struct.unpack("<I", f.read(4))[0]
                values.append(f.read(vn).decode("utf-8"))
            rows.append((name, values))
    return rows
```

---

### Part 3 — `_ensure_project_indexed` rewrite

Replace the current unconditional `index_all_files()` call:

```python
def _ensure_project_indexed(uri: str) -> None:
    global _project_indexer
    if _project_indexer is None:
        _project_indexer = _ProjectIndexer.for_uri(uri)
    if _project_indexer is None:
        return
    if _project_indexer._file_ngrams:
        return   # already populated this session

    # Try warm load first
    if _project_indexer.is_cache_valid():
        if _project_indexer.load():
            return   # warm start — no file parsing needed

    # Cache missing, stale, or corrupt → full reindex
    _project_indexer.index_all_files()
```

---

### Part 4 — `did_change` patch

Wire incremental re-index on every content change, not just on save:

```python
@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
    uri = params.text_document.uri
    source = params.content_changes[-1].text if params.content_changes else ""
    ds = _analyze(uri, source)
    server.text_document_publish_diagnostics(...)

    # Patch indexer with unsaved content so completions reflect current edits
    if _project_indexer is not None and uri.startswith("file://"):
        path = Path(uri[7:])
        if path.suffix == ".prv":
            try:
                _project_indexer.patch_file(path, source)
            except Exception:
                pass
```

Note: `patch_file` already calls `save()`, which writes to disk on every change. This
is acceptable for small projects; for large ones a debounce could be added later.

---

### Part 5 — CLI integration

#### `check` and `build`: update cache after a successful run

Both commands already parse all `.prv` files. After processing, update the cache using
the same `_ProjectIndexer` machinery (no extra parsing needed — reuse the tokens/modules
already produced).

Add a shared helper `_update_project_cache(project_dir, prv_files)` in `cli.py`:

```python
def _update_project_cache(project_dir: Path) -> None:
    """Rebuild .prove_cache after a check or build run."""
    try:
        indexer = _ProjectIndexer(project_dir)
        indexer.index_all_files()   # parses all files; cheap relative to compile
    except Exception:
        pass   # cache update is always non-fatal
```

Call it at the end of `check` and `build` (only on success or partial success — always
try even if there are errors, since partial data is better than stale data):

```python
# In check(), after _compile_project():
_update_project_cache(project_dir)

# In build(), after build_project():
_update_project_cache(project_dir)
```

#### `format`: update cache when files change

`format_cmd` rewrites source files. A rewritten file invalidates its cache entry.
After formatting, patch just the changed files:

```python
# In format_cmd(), after writing formatted content back to disk:
try:
    indexer = _ProjectIndexer(_find_project_root(target))
    for changed_path in changed_files:
        indexer.patch_file(changed_path, changed_source)
except Exception:
    pass
```

`_find_project_root` already exists as `_ProjectIndexer._find_root` — expose as a
module-level function or inline the `prove.toml` walk.

---

### Part 6 — `prove index` CLI subcommand (optional, user-facing)

A new explicit command for warm-up scripts and CI:

```
prove index [path]   — (re)build .prove_cache for the project at path
```

```python
@cli.command("index")
@click.argument("path", default=".")
def index_cmd(path: str) -> None:
    """Rebuild the .prove_cache ML completion index."""
    from prove.config import find_config, load_config
    config_path = find_config(Path(path))
    project_dir = config_path.parent
    click.echo("indexing...")
    indexer = _ProjectIndexer(project_dir)
    indexer.index_all_files()
    click.echo(f"indexed {len(indexer._file_ngrams)} files → {project_dir / '.prove_cache'}")
```

Useful for:
- First run after `git clone` before opening the editor
- CI pre-warming (cache checked in or artifact-cached between runs)
- Forcing a reindex after a large rebase

---

## Files changed

| File | Change |
|---|---|
| `prove-py/src/prove/store_binary.py` | Add `read_pdat()` function |
| `prove-py/src/prove/lsp.py` | `_ProjectIndexer`: add `_CACHE_VERSION`, `_write_manifest`, `_read_manifest`, `is_cache_valid`, `load`; update `save`; rewrite `_ensure_project_indexed`; patch `did_change` |
| `prove-py/src/prove/cli.py` | Add `_update_project_cache()`; call from `check` and `build`; patch `format_cmd`; add `index` subcommand |
| `prove-py/tests/test_lsp.py` | Tests for `is_cache_valid`, `load`, warm-start path |
| `prove-py/tests/test_store_binary.py` | Tests for `read_pdat` round-trip |

No changes to checker, parser, lexer, emitter, or C runtime.

---

## Staleness decision table

| Condition | Action |
|---|---|
| `.prove_cache/` missing | Full reindex |
| `manifest.json` missing | Full reindex |
| `cache_version` mismatch | Full reindex |
| Any tracked file mtime/size changed | Full reindex |
| New `.prv` file not in manifest | Full reindex |
| Tracked file deleted | Full reindex |
| All checks pass | Warm load from PDAT |
| PDAT read fails (corrupt) | Fall back to full reindex |
