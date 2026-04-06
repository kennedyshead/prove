"""Tests for the SQLite C runtime module."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from prove.c_compiler import find_c_compiler
from prove.c_runtime import copy_runtime


@pytest.fixture(scope="session")
def sqlite_runtime_dir(tmp_path_factory: pytest.TempPathFactory) -> Path | None:
    """Copy runtime + vendor sqlite files for SQLite testing."""
    cc = find_c_compiler()
    if cc is None:
        return None
    tmp = tmp_path_factory.mktemp("sqlite_runtime")
    copy_runtime(tmp, stdlib_libs={"prove_sqlite"})
    return tmp / "runtime"


def _compile_and_run_sqlite(
    runtime_dir: Path,
    tmp_path: Path,
    c_code: str,
    *,
    name: str = "test",
) -> subprocess.CompletedProcess[str]:
    """Compile a C test program with SQLite support and run it."""
    src = tmp_path / f"{name}.c"
    src.write_text(c_code)
    binary = tmp_path / name
    cc = find_c_compiler()
    assert cc is not None

    _EXCLUDE = frozenset({"prove_gui.c", "prove_prove.c"})
    runtime_c = sorted(f for f in runtime_dir.glob("*.c") if f.name not in _EXCLUDE)
    vendor_c = sorted(runtime_dir.glob("vendor/*.c"))

    cmd = [
        cc,
        "-O0",
        "-Wall",
        "-Wextra",
        "-Wno-unused-parameter",
        "-I",
        str(runtime_dir),
        str(src),
        *[str(f) for f in runtime_c],
        *[str(f) for f in vendor_c],
        "-o",
        str(binary),
        "-lm",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Compile failed:\n{result.stderr}"

    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)


class TestDatabaseLifecycle:
    def test_open_memory(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                printf("ok=%d\\n", prove_result_is_ok(r) ? 1 : 0);
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);
                printf("validates=%d\\n", prove_sqlite_database_validates(db) ? 1 : 0);
                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="db_mem")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "ok=1"
        assert lines[1] == "validates=1"

    def test_open_file(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        db_path = tmp_path / "test.db"
        code = textwrap.dedent(
            """\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *path = prove_string_from_cstr("%s");
                Prove_Result r = prove_sqlite_database_inputs(path);
                printf("ok=%%d\\n", prove_result_is_ok(r) ? 1 : 0);
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);
                prove_sqlite_database_outputs(db);
                return 0;
            }
        """
            % str(db_path)
        )
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="db_file")
        assert result.returncode == 0
        assert "ok=1" in result.stdout


class TestExecuteAndQuery:
    def test_create_insert_query(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);

                /* Create table */
                r = prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("CREATE TABLE t (name TEXT, age TEXT)"));
                printf("create=%d\\n", prove_result_is_ok(r) ? 1 : 0);

                /* Insert row */
                Prove_List *params = prove_list_new(2);
                prove_list_push(params, prove_string_from_cstr("Alice"));
                prove_list_push(params, prove_string_from_cstr("30"));
                r = prove_sqlite_execute_outputs_params(db,
                    prove_string_from_cstr("INSERT INTO t VALUES (?, ?)"), params);
                printf("insert=%d\\n", prove_result_is_ok(r) ? 1 : 0);

                /* Changes */
                printf("changes=%lld\\n", (long long)prove_sqlite_changes(db));

                /* Query */
                r = prove_sqlite_query_inputs(db,
                    prove_string_from_cstr("SELECT name, age FROM t"));
                printf("query=%d\\n", prove_result_is_ok(r) ? 1 : 0);
                Prove_Cursor *cursor = (Prove_Cursor *)prove_result_unwrap_ptr(r);

                Prove_Row *row = prove_sqlite_cursor_next(cursor);
                printf("row_null=%d\\n", row == NULL ? 1 : 0);

                /* Column by name */
                r = prove_sqlite_column_by_name(row, prove_string_from_cstr("name"));
                Prove_String *val = (Prove_String *)prove_result_unwrap_ptr(r);
                printf("name=%s\\n", val->data);

                /* Column by index */
                r = prove_sqlite_column_by_index(row, 1);
                val = (Prove_String *)prove_result_unwrap_ptr(r);
                printf("age=%s\\n", val->data);

                /* Columns list */
                Prove_List *cols = prove_sqlite_columns(row);
                printf("col_count=%lld\\n", (long long)cols->length);
                printf("col0=%s\\n", ((Prove_String *)cols->data[0])->data);
                printf("col1=%s\\n", ((Prove_String *)cols->data[1])->data);

                /* No more rows */
                Prove_Row *row2 = prove_sqlite_cursor_next(cursor);
                printf("done=%d\\n", row2 == NULL ? 1 : 0);

                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="exec_query")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "create=1"
        assert lines[1] == "insert=1"
        assert lines[2] == "changes=1"
        assert lines[3] == "query=1"
        assert lines[4] == "row_null=0"
        assert lines[5] == "name=Alice"
        assert lines[6] == "age=30"
        assert lines[7] == "col_count=2"
        assert lines[8] == "col0=name"
        assert lines[9] == "col1=age"
        assert lines[10] == "done=1"


class TestTransactions:
    def test_begin_commit_rollback(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);

                prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("CREATE TABLE t (x TEXT)"));

                /* Begin + insert + rollback → no rows */
                r = prove_sqlite_begin_outputs(db);
                printf("begin=%d\\n", prove_result_is_ok(r) ? 1 : 0);
                prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("INSERT INTO t VALUES ('gone')"));
                r = prove_sqlite_rollback_outputs(db);
                printf("rollback=%d\\n", prove_result_is_ok(r) ? 1 : 0);

                r = prove_sqlite_query_inputs(db,
                    prove_string_from_cstr("SELECT count(*) FROM t"));
                Prove_Cursor *c = (Prove_Cursor *)prove_result_unwrap_ptr(r);
                Prove_Row *row = prove_sqlite_cursor_next(c);
                r = prove_sqlite_column_by_index(row, 0);
                printf("count_after_rollback=%s\\n",
                    ((Prove_String *)prove_result_unwrap_ptr(r))->data);

                /* Begin + insert + commit → 1 row */
                prove_sqlite_begin_outputs(db);
                prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("INSERT INTO t VALUES ('kept')"));
                r = prove_sqlite_commit_outputs(db);
                printf("commit=%d\\n", prove_result_is_ok(r) ? 1 : 0);

                r = prove_sqlite_query_inputs(db,
                    prove_string_from_cstr("SELECT count(*) FROM t"));
                c = (Prove_Cursor *)prove_result_unwrap_ptr(r);
                row = prove_sqlite_cursor_next(c);
                r = prove_sqlite_column_by_index(row, 0);
                printf("count_after_commit=%s\\n",
                    ((Prove_String *)prove_result_unwrap_ptr(r))->data);

                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="txn")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "begin=1"
        assert lines[1] == "rollback=1"
        assert lines[2] == "count_after_rollback=0"
        assert lines[3] == "commit=1"
        assert lines[4] == "count_after_commit=1"


class TestPreparedStatements:
    def test_prepare_execute_query(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);

                prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("CREATE TABLE t (name TEXT)"));

                /* Prepare an INSERT */
                r = prove_sqlite_statement_creates(db,
                    prove_string_from_cstr("INSERT INTO t VALUES (?)"));
                printf("prepare=%d\\n", prove_result_is_ok(r) ? 1 : 0);
                Prove_Statement *stmt = (Prove_Statement *)prove_result_unwrap_ptr(r);

                /* Execute twice */
                Prove_List *p1 = prove_list_new(1);
                prove_list_push(p1, prove_string_from_cstr("Alice"));
                r = prove_sqlite_statement_outputs(stmt, p1);
                printf("exec1=%d\\n", prove_result_is_ok(r) ? 1 : 0);

                Prove_List *p2 = prove_list_new(1);
                prove_list_push(p2, prove_string_from_cstr("Bob"));
                r = prove_sqlite_statement_outputs(stmt, p2);
                printf("exec2=%d\\n", prove_result_is_ok(r) ? 1 : 0);

                prove_sqlite_finalize_outputs(stmt);

                /* Query to verify */
                r = prove_sqlite_query_inputs(db,
                    prove_string_from_cstr("SELECT name FROM t ORDER BY name"));
                Prove_Cursor *c = (Prove_Cursor *)prove_result_unwrap_ptr(r);

                Prove_Row *row = prove_sqlite_cursor_next(c);
                r = prove_sqlite_column_by_index(row, 0);
                printf("row1=%s\\n", ((Prove_String *)prove_result_unwrap_ptr(r))->data);

                row = prove_sqlite_cursor_next(c);
                r = prove_sqlite_column_by_index(row, 0);
                printf("row2=%s\\n", ((Prove_String *)prove_result_unwrap_ptr(r))->data);

                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="prepared")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "prepare=1"
        assert lines[1] == "exec1=1"
        assert lines[2] == "exec2=1"
        assert lines[3] == "row1=Alice"
        assert lines[4] == "row2=Bob"


class TestWAL:
    def test_wal_mode(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);
                r = prove_sqlite_wal_outputs(db);
                printf("wal=%d\\n", prove_result_is_ok(r) ? 1 : 0);
                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="wal")
        assert result.returncode == 0
        assert "wal=1" in result.stdout


class TestErrorHandling:
    def test_bad_sql(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);
                r = prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("NOT VALID SQL"));
                printf("err=%d\\n", prove_result_is_err(r) ? 1 : 0);
                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="bad_sql")
        assert result.returncode == 0
        assert "err=1" in result.stdout

    def test_column_not_found(self, tmp_path, sqlite_runtime_dir):
        if sqlite_runtime_dir is None:
            pytest.skip("no C compiler")
        code = textwrap.dedent("""\
            #include "prove_sqlite.h"
            #include <stdio.h>
            int main(void) {
                Prove_Result r = prove_sqlite_database_creates();
                Prove_Database *db = (Prove_Database *)prove_result_unwrap_ptr(r);
                prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("CREATE TABLE t (x TEXT)"));
                prove_sqlite_execute_outputs(db,
                    prove_string_from_cstr("INSERT INTO t VALUES ('hello')"));
                r = prove_sqlite_query_inputs(db,
                    prove_string_from_cstr("SELECT x FROM t"));
                Prove_Cursor *c = (Prove_Cursor *)prove_result_unwrap_ptr(r);
                Prove_Row *row = prove_sqlite_cursor_next(c);

                r = prove_sqlite_column_by_name(row, prove_string_from_cstr("nonexistent"));
                printf("err=%d\\n", prove_result_is_err(r) ? 1 : 0);

                r = prove_sqlite_column_by_index(row, 99);
                printf("idx_err=%d\\n", prove_result_is_err(r) ? 1 : 0);

                prove_sqlite_database_outputs(db);
                return 0;
            }
        """)
        result = _compile_and_run_sqlite(sqlite_runtime_dir, tmp_path, code, name="col_err")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "err=1"
        assert lines[1] == "idx_err=1"
