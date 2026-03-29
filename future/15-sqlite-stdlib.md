# Prove Sqlite Stdlib — Implementation Plan

## Context

Prove needs general-purpose SQLite database access for user programs. The existing Store module provides a custom key-value binary format, but users need direct relational database access. SQLite is ubiquitous, requires no server, and fits Prove's self-contained philosophy. Targeted for V1.2 alongside the package manager.

---

## Types

| Prove Type | C Type | Wraps | Purpose |
|------------|--------|-------|---------|
| `Database` | `Prove_Database` | `sqlite3*` | Connection handle |
| `Statement` | `Prove_Statement` | `sqlite3_stmt*` | Prepared, reusable statement |
| `Cursor` | `Prove_Cursor` | stepping `sqlite3_stmt*` | Single-pass, forward-only result iterator |
| `Row` | `Prove_Row` | column names + values | Snapshot of one result row |

---

## API

### Database lifecycle

```prove
/// Open a SQLite database at the given file path
inputs database(path String) Result<Database, Error>!

/// Open an in-memory SQLite database
creates database() Result<Database, Error>!

/// Close a database connection
outputs database(db Database)

/// Check if a database connection is open
validates database(db Database)
```

### Execute (no result rows)

```prove
/// Execute a SQL statement (CREATE, INSERT, UPDATE, DELETE)
outputs execute(db Database, sql String) Result<Unit, Error>!

/// Execute with bound parameters (prevents SQL injection)
outputs execute(db Database, sql String, params List<String>) Result<Unit, Error>!
```

### Query (returns Cursor)

```prove
/// Query rows — returns a cursor for iteration
inputs query(db Database, sql String) Result<Cursor, Error>!

/// Query with bound parameters
inputs query(db Database, sql String, params List<String>) Result<Cursor, Error>!
```

### Prepared statements

```prove
/// Prepare a SQL statement for repeated execution
creates statement(db Database, sql String) Result<Statement, Error>!

/// Execute a prepared statement with bound parameters
outputs statement(stmt Statement, params List<String>) Result<Unit, Error>!

/// Query from a prepared statement with bound parameters
inputs statement(stmt Statement, params List<String>) Result<Cursor, Error>!

/// Finalize (release) a prepared statement
outputs finalize(stmt Statement)
```

### Transactions

```prove
/// Begin a transaction
outputs begin(db Database) Result<Unit, Error>!

/// Commit a transaction
outputs commit(db Database) Result<Unit, Error>!

/// Rollback a transaction
outputs rollback(db Database) Result<Unit, Error>!
```

### WAL mode

```prove
/// Enable WAL journal mode for better concurrent read performance
outputs wal(db Database) Result<Unit, Error>!
```

### Row access

```prove
/// Read a column value by name
reads column(row Row, name String) Result<String, Error>!

/// Read a column value by index
reads column(row Row, index Integer) Result<String, Error>!

/// Get column names from a row
reads columns(row Row) List<String>
```

### Cursor iteration

`Cursor` is iterable — the builtin HOFs (`map`, `filter`, `each`, `reduce`) work on it directly. The compiler handles dispatch; no HOF declarations needed in this module.

```prove
// Example: iterate with builtins
rows as Cursor = query(db, "SELECT name FROM users")!
each(rows, |row| console(column(row, "name")!))
names as List<String> = map(rows, |row| column(row, "name")!)
```

### Changes

```prove
/// Get number of rows changed by last INSERT/UPDATE/DELETE
reads changes(db Database) Integer
```

---

## Usage Example

```prove
module Main
  Sqlite inputs database, query, each
  Sqlite derives column, changes
  Sqlite outputs execute, begin, commit, database
  System outputs console

main() Result<Unit, Error>!
from
    db as Database = database(":memory:")!
    execute(db, "CREATE TABLE users (name TEXT, age INTEGER)")!

    begin(db)!
    execute(db, "INSERT INTO users VALUES (?, ?)", ["Alice", "30"])!
    execute(db, "INSERT INTO users VALUES (?, ?)", ["Bob", "25"])!
    commit(db)!

    rows as Cursor = query(db, "SELECT name, age FROM users")!
    each(rows, |row| console(column(row, "name")!))

    database(db)
```

---

## SQLite Dependency — Vendor the Amalgamation

SQLite is **public domain** (explicit public domain dedication, not even a license). This is the same licensing status as the vendored Nuklear GUI library.

**Approach:** Vendor `sqlite3.c` + `sqlite3.h` into `prove-py/src/prove/runtime/vendor/`.

- Same pattern as Nuklear (`vendor/nuklear.h`, 1.1M)
- Amalgamation is ~250KB of C source
- Compiles as part of the Prove runtime — no external dependency
- No `-lsqlite3`, no `pkg_config`, no system library requirement
- Users get SQLite support out of the box with zero setup

---

## C Runtime

### Types (`prove_sqlite.h`)

