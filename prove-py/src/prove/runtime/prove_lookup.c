#include "prove_lookup.h"
#include <stdint.h>
#include <string.h>

int prove_lookup_find(const Prove_LookupTable *table, const char *key) {
    for (int i = 0; i < table->count; i++) {
        if (strcmp(table->entries[i].key, key) == 0) {
            return table->entries[i].value;
        }
    }
    return -1;
}

int prove_lookup_find_int(const Prove_IntLookupTable *table, int64_t key) {
    for (int i = 0; i < table->count; i++) {
        if (table->entries[i].key == key) {
            return table->entries[i].value;
        }
    }
    return -1;
}

int prove_lookup_find_sorted(const Prove_LookupTable *table, const char *key) {
    int lo = 0, hi = table->count - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        int cmp = strcmp(table->entries[mid].key, key);
        if (cmp == 0) return table->entries[mid].value;
        if (cmp < 0) lo = mid + 1;
        else hi = mid - 1;
    }
    return -1;
}

int prove_lookup_find_int_sorted(const Prove_IntLookupTable *table, int64_t key) {
    int lo = 0, hi = table->count - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        int64_t mk = table->entries[mid].key;
        if (mk == key) return table->entries[mid].value;
        if (mk < key) lo = mid + 1;
        else hi = mid - 1;
    }
    return -1;
}
