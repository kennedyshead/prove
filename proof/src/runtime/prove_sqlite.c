#include "prove_sqlite.h"
#include <string.h>

/* ── Helpers ───────────────────────────────────────────────── */

static Prove_Result _sqlite_error(sqlite3 *db) {
    const char *msg = sqlite3_errmsg(db);
    return prove_result_err(prove_string_from_cstr(msg));
}

static Prove_Result _bind_params(sqlite3_stmt *stmt, Prove_List *params) {
    for (int64_t i = 0; i < params->length; i++) {
        Prove_String *val = (Prove_String *)params->data[i];
        int rc = sqlite3_bind_text(stmt, (int)(i + 1),
                                    val->data, (int)val->length,
                                    SQLITE_TRANSIENT);
        if (rc != SQLITE_OK) {
            return prove_result_err(
                prove_string_from_cstr("failed to bind parameter"));
        }
    }
    return prove_result_ok();
}

/* ── Database lifecycle ────────────────────────────────────── */

Prove_Result prove_sqlite_database_inputs(Prove_String *path) {
    Prove_Database *d = (Prove_Database *)prove_alloc(sizeof(Prove_Database));
    int rc = sqlite3_open(path->data, &d->db);
    if (rc != SQLITE_OK) {
        Prove_Result err = _sqlite_error(d->db);
        sqlite3_close(d->db);
        prove_release(d);
        return err;
    }
    return prove_result_ok_ptr(d);
}

Prove_Result prove_sqlite_database_creates(void) {
    Prove_Database *d = (Prove_Database *)prove_alloc(sizeof(Prove_Database));
    int rc = sqlite3_open(":memory:", &d->db);
    if (rc != SQLITE_OK) {
        Prove_Result err = _sqlite_error(d->db);
        sqlite3_close(d->db);
        prove_release(d);
        return err;
    }
    return prove_result_ok_ptr(d);
}

void prove_sqlite_database_outputs(Prove_Database *db) {
    if (db && db->db) {
        sqlite3_close(db->db);
        db->db = NULL;
    }
    if (db) prove_release(db);
}

bool prove_sqlite_database_validates(Prove_Database *db) {
    return db != NULL && db->db != NULL;
}

/* ── Execute ───────────────────────────────────────────────── */

Prove_Result prove_sqlite_execute_outputs(Prove_Database *db, Prove_String *sql) {
    char *errmsg = NULL;
    int rc = sqlite3_exec(db->db, sql->data, NULL, NULL, &errmsg);
    if (rc != SQLITE_OK) {
        Prove_Result err = prove_result_err(
            prove_string_from_cstr(errmsg ? errmsg : "exec failed"));
        if (errmsg) sqlite3_free(errmsg);
        return err;
    }
    return prove_result_ok();
}

Prove_Result prove_sqlite_execute_outputs_params(Prove_Database *db,
                                                  Prove_String *sql,
                                                  Prove_List *params) {
    sqlite3_stmt *stmt;
    int rc = sqlite3_prepare_v2(db->db, sql->data, (int)sql->length, &stmt, NULL);
    if (rc != SQLITE_OK) return _sqlite_error(db->db);

    Prove_Result br = _bind_params(stmt, params);
    if (prove_result_is_err(br)) {
        sqlite3_finalize(stmt);
        return br;
    }

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc != SQLITE_DONE && rc != SQLITE_ROW) {
        return _sqlite_error(db->db);
    }
    return prove_result_ok();
}

/* ── Query ─────────────────────────────────────────────────── */

static Prove_Result _make_cursor(Prove_Database *db, sqlite3_stmt *stmt, bool owns) {
    Prove_Cursor *c = (Prove_Cursor *)prove_alloc(sizeof(Prove_Cursor));
    c->stmt = stmt;
    c->db = db;
    prove_retain(db);
    c->done = false;
    c->owns_stmt = owns;
    return prove_result_ok_ptr(c);
}

Prove_Result prove_sqlite_query_inputs(Prove_Database *db, Prove_String *sql) {
    sqlite3_stmt *stmt;
    int rc = sqlite3_prepare_v2(db->db, sql->data, (int)sql->length, &stmt, NULL);
    if (rc != SQLITE_OK) return _sqlite_error(db->db);
    return _make_cursor(db, stmt, true);
}

Prove_Result prove_sqlite_query_inputs_params(Prove_Database *db,
                                               Prove_String *sql,
                                               Prove_List *params) {
    sqlite3_stmt *stmt;
    int rc = sqlite3_prepare_v2(db->db, sql->data, (int)sql->length, &stmt, NULL);
    if (rc != SQLITE_OK) return _sqlite_error(db->db);

    Prove_Result br = _bind_params(stmt, params);
    if (prove_result_is_err(br)) {
        sqlite3_finalize(stmt);
        return br;
    }
    return _make_cursor(db, stmt, true);
}

/* ── Prepared statements ───────────────────────────────────── */

Prove_Result prove_sqlite_statement_creates(Prove_Database *db, Prove_String *sql) {
    Prove_Statement *s = (Prove_Statement *)prove_alloc(sizeof(Prove_Statement));
    int rc = sqlite3_prepare_v2(db->db, sql->data, (int)sql->length, &s->stmt, NULL);
    if (rc != SQLITE_OK) {
        Prove_Result err = _sqlite_error(db->db);
        prove_release(s);
        return err;
    }
    s->db = db;
    prove_retain(db);
    return prove_result_ok_ptr(s);
}

