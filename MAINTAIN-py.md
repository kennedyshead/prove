# Consolidate Runtime Metadata

## Context

Adding a new C runtime module currently requires updates in **4 places across 2 files**:
1. `c_runtime.py` — `_RUNTIME_FILES` list (add `.h` and `.c` entries)
2. `c_runtime.py` — `_RUNTIME_FUNCTIONS` dict (add function mappings)
3. `optimizer.py` — `_STDLIB_RUNTIME_LIBS` dict (add Prove module → C lib mapping)
4. `c_runtime.py` — hardcoded `needed_files.add()` block (if it's a core dependency)

This is error-prone and will get worse as stdlib grows. Goal: reduce to **1 step in 1 file** for the common case.

## Plan

### Step 1: Auto-discover `_RUNTIME_FILES` from the package

Replace the hardcoded 42-entry `_RUNTIME_FILES` list with a scan of the `prove.runtime` package:

```python
def _discover_runtime_files() -> list[str]:
    pkg = importlib.resources.files("prove.runtime")
    files = []
    for item in pkg.iterdir():
        name = item.name
        if name.startswith("prove_") and name.endswith((".c", ".h")):
            files.append(name)
    return sorted(files)

_RUNTIME_FILES = _discover_runtime_files()
```

New modules are found automatically just by dropping files into `prove/runtime/`.

### Step 2: Extract `_CORE_FILES` set

Replace the 18-line `needed_files.add(...)` block with a constant:

```python
_CORE_FILES = {
    "prove_runtime", "prove_arena", "prove_region", "prove_string",
    "prove_hash", "prove_intern", "prove_list", "prove_option",
    "prove_result", "prove_text",
}
```

The stripping logic expands these to `.h`/`.c` pairs. Clearer what's always included.

### Step 3: Move `_STDLIB_RUNTIME_LIBS` to `c_runtime.py`

Move the mapping from `optimizer.py` into `c_runtime.py` and rename to `STDLIB_RUNTIME_LIBS` (public). Keep the same dict structure but co-locate it with `_RUNTIME_FUNCTIONS` so they're maintained together:

```python
STDLIB_RUNTIME_LIBS: dict[str, set[str]] = {
    "io": {"prove_input_output"},
    "inputoutput": {"prove_input_output"},
    "character": {"prove_character"},
    "text": {"prove_text", "prove_string"},
    "table": {"prove_table", "prove_hash"},
    "parse": {"prove_parse"},
    "math": {"prove_math"},
    "convert": {"prove_convert"},
    "list": {"prove_list", "prove_list_ops"},
    "format": {"prove_format"},
    "path": {"prove_path"},
    "error": {"prove_error"},
    "pattern": {"prove_pattern"},
    "result": {"prove_result"},
    "option": {"prove_option"},
}
```

### Step 4: Update `optimizer.py` to import from `c_runtime`

Replace the local `_STDLIB_RUNTIME_LIBS` with:
```python
from prove.c_runtime import STDLIB_RUNTIME_LIBS
```

Update `RuntimeDeps.add_module()` to reference `STDLIB_RUNTIME_LIBS` instead of the deleted local dict.

### Step 5: Simplify `copy_runtime()` stripping logic

Use `_CORE_FILES` set to build the always-included list:
```python
for base in _CORE_FILES:
    needed_files.update(n for n in _RUNTIME_FILES if base in n)
```

## Files Modified

| File | Change |
|------|--------|
| `prove-py/src/prove/c_runtime.py` | Auto-discover files, extract `_CORE_FILES`, add `STDLIB_RUNTIME_LIBS` |
| `prove-py/src/prove/optimizer.py` | Delete `_STDLIB_RUNTIME_LIBS`, import from `c_runtime` |

## Result

Adding a new runtime module (e.g. `prove_network`):
1. Drop `prove_network.h` and `prove_network.c` into `prove/runtime/`
2. Add function mappings to `_RUNTIME_FUNCTIONS` in `c_runtime.py`
3. Add module name entry to `STDLIB_RUNTIME_LIBS` in `c_runtime.py`

All in **1 file**. File list auto-discovers. Core files are a clear constant.

## Verification

- `python3 -m pytest tests/ -v` — all tests pass
- `ruff check src/prove/c_runtime.py src/prove/optimizer.py` — no lint issues
- Build an example program to verify runtime stripping still works
