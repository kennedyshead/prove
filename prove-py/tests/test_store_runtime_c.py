"""Tests for the Store C runtime module."""

from __future__ import annotations

import textwrap

from tests.runtime_helpers import compile_and_run


class TestStoreCreate:
    def test_create_and_validate(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *path = prove_string_from_cstr("%s/testdb");
                Prove_Result r = prove_store_create(path);
                printf("create_ok=%%d\\n", prove_result_is_ok(r) ? 1 : 0);
                printf("validates=%%d\\n", prove_store_validates(path) ? 1 : 0);
                /* Non-existent path */
                Prove_String *bad = prove_string_from_cstr("%s/no/such/deep/path");
                printf("bad_validates=%%d\\n", prove_store_validates(bad) ? 1 : 0);
                return 0;
            }
        """ % (str(tmp_path), str(tmp_path)))
        result = compile_and_run(runtime_dir, tmp_path, code, name="store_create")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "create_ok=1"
        assert lines[1] == "validates=1"
        assert lines[2] == "bad_validates=0"


class TestTableNewAndVariants:
    def test_table_constructor(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *cols[2];
                cols[0] = prove_string_from_cstr("code");
                cols[1] = prove_string_from_cstr("message");
                Prove_String *name = prove_string_from_cstr("http_status");
                Prove_StoreTable *t = prove_store_table_new(name, 2, cols);
                printf("name=%s\\n", t->name->data);
                printf("cols=%lld\\n", (long long)t->column_count);
                printf("vars=%lld\\n", (long long)t->variant_count);

                /* Add a variant */
                Prove_String *vals[2];
                vals[0] = prove_string_from_cstr("200");
                vals[1] = prove_string_from_cstr("OK");
                prove_store_table_add_variant(t, prove_string_from_cstr("Ok"), vals);
                printf("vars_after=%lld\\n", (long long)t->variant_count);
                printf("v0_name=%s\\n", t->variant_names[0]->data);
                printf("v0_c0=%s\\n", t->values[0][0]->data);
                printf("v0_c1=%s\\n", t->values[0][1]->data);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="tbl_new")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "name=http_status"
        assert lines[1] == "cols=2"
        assert lines[2] == "vars=0"
        assert lines[3] == "vars_after=1"
        assert lines[4] == "v0_name=Ok"
        assert lines[5] == "v0_c0=200"
        assert lines[6] == "v0_c1=OK"


class TestTableSaveAndLoad:
    def test_save_load_roundtrip(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                /* Create store */
                Prove_String *path = prove_string_from_cstr("%s/roundtrip_db");
                Prove_Result cr = prove_store_create(path);
                if (!prove_result_is_ok(cr)) { printf("FAIL create\\n"); return 1; }
                Prove_Store *db = (Prove_Store *)prove_result_unwrap_ptr(cr);

                /* Create table */
                Prove_String *cols[2];
                cols[0] = prove_string_from_cstr("code");
                cols[1] = prove_string_from_cstr("message");
                Prove_StoreTable *t = prove_store_table_new(
                    prove_string_from_cstr("status"), 2, cols);

                Prove_String *v1[2];
                v1[0] = prove_string_from_cstr("200");
                v1[1] = prove_string_from_cstr("OK");
                prove_store_table_add_variant(t, prove_string_from_cstr("Ok"), v1);

                Prove_String *v2[2];
                v2[0] = prove_string_from_cstr("404");
                v2[1] = prove_string_from_cstr("Not Found");
                prove_store_table_add_variant(t, prove_string_from_cstr("NotFound"), v2);

                /* Save */
                Prove_Result sr = prove_store_table_outputs(db, t);
                printf("save_ok=%%d\\n", prove_result_is_ok(sr) ? 1 : 0);
                printf("version=%%lld\\n", (long long)t->version);

                /* Validate */
                printf("exists=%%d\\n",
                    prove_store_table_validates(db, prove_string_from_cstr("status")) ? 1 : 0);

                /* Load */
                Prove_Result lr = prove_store_table_inputs(db, prove_string_from_cstr("status"));
                printf("load_ok=%%d\\n", prove_result_is_ok(lr) ? 1 : 0);
                Prove_StoreTable *loaded = (Prove_StoreTable *)prove_result_unwrap_ptr(lr);
                printf("loaded_name=%%s\\n", loaded->name->data);
                printf("loaded_cols=%%lld\\n", (long long)loaded->column_count);
                printf("loaded_vars=%%lld\\n", (long long)loaded->variant_count);
                printf("loaded_ver=%%lld\\n", (long long)loaded->version);
                printf("loaded_v0=%%s\\n", loaded->variant_names[0]->data);
                printf("loaded_v1=%%s\\n", loaded->variant_names[1]->data);
                printf("loaded_v1_c1=%%s\\n", loaded->values[1][1]->data);
                return 0;
            }
        """ % str(tmp_path))
        result = compile_and_run(runtime_dir, tmp_path, code, name="tbl_save")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "save_ok=1"
        assert lines[1] == "version=1"
        assert lines[2] == "exists=1"
        assert lines[3] == "load_ok=1"
        assert lines[4] == "loaded_name=status"
        assert lines[5] == "loaded_cols=2"
        assert lines[6] == "loaded_vars=2"
        assert lines[7] == "loaded_ver=1"
        assert lines[8] == "loaded_v0=Ok"
        assert lines[9] == "loaded_v1=NotFound"
        assert lines[10] == "loaded_v1_c1=Not Found"


