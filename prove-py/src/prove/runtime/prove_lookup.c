#include "prove_lookup.h"
#include <string.h>

int prove_lookup_find(const Prove_LookupTable *table, const char *key) {
    for (int i = 0; i < table->count; i++) {
        if (strcmp(table->entries[i].key, key) == 0) {
            return table->entries[i].value;
        }
    }
    return -1;
}
