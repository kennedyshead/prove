/* Prove Database runtime — storage, versioning, diffs, merges for lookup tables. */

#include "prove_database.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <dirent.h>
#include <time.h>

/* ── Internal helpers ───────────────────────────────────────── */

static char *_to_cstr(Prove_String *s) {
    return s->data;
}

static int _mkdir_p(const char *path) {
    if (mkdir(path, 0755) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static Prove_String *_path_join(Prove_String *base, const char *child) {
    int64_t blen = base->length;
    int64_t clen = (int64_t)strlen(child);
    int64_t total = blen + 1 + clen;
    char *buf = (char *)malloc((size_t)total + 1);
    if (!buf) prove_panic("out of memory");
    memcpy(buf, base->data, (size_t)blen);
    buf[blen] = '/';
    memcpy(buf + blen + 1, child, (size_t)clen);
    buf[total] = '\0';
    Prove_String *result = prove_string_new(buf, total);
    free(buf);
    return result;
}

static Prove_String *_path_join_str(Prove_String *base, Prove_String *child) {
    return _path_join(base, child->data);
}

/* ── Binary serialization format ────────────────────────────── */
/*
 * Format (all little-endian):
 *   [4] magic "PDAT"
 *   [4] format version (1)
 *   [8] data version (int64)
 *   [8] column_count
 *   For each column:
 *     [4] name length
 *     [N] name bytes
 *   [8] variant_count
 *   For each variant:
 *     [4] name length
 *     [N] name bytes
 *     For each column:
 *       [4] value length
 *       [N] value bytes
 */

static void _write_u32(FILE *f, uint32_t v) {
    fwrite(&v, 4, 1, f);
}

static void _write_i64(FILE *f, int64_t v) {
    fwrite(&v, 8, 1, f);
}

static void _write_str(FILE *f, Prove_String *s) {
    uint32_t len = (uint32_t)s->length;
    _write_u32(f, len);
    fwrite(s->data, 1, (size_t)len, f);
}

static bool _read_u32(FILE *f, uint32_t *out) {
    return fread(out, 4, 1, f) == 1;
}

static bool _read_i64(FILE *f, int64_t *out) {
    return fread(out, 8, 1, f) == 1;
}

static Prove_String *_read_str(FILE *f) {
    uint32_t len;
    if (!_read_u32(f, &len)) return NULL;
    if (len > 10 * 1024 * 1024) return NULL;  /* sanity limit: 10MB per string */
    char *buf = (char *)malloc(len + 1);
    if (!buf) return NULL;
    if (fread(buf, 1, len, f) != len) { free(buf); return NULL; }
    buf[len] = '\0';
    Prove_String *s = prove_string_new(buf, (int64_t)len);
    free(buf);
    return s;
}

/* ── Table constructor ──────────────────────────────────────── */

Prove_DatabaseTable *prove_db_table_new(Prove_String *name, int64_t col_count,
                                         Prove_String **col_names) {
    Prove_DatabaseTable *t = (Prove_DatabaseTable *)prove_alloc(sizeof(Prove_DatabaseTable));
    t->name = name;
    prove_retain(name);
    t->version = 0;
    t->column_count = col_count;
    t->column_names = (Prove_String **)calloc((size_t)col_count, sizeof(Prove_String *));
    if (!t->column_names) prove_panic("out of memory");
    for (int64_t i = 0; i < col_count; i++) {
        t->column_names[i] = col_names[i];
        prove_retain(col_names[i]);
    }
    t->variant_count = 0;
    t->variant_names = NULL;
    t->values = NULL;
    return t;
}

void prove_db_table_add_variant(Prove_DatabaseTable *table,
                                 Prove_String *variant_name,
                                 Prove_String **values) {
    int64_t n = table->variant_count + 1;
    table->variant_names = (Prove_String **)realloc(table->variant_names,
                                                      (size_t)n * sizeof(Prove_String *));
    table->values = (Prove_String ***)realloc(table->values,
                                                (size_t)n * sizeof(Prove_String **));
    if (!table->variant_names || !table->values) prove_panic("out of memory");

    table->variant_names[n - 1] = variant_name;
    prove_retain(variant_name);

    Prove_String **row = (Prove_String **)calloc((size_t)table->column_count, sizeof(Prove_String *));
    if (!row) prove_panic("out of memory");
    for (int64_t i = 0; i < table->column_count; i++) {
        row[i] = values[i];
        prove_retain(values[i]);
    }
    table->values[n - 1] = row;
    table->variant_count = n;
}

/* ── Serialize table to file ────────────────────────────────── */

static bool _serialize_table(Prove_DatabaseTable *table, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return false;

    _write_u32(f, PROVE_DB_MAGIC);
    _write_u32(f, PROVE_DB_VERSION);
    _write_i64(f, table->version);
    _write_i64(f, table->column_count);

    for (int64_t i = 0; i < table->column_count; i++) {
        _write_str(f, table->column_names[i]);
    }

    _write_i64(f, table->variant_count);
    for (int64_t v = 0; v < table->variant_count; v++) {
        _write_str(f, table->variant_names[v]);
        for (int64_t c = 0; c < table->column_count; c++) {
            _write_str(f, table->values[v][c]);
        }
    }

    fclose(f);
    return true;
}

/* ── Deserialize table from file ────────────────────────────── */

static Prove_DatabaseTable *_deserialize_table(const char *path, const char *name) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    uint32_t magic, ver;
    if (!_read_u32(f, &magic) || magic != PROVE_DB_MAGIC) { fclose(f); return NULL; }
    if (!_read_u32(f, &ver) || ver != PROVE_DB_VERSION) { fclose(f); return NULL; }

    int64_t data_version;
    if (!_read_i64(f, &data_version)) { fclose(f); return NULL; }

    int64_t col_count;
    if (!_read_i64(f, &col_count)) { fclose(f); return NULL; }
    if (col_count < 0 || col_count > 10000) { fclose(f); return NULL; }

    Prove_String **col_names = (Prove_String **)calloc((size_t)col_count, sizeof(Prove_String *));
    if (!col_names) { fclose(f); return NULL; }

    for (int64_t i = 0; i < col_count; i++) {
        col_names[i] = _read_str(f);
        if (!col_names[i]) { fclose(f); free(col_names); return NULL; }
    }

    Prove_String *tname = prove_string_from_cstr(name);
    Prove_DatabaseTable *table = prove_db_table_new(tname, col_count, col_names);
    table->version = data_version;

    /* Free temporary col_names array (table_new retained them) */
    free(col_names);

    int64_t var_count;
    if (!_read_i64(f, &var_count)) { fclose(f); return NULL; }
    if (var_count < 0 || var_count > 1000000) { fclose(f); return NULL; }

    Prove_String **row = (Prove_String **)calloc((size_t)col_count, sizeof(Prove_String *));
    if (!row) { fclose(f); return NULL; }

    for (int64_t v = 0; v < var_count; v++) {
        Prove_String *vname = _read_str(f);
        if (!vname) { fclose(f); free(row); return NULL; }
        for (int64_t c = 0; c < col_count; c++) {
            row[c] = _read_str(f);
            if (!row[c]) { fclose(f); free(row); return NULL; }
        }
        prove_db_table_add_variant(table, vname, row);
    }

    free(row);
    fclose(f);
    return table;
}

/* ── Database channel ───────────────────────────────────────── */

Prove_Result prove_db_create(Prove_String *path) {
    if (_mkdir_p(_to_cstr(path)) != 0) {
        return prove_result_err(prove_string_from_cstr(strerror(errno)));
    }
    Prove_Database *db = (Prove_Database *)prove_alloc(sizeof(Prove_Database));
    db->path = path;
    prove_retain(path);
    return prove_result_ok_ptr(db);
}

bool prove_db_validates(Prove_String *path) {
    struct stat st;
    return (stat(_to_cstr(path), &st) == 0 && S_ISDIR(st.st_mode));
}

/* ── Table channel ──────────────────────────────────────────── */

Prove_Result prove_db_table_inputs(Prove_Database *db, Prove_String *name) {
    /* Path: db->path / name / current.dat */
    Prove_String *table_dir = _path_join_str(db->path, name);
    Prove_String *file_path = _path_join(table_dir, "current.dat");

    Prove_DatabaseTable *table = _deserialize_table(_to_cstr(file_path), name->data);
    if (!table) {
        return prove_result_err(prove_string_from_cstr("failed to load table"));
    }
    return prove_result_ok_ptr(table);
}

Prove_Result prove_db_table_outputs(Prove_Database *db, Prove_DatabaseTable *table) {
    /* Create table directory and versions subdirectory */
    Prove_String *table_dir = _path_join_str(db->path, table->name);
    if (_mkdir_p(_to_cstr(table_dir)) != 0) {
        return prove_result_err(prove_string_from_cstr(strerror(errno)));
    }

    Prove_String *versions_dir = _path_join(table_dir, "versions");
    if (_mkdir_p(_to_cstr(versions_dir)) != 0) {
        return prove_result_err(prove_string_from_cstr(strerror(errno)));
    }

    /* Optimistic concurrency: check current version on disk */
    Prove_String *current_path = _path_join(table_dir, "current.dat");
    FILE *existing = fopen(_to_cstr(current_path), "rb");
    if (existing) {
        uint32_t magic, ver;
        int64_t disk_version = 0;
        if (_read_u32(existing, &magic) && magic == PROVE_DB_MAGIC &&
            _read_u32(existing, &ver) &&
            _read_i64(existing, &disk_version)) {
            if (disk_version > table->version) {
                fclose(existing);
                return prove_result_err(prove_string_from_cstr("stale version"));
            }
        }
        fclose(existing);
    }

    /* Increment version */
    table->version++;

    /* Save versioned copy */
    char ver_name[64];
    snprintf(ver_name, sizeof(ver_name), "%lld.dat", (long long)table->version);
    Prove_String *ver_path = _path_join(versions_dir, ver_name);
    if (!_serialize_table(table, _to_cstr(ver_path))) {
        return prove_result_err(prove_string_from_cstr("failed to write version file"));
    }

    /* Save as current */
    if (!_serialize_table(table, _to_cstr(current_path))) {
        return prove_result_err(prove_string_from_cstr("failed to write current file"));
    }

    return prove_result_ok();
}

bool prove_db_table_validates(Prove_Database *db, Prove_String *name) {
    Prove_String *table_dir = _path_join_str(db->path, name);
    Prove_String *file_path = _path_join(table_dir, "current.dat");
    struct stat st;
    return (stat(_to_cstr(file_path), &st) == 0 && S_ISREG(st.st_mode));
}

/* ── Diff ───────────────────────────────────────────────────── */

/* Find variant index in table by name, or -1 */
static int64_t _find_variant(Prove_DatabaseTable *t, Prove_String *name) {
    for (int64_t i = 0; i < t->variant_count; i++) {
        if (prove_string_eq(t->variant_names[i], name)) return i;
    }
    return -1;
}

Prove_TableDiff *prove_db_diff(Prove_DatabaseTable *old_t, Prove_DatabaseTable *new_t) {
    Prove_TableDiff *diff = (Prove_TableDiff *)prove_alloc(sizeof(Prove_TableDiff));
    memset((char *)diff + sizeof(Prove_Header), 0, sizeof(Prove_TableDiff) - sizeof(Prove_Header));
    diff->header.refcount = 1;

    /* Pre-allocate max possible sizes */
    int64_t max_add = new_t->variant_count;
    int64_t max_rem = old_t->variant_count;
    int64_t max_chg = old_t->variant_count * old_t->column_count;

    Prove_DiffVariant *added = (Prove_DiffVariant *)calloc((size_t)max_add, sizeof(Prove_DiffVariant));
    Prove_DiffVariant *removed = (Prove_DiffVariant *)calloc((size_t)max_rem, sizeof(Prove_DiffVariant));
    Prove_DiffChange *changed = (Prove_DiffChange *)calloc((size_t)(max_chg > 0 ? max_chg : 1),
                                                             sizeof(Prove_DiffChange));
    int64_t nadd = 0, nrem = 0, nchg = 0;

    /* Find removed and changed variants */
    for (int64_t i = 0; i < old_t->variant_count; i++) {
        int64_t j = _find_variant(new_t, old_t->variant_names[i]);
        if (j < 0) {
            /* Removed */
            removed[nrem].variant = old_t->variant_names[i];
            prove_retain(old_t->variant_names[i]);
            int64_t cc = old_t->column_count;
            removed[nrem].values = (Prove_String **)calloc((size_t)cc, sizeof(Prove_String *));
            for (int64_t c = 0; c < cc; c++) {
                removed[nrem].values[c] = old_t->values[i][c];
                prove_retain(old_t->values[i][c]);
            }
            nrem++;
        } else {
            /* Check for value changes (only common columns) */
            int64_t cc = old_t->column_count < new_t->column_count ?
                         old_t->column_count : new_t->column_count;
            for (int64_t c = 0; c < cc; c++) {
                if (!prove_string_eq(old_t->values[i][c], new_t->values[j][c])) {
                    changed[nchg].variant = old_t->variant_names[i];
                    prove_retain(old_t->variant_names[i]);
                    changed[nchg].column = old_t->column_names[c];
                    prove_retain(old_t->column_names[c]);
                    changed[nchg].old_value = old_t->values[i][c];
                    prove_retain(old_t->values[i][c]);
                    changed[nchg].new_value = new_t->values[j][c];
                    prove_retain(new_t->values[j][c]);
                    nchg++;
                }
            }
        }
    }

    /* Find added variants */
    for (int64_t j = 0; j < new_t->variant_count; j++) {
        int64_t i = _find_variant(old_t, new_t->variant_names[j]);
        if (i < 0) {
            added[nadd].variant = new_t->variant_names[j];
            prove_retain(new_t->variant_names[j]);
            int64_t cc = new_t->column_count;
            added[nadd].values = (Prove_String **)calloc((size_t)cc, sizeof(Prove_String *));
            for (int64_t c = 0; c < cc; c++) {
                added[nadd].values[c] = new_t->values[j][c];
                prove_retain(new_t->values[j][c]);
            }
            nadd++;
        }
    }

    /* Schema changes (added/removed columns) */
    int64_t nadded_col = 0, nremoved_col = 0;
    Prove_String **added_cols = NULL;
    Prove_String **removed_cols = NULL;

    /* Find columns in new not in old */
    if (new_t->column_count > 0) {
        added_cols = (Prove_String **)calloc((size_t)new_t->column_count, sizeof(Prove_String *));
        for (int64_t c = 0; c < new_t->column_count; c++) {
            bool found = false;
            for (int64_t oc = 0; oc < old_t->column_count; oc++) {
                if (prove_string_eq(new_t->column_names[c], old_t->column_names[oc])) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                added_cols[nadded_col++] = new_t->column_names[c];
                prove_retain(new_t->column_names[c]);
            }
        }
    }

    /* Find columns in old not in new */
    if (old_t->column_count > 0) {
        removed_cols = (Prove_String **)calloc((size_t)old_t->column_count, sizeof(Prove_String *));
        for (int64_t c = 0; c < old_t->column_count; c++) {
            bool found = false;
            for (int64_t nc = 0; nc < new_t->column_count; nc++) {
                if (prove_string_eq(old_t->column_names[c], new_t->column_names[nc])) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                removed_cols[nremoved_col++] = old_t->column_names[c];
                prove_retain(old_t->column_names[c]);
            }
        }
    }

    diff->added_count = nadd;
    diff->added = added;
    diff->removed_count = nrem;
    diff->removed = removed;
    diff->changed_count = nchg;
    diff->changed = changed;
    diff->added_col_count = nadded_col;
    diff->added_columns = added_cols;
    diff->removed_col_count = nremoved_col;
    diff->removed_columns = removed_cols;

    return diff;
}

/* ── Patch ──────────────────────────────────────────────────── */

Prove_DatabaseTable *prove_db_patch(Prove_DatabaseTable *table, Prove_TableDiff *diff) {
    /* Clone the table */
    Prove_DatabaseTable *result = prove_db_table_new(table->name, table->column_count,
                                                      table->column_names);
    result->version = table->version;

    /* Copy all variants except removed ones */
    for (int64_t v = 0; v < table->variant_count; v++) {
        bool is_removed = false;
        for (int64_t r = 0; r < diff->removed_count; r++) {
            if (prove_string_eq(table->variant_names[v], diff->removed[r].variant)) {
                is_removed = true;
                break;
            }
        }
        if (!is_removed) {
            prove_db_table_add_variant(result, table->variant_names[v], table->values[v]);
        }
    }

    /* Apply value changes */
    for (int64_t ch = 0; ch < diff->changed_count; ch++) {
        int64_t vi = _find_variant(result, diff->changed[ch].variant);
        if (vi >= 0) {
            /* Find column index */
            for (int64_t c = 0; c < result->column_count; c++) {
                if (prove_string_eq(result->column_names[c], diff->changed[ch].column)) {
                    prove_release(result->values[vi][c]);
                    result->values[vi][c] = diff->changed[ch].new_value;
                    prove_retain(diff->changed[ch].new_value);
                    break;
                }
            }
        }
    }

    /* Add new variants */
    for (int64_t a = 0; a < diff->added_count; a++) {
        prove_db_table_add_variant(result, diff->added[a].variant, diff->added[a].values);
    }

    return result;
}

/* ── Merge ──────────────────────────────────────────────────── */

Prove_MergeResult *prove_db_merge(Prove_DatabaseTable *base,
                                   Prove_TableDiff *local,
                                   Prove_TableDiff *remote,
                                   Prove_ResolverFn resolver) {
    Prove_MergeResult *mr = (Prove_MergeResult *)prove_alloc(sizeof(Prove_MergeResult));

    /* Detect conflicts: changes to the same variant+column in both diffs */
    Prove_List *conflicts = prove_list_new(4);
    bool has_unresolved = false;

    /* Check value conflicts */
    for (int64_t l = 0; l < local->changed_count; l++) {
        for (int64_t r = 0; r < remote->changed_count; r++) {
            if (prove_string_eq(local->changed[l].variant, remote->changed[r].variant) &&
                prove_string_eq(local->changed[l].column, remote->changed[r].column)) {
                /* Same field changed in both — conflict */
                if (!prove_string_eq(local->changed[l].new_value, remote->changed[r].new_value)) {
                    Prove_Conflict *c = (Prove_Conflict *)calloc(1, sizeof(Prove_Conflict));
                    c->tag = PROVE_CONFLICT_VALUE;
                    c->data.value.variant = local->changed[l].variant;
                    c->data.value.column = local->changed[l].column;
                    c->data.value.local_val = local->changed[l].new_value;
                    c->data.value.remote_val = remote->changed[r].new_value;

                    if (resolver) {
                        Prove_Resolution res = resolver(*c);
                        if (res.tag == PROVE_RESOLUTION_REJECT) {
                            has_unresolved = true;
                            prove_list_push(conflicts, c);
                        } else {
                            /* Apply resolution by modifying the local diff value */
                            if (res.tag == PROVE_RESOLUTION_KEEP_REMOTE) {
                                local->changed[l].new_value = remote->changed[r].new_value;
                            } else if (res.tag == PROVE_RESOLUTION_USE_VALUE) {
                                local->changed[l].new_value = res.data.use_value;
                            }
                            /* KEEP_LOCAL: no change needed */
                            free(c);
                        }
                    } else {
                        has_unresolved = true;
                        prove_list_push(conflicts, c);
                    }
                }
            }
        }
    }

    /* Check addition conflicts (same variant added in both with different values) */
    for (int64_t l = 0; l < local->added_count; l++) {
        for (int64_t r = 0; r < remote->added_count; r++) {
            if (prove_string_eq(local->added[l].variant, remote->added[r].variant)) {
                Prove_Conflict *c = (Prove_Conflict *)calloc(1, sizeof(Prove_Conflict));
                c->tag = PROVE_CONFLICT_ADDITION;
                c->data.addition.variant = local->added[l].variant;
                /* Store values as lists for the conflict */
                c->data.addition.local_vals = prove_list_new(base->column_count);
                c->data.addition.remote_vals = prove_list_new(base->column_count);
                for (int64_t col = 0; col < base->column_count; col++) {
                    if (col < local->added_count && local->added[l].values) {
                        prove_list_push(c->data.addition.local_vals, local->added[l].values[col]);
                    }
                    if (col < remote->added_count && remote->added[r].values) {
                        prove_list_push(c->data.addition.remote_vals, remote->added[r].values[col]);
                    }
                }

                if (resolver) {
                    Prove_Resolution res = resolver(*c);
                    if (res.tag == PROVE_RESOLUTION_REJECT) {
                        has_unresolved = true;
                        prove_list_push(conflicts, c);
                    } else {
                        if (res.tag == PROVE_RESOLUTION_KEEP_REMOTE) {
                            /* Replace local added values with remote ones */
                            for (int64_t col = 0; col < base->column_count; col++) {
                                local->added[l].values[col] = remote->added[r].values[col];
                            }
                        }
                        /* Mark remote as duplicate so we skip it later */
                        remote->added[r].variant = NULL;
                        free(c);
                    }
                } else {
                    has_unresolved = true;
                    prove_list_push(conflicts, c);
                }
            }
        }
    }

    if (has_unresolved) {
        mr->tag = PROVE_MERGE_CONFLICTED;
        mr->data.conflicts = conflicts;
        return mr;
    }

    /* No unresolved conflicts — apply both diffs to base */
    Prove_DatabaseTable *merged = prove_db_patch(base, local);

    /* Apply non-conflicting remote changes */
    for (int64_t r = 0; r < remote->changed_count; r++) {
        /* Skip if already handled via conflict resolution */
        bool was_conflict = false;
        for (int64_t l = 0; l < local->changed_count; l++) {
            if (prove_string_eq(local->changed[l].variant, remote->changed[r].variant) &&
                prove_string_eq(local->changed[l].column, remote->changed[r].column)) {
                was_conflict = true;
                break;
            }
        }
        if (!was_conflict) {
            int64_t vi = _find_variant(merged, remote->changed[r].variant);
            if (vi >= 0) {
                for (int64_t c = 0; c < merged->column_count; c++) {
                    if (prove_string_eq(merged->column_names[c], remote->changed[r].column)) {
                        prove_release(merged->values[vi][c]);
                        merged->values[vi][c] = remote->changed[r].new_value;
                        prove_retain(remote->changed[r].new_value);
                        break;
                    }
                }
            }
        }
    }

    /* Add remote-only additions */
    for (int64_t r = 0; r < remote->added_count; r++) {
        if (remote->added[r].variant == NULL) continue;  /* already merged */
        /* Check if not also added locally */
        bool local_added = false;
        for (int64_t l = 0; l < local->added_count; l++) {
            if (local->added[l].variant &&
                prove_string_eq(local->added[l].variant, remote->added[r].variant)) {
                local_added = true;
                break;
            }
        }
        if (!local_added) {
            prove_db_table_add_variant(merged, remote->added[r].variant, remote->added[r].values);
        }
    }

    /* Apply remote removals */
    for (int64_t r = 0; r < remote->removed_count; r++) {
        int64_t vi = _find_variant(merged, remote->removed[r].variant);
        if (vi >= 0) {
            /* Remove by shifting */
            for (int64_t k = vi; k < merged->variant_count - 1; k++) {
                merged->variant_names[k] = merged->variant_names[k + 1];
                merged->values[k] = merged->values[k + 1];
            }
            merged->variant_count--;
        }
    }

    mr->tag = PROVE_MERGE_MERGED;
    mr->data.table = merged;
    return mr;
}

/* ── Binary channel ─────────────────────────────────────────── */

Prove_Result prove_db_binary_outputs(Prove_Database *db, Prove_String *name) {
    /* Load the current table and write a compiled lookup binary */
    Prove_String *table_dir = _path_join_str(db->path, name);
    Prove_String *current_path = _path_join(table_dir, "current.dat");
    Prove_String *binary_path = _path_join(table_dir, "lookup.bin");

    Prove_DatabaseTable *table = _deserialize_table(_to_cstr(current_path), name->data);
    if (!table) {
        return prove_result_err(prove_string_from_cstr("failed to load table for binary compilation"));
    }

    /*
     * Binary lookup format:
     *   [4]  entry count (uint32)
     *   For each variant:
     *     [4]  key length
     *     [N]  key bytes (variant name)
     *     [4]  value (variant index as uint32)
     */
    FILE *f = fopen(_to_cstr(binary_path), "wb");
    if (!f) {
        return prove_result_err(prove_string_from_cstr(strerror(errno)));
    }

    uint32_t count = (uint32_t)table->variant_count;
    _write_u32(f, count);

    for (int64_t i = 0; i < table->variant_count; i++) {
        _write_str(f, table->variant_names[i]);
        uint32_t idx = (uint32_t)i;
        _write_u32(f, idx);
    }

    fclose(f);
    return prove_result_ok();
}

Prove_Result prove_db_binary_inputs(Prove_String *path) {
    FILE *f = fopen(_to_cstr(path), "rb");
    if (!f) {
        return prove_result_err(prove_string_from_cstr(strerror(errno)));
    }

    uint32_t count;
    if (!_read_u32(f, &count)) { fclose(f); return prove_result_err(prove_string_from_cstr("invalid binary")); }

    /* Build a Prove_List of key-index pairs as strings "key=index" */
    Prove_List *entries = prove_list_new((int64_t)count);
    for (uint32_t i = 0; i < count; i++) {
        Prove_String *key = _read_str(f);
        uint32_t idx;
        if (!key || !_read_u32(f, &idx)) {
            fclose(f);
            return prove_result_err(prove_string_from_cstr("corrupt binary file"));
        }
        prove_list_push(entries, key);
    }

    fclose(f);
    return prove_result_ok_ptr(entries);
}

/* ── Integrity channel ──────────────────────────────────────── */

Prove_String *prove_db_integrity(Prove_DatabaseTable *table) {
    /* Serialize table data to a buffer, then SHA-256 hash it */
    /* We hash: name + columns + all variant names + all values */
    size_t buf_cap = 4096;
    size_t buf_len = 0;
    uint8_t *buf = (uint8_t *)malloc(buf_cap);
    if (!buf) prove_panic("out of memory");

    #define APPEND(data, len) do { \
        while (buf_len + (size_t)(len) > buf_cap) { \
            buf_cap *= 2; \
            buf = (uint8_t *)realloc(buf, buf_cap); \
            if (!buf) prove_panic("out of memory"); \
        } \
        memcpy(buf + buf_len, (data), (size_t)(len)); \
        buf_len += (size_t)(len); \
    } while(0)

    /* Hash table name */
    APPEND(table->name->data, table->name->length);

    /* Hash column names */
    for (int64_t i = 0; i < table->column_count; i++) {
        APPEND(table->column_names[i]->data, table->column_names[i]->length);
    }

    /* Hash variant names and values */
    for (int64_t v = 0; v < table->variant_count; v++) {
        APPEND(table->variant_names[v]->data, table->variant_names[v]->length);
        for (int64_t c = 0; c < table->column_count; c++) {
            APPEND(table->values[v][c]->data, table->values[v][c]->length);
        }
    }

    #undef APPEND

    /* Compute SHA-256 */
    Prove_ByteArray *data = (Prove_ByteArray *)prove_alloc(sizeof(Prove_ByteArray) + buf_len);
    data->length = (int64_t)buf_len;
    memcpy(data->data, buf, buf_len);
    free(buf);

    Prove_String *hash = prove_crypto_sha256_string((Prove_String *)data);
    return hash;
}

