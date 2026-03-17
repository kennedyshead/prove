#ifndef PROVE_LOOKUP_H
#define PROVE_LOOKUP_H

#include <stddef.h>
#include <stdint.h>

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

/* Entry in a binary lookup reverse table (integer key -> variant index). */
typedef struct {
    int64_t key;
    int value;
} Prove_IntLookupEntry;

/* Reverse lookup table: maps integer keys to variant indices. */
typedef struct {
    const Prove_IntLookupEntry *entries;
    int count;
} Prove_IntLookupTable;

/* Find variant index for string key, or -1 if not found (linear scan). */
int prove_lookup_find(const Prove_LookupTable *table, const char *key);

/* Find variant index for integer key, or -1 if not found (linear scan). */
int prove_lookup_find_int(const Prove_IntLookupTable *table, int64_t key);

/* Find variant index for string key, or -1 if not found (binary search, entries must be sorted). */
int prove_lookup_find_sorted(const Prove_LookupTable *table, const char *key);

/* Find variant index for integer key, or -1 if not found (binary search, entries must be sorted). */
int prove_lookup_find_int_sorted(const Prove_IntLookupTable *table, int64_t key);

#endif /* PROVE_LOOKUP_H */
