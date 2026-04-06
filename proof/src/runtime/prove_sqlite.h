#ifndef PROVE_SQLITE_H
#define PROVE_SQLITE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_result.h"

#include "vendor/sqlite3.h"

/* ── Database handle ───────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    sqlite3      *db;
} Prove_Database;

/* ── Prepared statement ────────────────────────────────────── */

typedef struct {
    Prove_Header    header;
    sqlite3_stmt   *stmt;
    Prove_Database *db;       /* back-ref prevents premature GC */
} Prove_Statement;

/* ── Cursor (forward-only result iterator) ─────────────────── */

typedef struct {
    Prove_Header    header;
    sqlite3_stmt   *stmt;
    Prove_Database *db;       /* back-ref */
    bool            done;     /* true after SQLITE_DONE */
    bool            owns_stmt; /* true if cursor should finalize stmt */
} Prove_Cursor;

/* ── Row (snapshot of one result row) ──────────────────────── */

typedef struct {
    Prove_Header    header;
    int64_t         column_count;
    Prove_String  **column_names;
    Prove_String  **values;   /* NULL entry for SQL NULL */
} Prove_Row;

/* ── Database lifecycle ────────────────────────────────────── */

Prove_Result prove_sqlite_database_inputs(Prove_String *path);
Prove_Result prove_sqlite_database_creates(void);
void         prove_sqlite_database_outputs(Prove_Database *db);
bool         prove_sqlite_database_validates(Prove_Database *db);

/* ── Execute (no result rows) ──────────────────────────────── */

Prove_Result prove_sqlite_execute_outputs(Prove_Database *db, Prove_String *sql);
Prove_Result prove_sqlite_execute_outputs_params(Prove_Database *db,
                                                  Prove_String *sql,
                                                  Prove_List *params);

/* ── Query (returns Cursor) ────────────────────────────────── */

Prove_Result prove_sqlite_query_inputs(Prove_Database *db, Prove_String *sql);
Prove_Result prove_sqlite_query_inputs_params(Prove_Database *db,
                                               Prove_String *sql,
                                               Prove_List *params);

/* ── Prepared statements ───────────────────────────────────── */

Prove_Result prove_sqlite_statement_creates(Prove_Database *db, Prove_String *sql);
Prove_Result prove_sqlite_statement_outputs(Prove_Statement *stmt, Prove_List *params);
Prove_Result prove_sqlite_statement_inputs(Prove_Statement *stmt, Prove_List *params);
void         prove_sqlite_finalize_outputs(Prove_Statement *stmt);

/* ── Transactions ──────────────────────────────────────────── */

Prove_Result prove_sqlite_begin_outputs(Prove_Database *db);
Prove_Result prove_sqlite_commit_outputs(Prove_Database *db);
Prove_Result prove_sqlite_rollback_outputs(Prove_Database *db);

/* ── WAL mode ──────────────────────────────────────────────── */

Prove_Result prove_sqlite_wal_outputs(Prove_Database *db);

/* ── Row access ────────────────────────────────────────────── */

Prove_Result  prove_sqlite_column_by_name(Prove_Row *row, Prove_String *name);
Prove_Result  prove_sqlite_column_by_index(Prove_Row *row, int64_t index);
Prove_List   *prove_sqlite_columns(Prove_Row *row);

/* ── Changes ───────────────────────────────────────────────── */

int64_t prove_sqlite_changes(Prove_Database *db);

/* ── Cursor iteration (called by HOF runtime) ──────────────── */

Prove_Row *prove_sqlite_cursor_next(Prove_Cursor *cursor);

#endif /* PROVE_SQLITE_H */
