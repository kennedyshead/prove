#ifndef PROVE_ARENA_H
#define PROVE_ARENA_H

#include <stddef.h>

typedef struct ProveArenaChunk {
    struct ProveArenaChunk *next;
    size_t size;
    size_t used;
    char data[];  /* flexible array member */
} ProveArenaChunk;

typedef struct {
    ProveArenaChunk *head;    /* current chunk */
    ProveArenaChunk *first;   /* first chunk (for reset) */
} ProveArena;

/* Create a new arena. Pass 0 for default (1 MB). */
ProveArena *prove_arena_new(size_t initial_size);

/* Aligned bump allocation. Returns NULL only on OOM. */
void *prove_arena_alloc(ProveArena *a, size_t size, size_t align);

/* Rewind all chunks — reuse memory without freeing. */
void prove_arena_reset(ProveArena *a);

/* Free all chunks and the arena itself. */
void prove_arena_free(ProveArena *a);

#endif /* PROVE_ARENA_H */
