#include "prove_intern.h"
#include "prove_hash.h"
#include <stdlib.h>
#include <string.h>

#define INTERN_INITIAL_CAP 256
#define INTERN_LOAD_FACTOR 75  /* percent */

static void intern_grow(ProveInternTable *t);

ProveInternTable *prove_intern_table_new(ProveArena *a) {
    ProveInternTable *t = (ProveInternTable *)malloc(sizeof(ProveInternTable));
    if (!t) return NULL;
    t->arena = a;
    t->capacity = INTERN_INITIAL_CAP;
    t->count = 0;
    t->entries = (ProveInternEntry *)calloc(t->capacity, sizeof(ProveInternEntry));
    if (!t->entries) { free(t); return NULL; }
    return t;
}

const char *prove_intern(ProveInternTable *t, const char *s, size_t len) {
    if (!t || !s) return NULL;

    uint32_t h = prove_hash(s, len);
    size_t mask = t->capacity - 1;
    size_t idx = h & mask;

    /* Linear probe — look for existing entry */
    for (;;) {
        ProveInternEntry *e = &t->entries[idx];
        if (e->str == NULL) break;  /* empty slot */
        if (e->hash == h && e->len == len && memcmp(e->str, s, len) == 0) {
            return e->str;  /* already interned */
        }
        idx = (idx + 1) & mask;
    }

    /* Grow if needed */
    if ((t->count + 1) * 100 > t->capacity * INTERN_LOAD_FACTOR) {
        intern_grow(t);
        /* Recompute slot after growth */
        mask = t->capacity - 1;
        idx = h & mask;
        while (t->entries[idx].str != NULL) {
            idx = (idx + 1) & mask;
        }
    }

    /* Copy string into arena */
    char *copy = (char *)prove_arena_alloc(t->arena, len + 1, 1);
    if (!copy) return NULL;
    memcpy(copy, s, len);
    copy[len] = '\0';

    t->entries[idx].str = copy;
    t->entries[idx].len = len;
    t->entries[idx].hash = h;
    t->count++;

    return copy;
}

static void intern_grow(ProveInternTable *t) {
    size_t old_cap = t->capacity;
    ProveInternEntry *old = t->entries;

    t->capacity = old_cap * 2;
    t->entries = (ProveInternEntry *)calloc(t->capacity, sizeof(ProveInternEntry));
    if (!t->entries) {
        /* Fallback: keep old table */
        t->entries = old;
        t->capacity = old_cap;
        return;
    }

    size_t mask = t->capacity - 1;
    for (size_t i = 0; i < old_cap; i++) {
        if (old[i].str != NULL) {
            size_t idx = old[i].hash & mask;
            while (t->entries[idx].str != NULL) {
                idx = (idx + 1) & mask;
            }
            t->entries[idx] = old[i];
        }
    }
    free(old);
}

void prove_intern_table_free(ProveInternTable *t) {
    if (!t) return;
    free(t->entries);
    free(t);
}
