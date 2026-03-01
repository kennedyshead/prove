#ifndef PROVE_INTERN_H
#define PROVE_INTERN_H

#include <stddef.h>
#include <stdint.h>
#include "prove_arena.h"

typedef struct {
    const char *str;
    size_t len;
    uint32_t hash;
} ProveInternEntry;

typedef struct {
    ProveArena *arena;        /* arena for interned string storage */
    ProveInternEntry *entries;
    size_t capacity;
    size_t count;
} ProveInternTable;

/* Create a new intern table backed by the given arena. */
ProveInternTable *prove_intern_table_new(ProveArena *a);

/* Intern a string. Returns a pointer that is stable for the arena's lifetime.
   Equal strings return the same pointer (pointer equality). */
const char *prove_intern(ProveInternTable *t, const char *s, size_t len);

/* Free the table arrays. The arena frees the interned strings. */
void prove_intern_table_free(ProveInternTable *t);

#endif /* PROVE_INTERN_H */