class TestOptimisticConcurrency:
    def test_stale_version_rejected(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *path = prove_string_from_cstr("%s/concurrency_db");
                Prove_Store *db = (Prove_Store *)prove_result_unwrap_ptr(
                    prove_store_create(path));

                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");
                Prove_StoreTable *t = prove_store_table_new(
                    prove_string_from_cstr("data"), 1, cols);
                Prove_String *v[1];
                v[0] = prove_string_from_cstr("hello");
                prove_store_table_add_variant(t, prove_string_from_cstr("greeting"), v);

                /* Save version 1 */
                prove_store_table_outputs(db, t);
                printf("v1=%%lld\\n", (long long)t->version);

                /* Save version 2 */
                prove_store_table_outputs(db, t);
                printf("v2=%%lld\\n", (long long)t->version);

                /* Load — gets version 2 */
                Prove_StoreTable *loaded = (Prove_StoreTable *)prove_result_unwrap_ptr(
                    prove_store_table_inputs(db, prove_string_from_cstr("data")));
                printf("loaded_v=%%lld\\n", (long long)loaded->version);

                /* Simulate stale: set loaded version back to 1 */
                loaded->version = 1;
                Prove_Result stale = prove_store_table_outputs(db, loaded);
                printf("stale_ok=%%d\\n", prove_result_is_ok(stale) ? 1 : 0);
                if (prove_result_is_err(stale)) {
                    printf("err=%%s\\n", ((Prove_String *)stale.error)->data);
                }
                return 0;
            }
        """ % str(tmp_path))
        result = compile_and_run(runtime_dir, tmp_path, code, name="stale")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "v1=1"
        assert lines[1] == "v2=2"
        assert lines[2] == "loaded_v=2"
        assert lines[3] == "stale_ok=0"
        assert lines[4] == "err=stale version"


class TestDiff:
    def test_diff_added_removed_changed(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");

                /* Old table: A=1, B=2 */
                Prove_StoreTable *old = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *va[1]; va[0] = prove_string_from_cstr("1");
                prove_store_table_add_variant(old, prove_string_from_cstr("A"), va);
                Prove_String *vb[1]; vb[0] = prove_string_from_cstr("2");
                prove_store_table_add_variant(old, prove_string_from_cstr("B"), vb);

                /* New table: A=10 (changed), C=3 (added), B removed */
                Prove_StoreTable *new_t = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *va2[1]; va2[0] = prove_string_from_cstr("10");
                prove_store_table_add_variant(new_t, prove_string_from_cstr("A"), va2);
                Prove_String *vc[1]; vc[0] = prove_string_from_cstr("3");
                prove_store_table_add_variant(new_t, prove_string_from_cstr("C"), vc);

                Prove_TableDiff *d = prove_store_diff(old, new_t);
                printf("added=%lld\\n", (long long)d->added_count);
                printf("removed=%lld\\n", (long long)d->removed_count);
                printf("changed=%lld\\n", (long long)d->changed_count);
                if (d->added_count > 0)
                    printf("added_name=%s\\n", d->added[0].variant->data);
                if (d->removed_count > 0)
                    printf("removed_name=%s\\n", d->removed[0].variant->data);
                if (d->changed_count > 0) {
                    printf("changed_var=%s\\n", d->changed[0].variant->data);
                    printf("changed_old=%s\\n", d->changed[0].old_value->data);
                    printf("changed_new=%s\\n", d->changed[0].new_value->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="diff")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "added=1"
        assert lines[1] == "removed=1"
        assert lines[2] == "changed=1"
        assert lines[3] == "added_name=C"
        assert lines[4] == "removed_name=B"
        assert lines[5] == "changed_var=A"
        assert lines[6] == "changed_old=1"
        assert lines[7] == "changed_new=10"


class TestPatch:
    def test_patch_apply(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");

                /* Base: A=1, B=2 */
                Prove_StoreTable *base = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *va[1]; va[0] = prove_string_from_cstr("1");
                prove_store_table_add_variant(base, prove_string_from_cstr("A"), va);
                Prove_String *vb[1]; vb[0] = prove_string_from_cstr("2");
                prove_store_table_add_variant(base, prove_string_from_cstr("B"), vb);

                /* Modified: A=10, C=3, B removed */
                Prove_StoreTable *modified = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *va2[1]; va2[0] = prove_string_from_cstr("10");
                prove_store_table_add_variant(modified, prove_string_from_cstr("A"), va2);
                Prove_String *vc[1]; vc[0] = prove_string_from_cstr("3");
                prove_store_table_add_variant(modified, prove_string_from_cstr("C"), vc);

                Prove_TableDiff *d = prove_store_diff(base, modified);
                Prove_StoreTable *patched = prove_store_patch(base, d);

                printf("vars=%lld\\n", (long long)patched->variant_count);
                for (int64_t i = 0; i < patched->variant_count; i++) {
                    printf("%s=%s\\n", patched->variant_names[i]->data,
                           patched->values[i][0]->data);
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="patch")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "vars=2"
        assert "A=10" in lines
        assert "C=3" in lines


class TestIntegrity:
    def test_integrity_hash(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");
                Prove_StoreTable *t = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *v[1]; v[0] = prove_string_from_cstr("hello");
                prove_store_table_add_variant(t, prove_string_from_cstr("A"), v);

                Prove_String *h1 = prove_store_integrity(t);
                Prove_String *h2 = prove_store_integrity(t);
                printf("len=%lld\\n", (long long)h1->length);
                printf("eq=%d\\n", prove_string_eq(h1, h2) ? 1 : 0);

                /* Change value, hash should differ */
                v[0] = prove_string_from_cstr("world");
                Prove_StoreTable *t2 = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                prove_store_table_add_variant(t2, prove_string_from_cstr("A"), v);
                Prove_String *h3 = prove_store_integrity(t2);
                printf("diff=%d\\n", prove_string_eq(h1, h3) ? 0 : 1);
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="integrity")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "len=64"  # SHA-256 hex string is 64 chars
        assert lines[1] == "eq=1"
        assert lines[2] == "diff=1"


class TestVersionsAndRollback:
    def test_versions_and_rollback(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *path = prove_string_from_cstr("%s/ver_db");
                Prove_Store *db = (Prove_Store *)prove_result_unwrap_ptr(
                    prove_store_create(path));

                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");
                Prove_StoreTable *t = prove_store_table_new(
                    prove_string_from_cstr("data"), 1, cols);
                Prove_String *v[1]; v[0] = prove_string_from_cstr("original");
                prove_store_table_add_variant(t, prove_string_from_cstr("A"), v);

                /* Save version 1 */
                prove_store_table_outputs(db, t);

                /* Modify and save version 2 */
                t->values[0][0] = prove_string_from_cstr("modified");
                prove_store_table_outputs(db, t);

                /* List versions */
                Prove_Result vr = prove_store_version_inputs(db, prove_string_from_cstr("data"));
                printf("list_ok=%%d\\n", prove_result_is_ok(vr) ? 1 : 0);
                Prove_List *versions = (Prove_List *)prove_result_unwrap_ptr(vr);
                printf("version_count=%%lld\\n", (long long)prove_list_len(versions));

                /* Rollback to version 1 */
                Prove_Result rb = prove_store_rollback(db,
                    prove_string_from_cstr("data"), 1);
                printf("rollback_ok=%%d\\n", prove_result_is_ok(rb) ? 1 : 0);
                Prove_StoreTable *rolled = (Prove_StoreTable *)prove_result_unwrap_ptr(rb);
                printf("rolled_value=%%s\\n", rolled->values[0][0]->data);
                printf("rolled_ver=%%lld\\n", (long long)rolled->version);
                return 0;
            }
        """ % str(tmp_path))
        result = compile_and_run(runtime_dir, tmp_path, code, name="versions")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "list_ok=1"
        assert lines[1] == "version_count=2"
        assert lines[2] == "rollback_ok=1"
        assert lines[3] == "rolled_value=original"
        assert lines[4] == "rolled_ver=3"  # version 3 after rollback