```c
typedef struct {
    Prove_Header  header;
    sqlite3      *db;
} Prove_Database;

typedef struct {
    Prove_Header   header;
    sqlite3_stmt  *stmt;
    Prove_Database *db;      /* back-ref prevents premature GC */
} Prove_Statement;

typedef struct {
    Prove_Header   header;
    sqlite3_stmt  *stmt;
    Prove_Database *db;      /* back-ref */
    bool           done;     /* true after SQLITE_DONE */
} Prove_Cursor;

typedef struct {
    Prove_Header    header;
    int64_t         column_count;
    Prove_String  **column_names;
    Prove_String  **values;  /* NULL for SQL NULL */
} Prove_Row;
```

### Implementation notes (`prove_sqlite.c`)

- `_sqlite_error(sqlite3 *db)` — wraps `sqlite3_errmsg()` into `prove_result_err()`
- `Prove_Statement` and `Prove_Cursor` hold a back-reference to `Prove_Database` via `prove_retain()`, preventing the database from being freed while statements/cursors exist
- Cursor exposes a `prove_sqlite_cursor_next()` function returning the next `Prove_Row*` (or `NULL` when done) — the builtin HOF runtime calls this to iterate
- `Prove_Row` copies column names and values as `Prove_String*` at step time (snapshot, not live reference)
- All allocation via `prove_alloc()`, never `malloc()`

### Estimated size

~350-400 lines of C for the full implementation.

---

## Registration

### `stdlib_loader.py`

```python
_register_module(
    "sqlite",
    display="Sqlite",
    prv_file="sqlite.prv",
    c_map={
        ("inputs", "database"): "prove_sqlite_database_inputs",
        ("creates", "database"): "prove_sqlite_database_creates",
        ("outputs", "database"): "prove_sqlite_database_outputs",
        ("validates", "database"): "prove_sqlite_database_validates",
        ("outputs", "execute"): "prove_sqlite_execute_outputs",
        ("inputs", "query"): "prove_sqlite_query_inputs",
        ("creates", "statement"): "prove_sqlite_statement_creates",
        ("outputs", "statement"): "prove_sqlite_statement_outputs",
        ("inputs", "statement"): "prove_sqlite_statement_inputs",
        ("outputs", "finalize"): "prove_sqlite_finalize_outputs",
        ("outputs", "begin"): "prove_sqlite_begin_outputs",
        ("outputs", "commit"): "prove_sqlite_commit_outputs",
        ("outputs", "rollback"): "prove_sqlite_rollback_outputs",
        ("outputs", "wal"): "prove_sqlite_wal_outputs",
        ("derives", "column"): "prove_sqlite_column_by_name",
        ("derives", "columns"): "prove_sqlite_columns",
        ("derives", "changes"): "prove_sqlite_changes",
    },
    overloads={
        ("outputs", "execute", "Database_String_List"): "prove_sqlite_execute_outputs_params",
        ("inputs", "query", "Database_String_List"): "prove_sqlite_query_inputs_params",
        ("derives", "column", "Row_Integer"): "prove_sqlite_column_by_index",
    },
)
```

### `c_runtime.py`

```python
# STDLIB_RUNTIME_LIBS
"sqlite": {"prove_sqlite"},

# _RUNTIME_FUNCTIONS
"prove_sqlite": [
    "prove_sqlite_database_inputs",
    "prove_sqlite_database_creates",
    "prove_sqlite_database_outputs",
    "prove_sqlite_database_validates",
    "prove_sqlite_execute_outputs",
    "prove_sqlite_execute_outputs_params",
    "prove_sqlite_query_inputs",
    "prove_sqlite_query_inputs_params",
    "prove_sqlite_statement_creates",
    "prove_sqlite_statement_outputs",
    "prove_sqlite_statement_inputs",
    "prove_sqlite_finalize_outputs",
    "prove_sqlite_begin_outputs",
    "prove_sqlite_commit_outputs",
    "prove_sqlite_rollback_outputs",
    "prove_sqlite_wal_outputs",
    "prove_sqlite_column_by_name",
    "prove_sqlite_column_by_index",
    "prove_sqlite_columns",
    "prove_sqlite_changes",
],
```

---

## Implementation Files

| File | Action |
|------|--------|
| `prove-py/src/prove/runtime/vendor/sqlite3.h` | Vendor SQLite amalgamation header |
| `prove-py/src/prove/runtime/vendor/sqlite3.c` | Vendor SQLite amalgamation source |
| `prove-py/src/prove/runtime/prove_sqlite.h` | Type definitions + function declarations |
| `prove-py/src/prove/runtime/prove_sqlite.c` | Full C implementation (~350-400 lines) |
| `prove-py/src/prove/stdlib/sqlite.prv` | Prove module definition |
| `prove-py/src/prove/stdlib_loader.py` | Add `_register_module("sqlite", ...)` |
| `prove-py/src/prove/c_runtime.py` | Add to `STDLIB_RUNTIME_LIBS` + `_RUNTIME_FUNCTIONS` |
| `prove-py/tests/test_sqlite_runtime_c.py` | C runtime tests |

## Implementation Order

1. Vendor SQLite amalgamation
2. `prove_sqlite.h` — types and declarations
3. `prove_sqlite.c` — C implementation
4. `sqlite.prv` — module definition
5. `c_runtime.py` — runtime registration
6. `stdlib_loader.py` — module registration
7. Tests
8. E2e validation