/* ── Rollback channel ───────────────────────────────────────── */

Prove_Result prove_db_rollback(Prove_Database *db, Prove_String *name, int64_t version) {
    Prove_String *table_dir = _path_join_str(db->path, name);
    Prove_String *versions_dir = _path_join(table_dir, "versions");

    /* Load the requested version */
    char ver_name[64];
    snprintf(ver_name, sizeof(ver_name), "%lld.dat", (long long)version);
    Prove_String *ver_path = _path_join(versions_dir, ver_name);

    Prove_DatabaseTable *table = _deserialize_table(_to_cstr(ver_path), name->data);
    if (!table) {
        return prove_result_err(prove_string_from_cstr("version not found"));
    }

    /* Write it as the new current (with incremented version) */
    /* First read current version to get next version number */
    Prove_String *current_path = _path_join(table_dir, "current.dat");
    FILE *cf = fopen(_to_cstr(current_path), "rb");
    int64_t cur_ver = 0;
    if (cf) {
        uint32_t magic, fver;
        if (_read_u32(cf, &magic) && magic == PROVE_DB_MAGIC &&
            _read_u32(cf, &fver) && _read_i64(cf, &cur_ver)) {
            /* got it */
        }
        fclose(cf);
    }

    table->version = cur_ver + 1;

    /* Save versioned copy */
    snprintf(ver_name, sizeof(ver_name), "%lld.dat", (long long)table->version);
    Prove_String *new_ver_path = _path_join(versions_dir, ver_name);
    if (!_serialize_table(table, _to_cstr(new_ver_path))) {
        return prove_result_err(prove_string_from_cstr("failed to write rollback version"));
    }

    /* Save as current */
    if (!_serialize_table(table, _to_cstr(current_path))) {
        return prove_result_err(prove_string_from_cstr("failed to write current after rollback"));
    }

    return prove_result_ok_ptr(table);
}

