#ifndef PROVE_TABLE_H
#define PROVE_TABLE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_hash.h"
#include "prove_option.h"

/* ── Option<void*> for generic get ───────────────────────────── */

PROVE_DEFINE_OPTION(void*, Prove_Option_voidptr)

/* ── Hash table type ─────────────────────────────────────────── */

typedef struct {
    Prove_String *key;   /* NULL = empty slot */
    void         *value;
    uint32_t      hash;
} Prove_TableEntry;

typedef struct {
    Prove_Header     header;
    int64_t          count;
    int64_t          capacity;
    Prove_TableEntry *entries;
} Prove_Table;

/* ── Table operations ────────────────────────────────────────── */

Prove_Table  *prove_table_new(void);
bool          prove_table_has(Prove_String *key, Prove_Table *table);
Prove_Table  *prove_table_add(Prove_String *key, void *value, Prove_Table *table);
Prove_Option_voidptr prove_table_get(Prove_String *key, Prove_Table *table);
Prove_Table  *prove_table_remove(Prove_String *key, Prove_Table *table);
Prove_List   *prove_table_keys(Prove_Table *table);
Prove_List   *prove_table_values(Prove_Table *table);
int64_t       prove_table_length(Prove_Table *table);

#endif /* PROVE_TABLE_H */
