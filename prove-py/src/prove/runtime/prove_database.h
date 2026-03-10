#ifndef PROVE_DATABASE_H
#define PROVE_DATABASE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_hash_crypto.h"
#include "prove_bytes.h"

/* ── Magic and version for binary format ────────────────────── */

#define PROVE_DB_MAGIC      0x50444154  /* "PDAT" */
#define PROVE_DB_VERSION    1

/* ── Database handle ────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *path;
} Prove_Database;

/* ── DatabaseTable ──────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *name;
    int64_t       version;
    int64_t       column_count;
    Prove_String **column_names;
    int64_t       variant_count;
    Prove_String **variant_names;
    Prove_String ***values;  /* [variant_count][column_count] */
} Prove_DatabaseTable;

/* ── Version metadata ───────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    int64_t       number;
    int64_t       timestamp;
    Prove_String *hash;
} Prove_Version;

/* ── Diff types ─────────────────────────────────────────────── */

typedef struct {
    Prove_String  *variant;
    Prove_String **values;     /* column_count values */
} Prove_DiffVariant;

typedef struct {
    Prove_String *variant;
    Prove_String *column;
    Prove_String *old_value;
    Prove_String *new_value;
} Prove_DiffChange;

typedef struct {
    Prove_Header        header;
    int64_t             added_count;
    Prove_DiffVariant  *added;
    int64_t             removed_count;
    Prove_DiffVariant  *removed;
    int64_t             changed_count;
    Prove_DiffChange   *changed;
    /* Schema changes */
    int64_t             added_col_count;
    Prove_String      **added_columns;
    int64_t             removed_col_count;
    Prove_String      **removed_columns;
} Prove_TableDiff;

/* ── Merge types (tagged unions) ────────────────────────────── */

typedef enum {
    PROVE_CONFLICT_VALUE    = 0,
    PROVE_CONFLICT_ADDITION = 1,
    PROVE_CONFLICT_SCHEMA   = 2,
} Prove_ConflictTag;

typedef struct {
    Prove_ConflictTag tag;
    union {
        struct { Prove_String *variant; Prove_String *column;
                 Prove_String *local_val; Prove_String *remote_val; } value;
        struct { Prove_String *variant;
                 Prove_List *local_vals; Prove_List *remote_vals; } addition;
        struct { Prove_List *base_columns; Prove_List *changed_columns; } schema;
    } data;
} Prove_Conflict;

typedef enum {
    PROVE_RESOLUTION_KEEP_LOCAL  = 0,
    PROVE_RESOLUTION_KEEP_REMOTE = 1,
    PROVE_RESOLUTION_USE_VALUE   = 2,
    PROVE_RESOLUTION_REJECT      = 3,
} Prove_ResolutionTag;

typedef struct {
    Prove_ResolutionTag tag;
    union {
        Prove_String *use_value;
        Prove_String *reject_reason;
    } data;
} Prove_Resolution;

typedef enum {
    PROVE_MERGE_MERGED     = 0,
    PROVE_MERGE_CONFLICTED = 1,
} Prove_MergeResultTag;

typedef struct {
    Prove_Header          header;
    Prove_MergeResultTag  tag;
    union {
        Prove_DatabaseTable *table;
        Prove_List          *conflicts;  /* List of Prove_Conflict */
    } data;
} Prove_MergeResult;

/* Resolver callback: takes a Prove_Conflict, returns Prove_Resolution */
typedef Prove_Resolution (*Prove_ResolverFn)(Prove_Conflict);

/* ── Database channel ───────────────────────────────────────── */

Prove_Result prove_db_create(Prove_String *path);
bool         prove_db_validates(Prove_String *path);

/* ── Table channel ──────────────────────────────────────────── */

Prove_Result prove_db_table_inputs(Prove_Database *db, Prove_String *name);
Prove_Result prove_db_table_outputs(Prove_Database *db, Prove_DatabaseTable *table);
bool         prove_db_table_validates(Prove_Database *db, Prove_String *name);

/* ── Diff / patch / merge ───────────────────────────────────── */

Prove_TableDiff   *prove_db_diff(Prove_DatabaseTable *old_t, Prove_DatabaseTable *new_t);
Prove_DatabaseTable *prove_db_patch(Prove_DatabaseTable *table, Prove_TableDiff *diff);
Prove_MergeResult *prove_db_merge(Prove_DatabaseTable *base,
                                   Prove_TableDiff *local,
                                   Prove_TableDiff *remote,
                                   Prove_ResolverFn resolver);

/* ── Binary channel ─────────────────────────────────────────── */

Prove_Result prove_db_binary_outputs(Prove_Database *db, Prove_String *name);
Prove_Result prove_db_binary_inputs(Prove_String *path);

/* ── Integrity channel ──────────────────────────────────────── */

Prove_String *prove_db_integrity(Prove_DatabaseTable *table);

/* ── Rollback channel ───────────────────────────────────────── */

Prove_Result prove_db_rollback(Prove_Database *db, Prove_String *name, int64_t version);

/* ── Version channel ────────────────────────────────────────── */

Prove_Result prove_db_version_inputs(Prove_Database *db, Prove_String *name);

/* ── Internal helpers (for testing) ─────────────────────────── */

Prove_DatabaseTable *prove_db_table_new(Prove_String *name, int64_t col_count,
                                         Prove_String **col_names);
void prove_db_table_add_variant(Prove_DatabaseTable *table,
                                 Prove_String *variant_name,
                                 Prove_String **values);

#endif /* PROVE_DATABASE_H */
