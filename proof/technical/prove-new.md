# `prove new` — Complete Flow

Step-by-step description of what happens from CLI invocation to final output.

---

## CLI Entry Point

**Command:** `prove new <name>`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | positional | yes | Name of the new project directory |

**Source:** `cli.py` → `new()` function

---

## Step 1 — Call `scaffold()`

```
cli.py → project.py → scaffold(name)
```

### 1a. Resolve base directory

```python
base = Path.cwd()
project_dir = base / name
```

- Uses the current working directory as parent
- Project will be created at `./<name>/`

### 1b. Check for conflicts

```python
if project_dir.exists():
    raise FileExistsError(f"Directory '{name}' already exists")
```

- **If directory exists:** raises `FileExistsError` → CLI prints `"error: Directory '<name>' already exists"` → exit 1

---

## Step 2 — Create directory structure

```
project.py lines 52-53
```

Creates the following directory tree:

```
<name>/
└── src/
```

- `src_dir.mkdir(parents=True)` creates both `<name>/` and `<name>/src/` in one call

---

## Step 3 — Write `prove.toml`

```
project.py line 56
```

Writes `<name>/prove.toml` with contents:

```toml
[package]
name = "<name>"
version = "0.1.0"
authors = []
license = ""

[build]
target = "native"
optimize = true

[test]
property_rounds = 1000

[style]
line_length = 90
```

- The `name` field is interpolated from the CLI argument

---

## Step 4 — Write `src/main.prv`

```
project.py line 59
```

Writes `<name>/src/main.prv` with a starter module:

```prove
module Main
  narrative: """A new Prove project."""
  InputOutput outputs console

main() Result<Unit, Error>!
from
    console("Hello from Prove!")
```

---

## Step 5 — Write `.gitignore`

```
project.py line 62
```

Writes `<name>/.gitignore`:

```
build/
__pycache__/
.prove/
```

---

## Step 6 — Copy LICENSE (optional)

```
project.py lines 65-67 → _find_license()
```

Searches for a LICENSE file to copy into the new project:

1. Try `<prove-py-package>/../../LICENSE` (two levels up from the Python package)
2. Try `<current-working-directory>/LICENSE`
3. **If found:** copies it to `<name>/LICENSE` via `shutil.copy2` (preserves metadata)
4. **If not found:** no LICENSE file is created (silently skipped)

---

## Step 7 — Final output

```
cli.py line 505
```

```
created project '<name>' at <absolute-path-to-project-dir>
```

---

## Error Paths

| Condition | Output | Exit code |
|-----------|--------|-----------|
| Directory already exists | `error: Directory '<name>' already exists` | 1 |
| Success | `created project '<name>' at <path>` | 0 |

---

## Complete Pipeline Diagram

```
prove new <name>
│
├─ scaffold(name)
│  ├─ Resolve base = cwd(), project_dir = base / name
│  ├─ [if exists] → raise FileExistsError
│  ├─ mkdir -p <name>/src/
│  ├─ Write <name>/prove.toml (with name interpolated)
│  ├─ Write <name>/src/main.prv (starter template)
│  ├─ Write <name>/.gitignore
│  └─ [if LICENSE found] Copy LICENSE to <name>/LICENSE
│
└─ Print: created project '<name>' at <path>
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point, error handling |
| `project.py` | Project scaffolding (`scaffold`, templates) |

---

## Generated Project Structure

```
<name>/
├── .gitignore
├── LICENSE          (if source LICENSE found)
├── prove.toml
└── src/
    └── main.prv
```