/* ── Version channel ────────────────────────────────────────── */

Prove_Result prove_db_version_inputs(Prove_Database *db, Prove_String *name) {
    Prove_String *table_dir = _path_join_str(db->path, name);
    Prove_String *versions_dir = _path_join(table_dir, "versions");

    DIR *d = opendir(_to_cstr(versions_dir));
    if (!d) {
        return prove_result_err(prove_string_from_cstr("cannot open versions directory"));
    }

    Prove_List *versions = prove_list_new(8);
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {
        /* Skip . and .. and non-dat files */
        size_t nlen = strlen(entry->d_name);
        if (nlen < 5) continue;
        if (strcmp(entry->d_name + nlen - 4, ".dat") != 0) continue;

        /* Extract version number from filename */
        char *endp;
        long long vnum = strtoll(entry->d_name, &endp, 10);
        if (endp == entry->d_name || strcmp(endp, ".dat") != 0) continue;

        /* Get file modification time */
        char full_path[4096];
        snprintf(full_path, sizeof(full_path), "%s/%s",
                 _to_cstr(versions_dir), entry->d_name);
        struct stat st;
        int64_t mtime = 0;
        if (stat(full_path, &st) == 0) {
            mtime = (int64_t)st.st_mtime;
        }

        /* Compute hash of the version file */
        Prove_DatabaseTable *vtable = _deserialize_table(full_path, name->data);
        Prove_String *hash = prove_string_from_cstr("");
        if (vtable) {
            hash = prove_db_integrity(vtable);
        }

        Prove_Version *ver = (Prove_Version *)prove_alloc(sizeof(Prove_Version));
        ver->number = (int64_t)vnum;
        ver->timestamp = mtime;
        ver->hash = hash;
        prove_list_push(versions, ver);
    }
    closedir(d);

    return prove_result_ok_ptr(versions);
}
