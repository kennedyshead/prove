#ifndef PROVE_STORE_H
#define PROVE_STORE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_result.h"
#include "prove_hash_crypto.h"
#include "prove_bytes.h"
#include "prove_input_output.h"
#include "prove_path.h"

/* ── Magic and version for binary format ────────────────────── */

#define PROVE_STORE_MAGIC      0x50444154  /* "PDAT" */
#define PROVE_STORE_VERSION    1

/* ── Store handle ───────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *path;
} Prove_Store;

/* ── StoreTable ─────────────────────────────────────────────── */

typedef struct {
    Prove_Header  header;
    Prove_String *name;
    int64_t       version;
    int64_t       column_count;
    Prove_String **column_names;
    int64_t       variant_count;
    Prove_String **variant_names;
    Prove_String ***values;  /* [variant_count][column_count] */
} Prove_StoreTable;

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
    Prove_String **values;     /* value_count values */
    int64_t       value_count;
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
        Prove_StoreTable *table;
        Prove_List       *conflicts;  /* List of Prove_Conflict */
    } data;
} Prove_MergeResult;

/* Resolver callback: takes pointer to Conflict, returns pointer to Resolution */
typedef Prove_Resolution* (*Prove_ResolverFn)(Prove_Conflict*);

/* ── Resolution constructors ────────────────────────────────── */

Prove_Resolution *prove_store_resolution_keep_local(void);
Prove_Resolution *prove_store_resolution_keep_remote(void);
Prove_Resolution *prove_store_resolution_use_value(Prove_String *value);
Prove_Resolution *prove_store_resolution_reject(Prove_String *reason);

/* ── Store channel ──────────────────────────────────────────── */

Prove_Result prove_store_create(Prove_String *path);
bool         prove_store_validates(Prove_String *path);

/* ── Table channel ──────────────────────────────────────────── */

Prove_Result prove_store_table_inputs(Prove_Store *store, Prove_String *name);
Prove_Result prove_store_table_outputs(Prove_Store *store, Prove_StoreTable *table);
bool         prove_store_table_validates(Prove_Store *store, Prove_String *name);

/* ── Diff / patch / merge ───────────────────────────────────── */

Prove_TableDiff  *prove_store_diff(Prove_StoreTable *old_t, Prove_StoreTable *new_t);
Prove_StoreTable *prove_store_patch(Prove_StoreTable *table, Prove_TableDiff *diff);
Prove_MergeResult *prove_store_merge(Prove_StoreTable *base,
                                      Prove_TableDiff *local,
                                      Prove_TableDiff *remote,
                                      Prove_ResolverFn resolver);

/* ── MergeResult accessors ──────────────────────────────────── */

bool              prove_store_merged_validates(Prove_MergeResult *mr);
Prove_StoreTable *prove_store_merged(Prove_MergeResult *mr);
Prove_List       *prove_store_conflicts(Prove_MergeResult *mr);

/* ── Conflict accessors ────────────────────────────────────── */

Prove_String *prove_store_conflict_variant(Prove_Conflict *c);
Prove_String *prove_store_conflict_column(Prove_Conflict *c);
Prove_String *prove_store_conflict_local_value(Prove_Conflict *c);
Prove_String *prove_store_conflict_remote_value(Prove_Conflict *c);

/* ── Lookup channel ─────────────────────────────────────────── */

Prove_Result prove_store_lookup_outputs(Prove_Store *store, Prove_String *name);
Prove_Result prove_store_lookup_inputs(Prove_String *path);

/* ── Integrity channel ──────────────────────────────────────── */

Prove_String *prove_store_integrity(Prove_StoreTable *table);

/* ── Rollback channel ───────────────────────────────────────── */

Prove_Result prove_store_rollback(Prove_Store *store, Prove_String *name, int64_t version);

/* ── Version channel ────────────────────────────────────────── */

Prove_Result prove_store_version_inputs(Prove_Store *store, Prove_String *name);

/* ── Internal helpers (for testing) ─────────────────────────── */

Prove_StoreTable *prove_store_table_new(Prove_String *name, int64_t col_count,
                                         Prove_String **col_names);
void prove_store_table_add_variant(Prove_StoreTable *table,
                                    Prove_String *variant_name,
                                    Prove_String **values);

/* ── Store-backed row addition (stdlib entry point) ────────── */

void prove_store_table_add(Prove_StoreTable *table, Prove_StoreTable *row);

/* ── Store-backed lookup ───────────────────────────────────── */

Prove_String *prove_store_table_find(Prove_StoreTable *table,
                                      Prove_String *key,
                                      int64_t key_col,
                                      int64_t val_col);

int64_t prove_store_table_find_int(Prove_StoreTable *table,
                                    Prove_String *key,
                                    int64_t key_col,
                                    int64_t val_col);

#endif /* PROVE_STORE_H */