Prove_Result prove_sqlite_statement_outputs(Prove_Statement *stmt, Prove_List *params) {
    sqlite3_reset(stmt->stmt);
    sqlite3_clear_bindings(stmt->stmt);

    Prove_Result br = _bind_params(stmt->stmt, params);
    if (prove_result_is_err(br)) return br;

    int rc = sqlite3_step(stmt->stmt);
    if (rc != SQLITE_DONE && rc != SQLITE_ROW) {
        return _sqlite_error(stmt->db->db);
    }
    return prove_result_ok();
}

Prove_Result prove_sqlite_statement_inputs(Prove_Statement *stmt, Prove_List *params) {
    sqlite3_reset(stmt->stmt);
    sqlite3_clear_bindings(stmt->stmt);

    Prove_Result br = _bind_params(stmt->stmt, params);
    if (prove_result_is_err(br)) return br;

    return _make_cursor(stmt->db, stmt->stmt, false);
}

void prove_sqlite_finalize_outputs(Prove_Statement *stmt) {
    if (stmt && stmt->stmt) {
        sqlite3_finalize(stmt->stmt);
        stmt->stmt = NULL;
    }
    if (stmt) {
        if (stmt->db) prove_release(stmt->db);
        prove_release(stmt);
    }
}

/* ── Transactions ──────────────────────────────────────────── */

Prove_Result prove_sqlite_begin_outputs(Prove_Database *db) {
    return prove_sqlite_execute_outputs(db, prove_string_from_cstr("BEGIN"));
}

Prove_Result prove_sqlite_commit_outputs(Prove_Database *db) {
    return prove_sqlite_execute_outputs(db, prove_string_from_cstr("COMMIT"));
}

Prove_Result prove_sqlite_rollback_outputs(Prove_Database *db) {
    return prove_sqlite_execute_outputs(db, prove_string_from_cstr("ROLLBACK"));
}

/* ── WAL mode ──────────────────────────────────────────────── */

Prove_Result prove_sqlite_wal_outputs(Prove_Database *db) {
    return prove_sqlite_execute_outputs(db, prove_string_from_cstr("PRAGMA journal_mode=WAL"));
}

/* ── Cursor iteration ──────────────────────────────────────── */

Prove_Row *prove_sqlite_cursor_next(Prove_Cursor *cursor) {
    if (cursor->done) return NULL;

    int rc = sqlite3_step(cursor->stmt);
    if (rc == SQLITE_DONE) {
        cursor->done = true;
        if (cursor->owns_stmt) {
            sqlite3_finalize(cursor->stmt);
            cursor->stmt = NULL;
        }
        return NULL;
    }
    if (rc != SQLITE_ROW) {
        cursor->done = true;
        return NULL;
    }

    int col_count = sqlite3_column_count(cursor->stmt);
    Prove_Row *row = (Prove_Row *)prove_alloc(sizeof(Prove_Row));
    row->column_count = col_count;
    row->column_names = (Prove_String **)calloc((size_t)col_count, sizeof(Prove_String *));
    row->values = (Prove_String **)calloc((size_t)col_count, sizeof(Prove_String *));

    for (int i = 0; i < col_count; i++) {
        const char *cname = sqlite3_column_name(cursor->stmt, i);
        row->column_names[i] = prove_string_from_cstr(cname);

        if (sqlite3_column_type(cursor->stmt, i) == SQLITE_NULL) {
            row->values[i] = NULL;
        } else {
            const char *cval = (const char *)sqlite3_column_text(cursor->stmt, i);
            row->values[i] = prove_string_from_cstr(cval);
        }
    }
    return row;
}

/* ── Row access ────────────────────────────────────────────── */

Prove_Result prove_sqlite_column_by_name(Prove_Row *row, Prove_String *name) {
    for (int64_t i = 0; i < row->column_count; i++) {
        if (prove_string_eq(row->column_names[i], name)) {
            if (row->values[i] == NULL) {
                return prove_result_ok_ptr(prove_string_from_cstr(""));
            }
            prove_retain(row->values[i]);
            return prove_result_ok_ptr(row->values[i]);
        }
    }
    Prove_String *msg = prove_string_concat(
        prove_string_from_cstr("no such column: "), name);
    return prove_result_err(msg);
}

Prove_Result prove_sqlite_column_by_index(Prove_Row *row, int64_t index) {
    if (index < 0 || index >= row->column_count) {
        return prove_result_err(
            prove_string_from_cstr("column index out of range"));
    }
    if (row->values[index] == NULL) {
        return prove_result_ok_ptr(prove_string_from_cstr(""));
    }
    prove_retain(row->values[index]);
    return prove_result_ok_ptr(row->values[index]);
}

Prove_List *prove_sqlite_columns(Prove_Row *row) {
    Prove_List *list = prove_list_new(row->column_count);
    for (int64_t i = 0; i < row->column_count; i++) {
        prove_retain(row->column_names[i]);
        prove_list_push(list, row->column_names[i]);
    }
    return list;
}

/* ── Changes ───────────────────────────────────────────────── */

int64_t prove_sqlite_changes(Prove_Database *db) {
    return (int64_t)sqlite3_changes(db->db);
}
