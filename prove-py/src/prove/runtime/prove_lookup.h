#ifndef PROVE_LOOKUP_H
#define PROVE_LOOKUP_H

#include <stddef.h>

/* Entry in a binary lookup reverse table (string key -> variant index). */
typedef struct {
    const char *key;
    int value;
} Prove_LookupEntry;

/* Reverse lookup table: maps string keys to variant indices. */
typedef struct {
    const Prove_LookupEntry *entries;
    int count;
} Prove_LookupTable;

/* Find variant index for key, or -1 if not found. */
int prove_lookup_find(const Prove_LookupTable *table, const char *key);

#endif /* PROVE_LOOKUP_H */