class TestMerge:
    def test_merge_no_conflict(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");

                /* Base: A=1, B=2 */
                Prove_StoreTable *base = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *va[1]; va[0] = prove_string_from_cstr("1");
                prove_store_table_add_variant(base, prove_string_from_cstr("A"), va);
                Prove_String *vb[1]; vb[0] = prove_string_from_cstr("2");
                prove_store_table_add_variant(base, prove_string_from_cstr("B"), vb);

                /* Local changes: A=10 */
                Prove_StoreTable *local_t = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *vla[1]; vla[0] = prove_string_from_cstr("10");
                prove_store_table_add_variant(local_t, prove_string_from_cstr("A"), vla);
                Prove_String *vlb[1]; vlb[0] = prove_string_from_cstr("2");
                prove_store_table_add_variant(local_t, prove_string_from_cstr("B"), vlb);

                /* Remote changes: B=20 */
                Prove_StoreTable *remote_t = prove_store_table_new(
                    prove_string_from_cstr("t"), 1, cols);
                Prove_String *vra[1]; vra[0] = prove_string_from_cstr("1");
                prove_store_table_add_variant(remote_t, prove_string_from_cstr("A"), vra);
                Prove_String *vrb[1]; vrb[0] = prove_string_from_cstr("20");
                prove_store_table_add_variant(remote_t, prove_string_from_cstr("B"), vrb);

                Prove_TableDiff *ld = prove_store_diff(base, local_t);
                Prove_TableDiff *rd = prove_store_diff(base, remote_t);

                Prove_MergeResult *mr = prove_store_merge(base, ld, rd, NULL);
                printf("tag=%d\\n", mr->tag);
                if (mr->tag == PROVE_MERGE_MERGED) {
                    Prove_StoreTable *merged = mr->data.table;
                    printf("vars=%lld\\n", (long long)merged->variant_count);
                    for (int64_t i = 0; i < merged->variant_count; i++) {
                        printf("%s=%s\\n", merged->variant_names[i]->data,
                               merged->values[i][0]->data);
                    }
                }
                return 0;
            }
        """)
        result = compile_and_run(runtime_dir, tmp_path, code, name="merge")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "tag=0"  # PROVE_MERGE_MERGED
        assert lines[1] == "vars=2"
        assert "A=10" in lines
        assert "B=20" in lines


class TestLookupCompile:
    def test_lookup_output_input(self, tmp_path, runtime_dir):
        code = textwrap.dedent("""\
            #include "prove_store.h"
            #include <stdio.h>
            int main(void) {
                Prove_String *path = prove_string_from_cstr("%s/bin_db");
                Prove_Store *db = (Prove_Store *)prove_result_unwrap_ptr(
                    prove_store_create(path));

                Prove_String *cols[1];
                cols[0] = prove_string_from_cstr("value");
                Prove_StoreTable *t = prove_store_table_new(
                    prove_string_from_cstr("codes"), 1, cols);
                Prove_String *v1[1]; v1[0] = prove_string_from_cstr("OK");
                prove_store_table_add_variant(t, prove_string_from_cstr("Status200"), v1);
                Prove_String *v2[1]; v2[0] = prove_string_from_cstr("Not Found");
                prove_store_table_add_variant(t, prove_string_from_cstr("Status404"), v2);

                prove_store_table_outputs(db, t);

                /* Compile lookup */
                Prove_Result br = prove_store_lookup_outputs(db,
                    prove_string_from_cstr("codes"));
                printf("compile_ok=%%d\\n", prove_result_is_ok(br) ? 1 : 0);

                /* Load lookup */
                Prove_String *bin_path = prove_string_from_cstr(
                    "%s/bin_db/codes/lookup.bin");
                Prove_Result lr = prove_store_lookup_inputs(bin_path);
                printf("load_ok=%%d\\n", prove_result_is_ok(lr) ? 1 : 0);
                Prove_List *entries = (Prove_List *)prove_result_unwrap_ptr(lr);
                printf("entries=%%lld\\n", (long long)prove_list_len(entries));
                return 0;
            }
        """ % (str(tmp_path), str(tmp_path)))
        result = compile_and_run(runtime_dir, tmp_path, code, name="lookup")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "compile_ok=1"
        assert lines[1] == "load_ok=1"
        assert lines[2] == "entries=2"
