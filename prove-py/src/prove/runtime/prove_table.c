#include "prove_table.h"
#include <string.h>

#define TABLE_INITIAL_CAP 16
#define TABLE_LOAD_FACTOR 70 /* percent */

/* ── Internal helpers ────────────────────────────────────────── */

static uint32_t _hash_key(Prove_String *key) {
    return prove_hash(key->data, (size_t)key->length);
}

static int64_t _find_slot(Prove_TableEntry *entries, int64_t capacity,
                          Prove_String *key, uint32_t hash) {
    int64_t mask = capacity - 1;
    int64_t idx = (int64_t)(hash & (uint32_t)mask);

    for (;;) {
        Prove_TableEntry *e = &entries[idx];
        if (!e->key) return idx; /* empty slot */
        if (e->hash == hash && prove_string_eq(e->key, key)) return idx;
        idx = (idx + 1) & mask;
    }
}

static void _resize(Prove_Table *table) {
    int64_t new_cap = table->capacity * 2;
    Prove_TableEntry *new_entries = (Prove_TableEntry *)calloc(
        (size_t)new_cap, sizeof(Prove_TableEntry)
    );
    if (!new_entries) prove_panic("Table resize failed");

    /* Re-insert all existing entries */
    for (int64_t i = 0; i < table->capacity; i++) {
        Prove_TableEntry *e = &table->entries[i];
        if (e->key) {
            int64_t slot = _find_slot(new_entries, new_cap, e->key, e->hash);
            new_entries[slot] = *e;
        }
    }

    free(table->entries);
    table->entries = new_entries;
    table->capacity = new_cap;
}

/* ── Public API ──────────────────────────────────────────────── */

Prove_Table *prove_table_new(void) {
    Prove_Table *t = (Prove_Table *)prove_alloc(sizeof(Prove_Table));
    t->count = 0;
    t->capacity = TABLE_INITIAL_CAP;
    t->entries = (Prove_TableEntry *)calloc(
        TABLE_INITIAL_CAP, sizeof(Prove_TableEntry)
    );
    if (!t->entries) prove_panic("Table allocation failed");
    return t;
}

bool prove_table_has(Prove_String *key, Prove_Table *table) {
    if (!table || !key || table->count == 0) return false;
    uint32_t hash = _hash_key(key);
    int64_t slot = _find_slot(table->entries, table->capacity, key, hash);
    return table->entries[slot].key != NULL;
}

Prove_Table *prove_table_add(Prove_String *key, void *value, Prove_Table *table) {
    if (!table) prove_panic("Table.add: null table");
    if (!key) prove_panic("Table.add: null key");

    /* Resize if load factor exceeded */
    if ((table->count + 1) * 100 > table->capacity * TABLE_LOAD_FACTOR) {
        _resize(table);
    }

    uint32_t hash = _hash_key(key);
    int64_t slot = _find_slot(table->entries, table->capacity, key, hash);
    Prove_TableEntry *e = &table->entries[slot];

    if (e->key) {
        /* Update existing */
        e->value = value;
    } else {
        /* Insert new */
        prove_retain(key);
        e->key = key;
        e->hash = hash;
        e->value = value;
        table->count++;
    }

    return table;
}

Prove_Option_voidptr prove_table_get(Prove_String *key, Prove_Table *table) {
    if (!table || !key || table->count == 0) {
        return Prove_Option_voidptr_none();
    }
    uint32_t hash = _hash_key(key);
    int64_t slot = _find_slot(table->entries, table->capacity, key, hash);
    Prove_TableEntry *e = &table->entries[slot];
    if (e->key) {
        return Prove_Option_voidptr_some(e->value);
    }
    return Prove_Option_voidptr_none();
}

Prove_Table *prove_table_remove(Prove_String *key, Prove_Table *table) {
    if (!table || !key || table->count == 0) return table;

    uint32_t hash = _hash_key(key);
    int64_t slot = _find_slot(table->entries, table->capacity, key, hash);
    Prove_TableEntry *e = &table->entries[slot];

    if (!e->key) return table; /* key not found */

    /* Tombstone deletion: clear slot and re-insert displaced entries */
    prove_release(e->key);
    e->key = NULL;
    e->value = NULL;
    e->hash = 0;
    table->count--;

    /* Re-insert entries that may have been displaced past this slot */
    int64_t mask = table->capacity - 1;
    int64_t idx = (slot + 1) & mask;
    while (table->entries[idx].key) {
        Prove_TableEntry displaced = table->entries[idx];
        table->entries[idx].key = NULL;
        table->entries[idx].value = NULL;
        table->entries[idx].hash = 0;
        table->count--;

        /* Re-insert */
        int64_t new_slot = _find_slot(
            table->entries, table->capacity,
            displaced.key, displaced.hash
        );
        table->entries[new_slot] = displaced;
        table->count++;

        idx = (idx + 1) & mask;
    }

    return table;
}

Prove_List *prove_table_keys(Prove_Table *table) {
    Prove_List *list = prove_list_new(sizeof(Prove_String *), table ? table->count + 1 : 4);
    if (!table) return list;

    for (int64_t i = 0; i < table->capacity; i++) {
        if (table->entries[i].key) {
            Prove_String *k = table->entries[i].key;
            prove_list_push(&list, &k);
        }
    }
    return list;
}

Prove_List *prove_table_values(Prove_Table *table) {
    Prove_List *list = prove_list_new(sizeof(void *), table ? table->count + 1 : 4);
    if (!table) return list;

    for (int64_t i = 0; i < table->capacity; i++) {
        if (table->entries[i].key) {
            void *v = table->entries[i].value;
            prove_list_push(&list, &v);
        }
    }
    return list;
}

int64_t prove_table_length(Prove_Table *table) {
    return table ? table->count : 0;
}
