#include "prove_arena.h"
#include <stdlib.h>
#include <stdint.h>

#define ARENA_DEFAULT_SIZE (1024 * 1024)  /* 1 MB */

static ProveArenaChunk *chunk_new(size_t data_size) {
    ProveArenaChunk *c = (ProveArenaChunk *)malloc(sizeof(ProveArenaChunk) + data_size);
    if (!c) return NULL;
    c->next = NULL;
    c->size = data_size;
    c->used = 0;
    return c;
}

ProveArena *prove_arena_new(size_t initial_size) {
    if (initial_size == 0) initial_size = ARENA_DEFAULT_SIZE;
    ProveArena *a = (ProveArena *)malloc(sizeof(ProveArena));
    if (!a) return NULL;
    a->head = chunk_new(initial_size);
    if (!a->head) { free(a); return NULL; }
    a->first = a->head;
    return a;
}

void *prove_arena_alloc(ProveArena *a, size_t size, size_t align) {
    if (!a || !a->head) return NULL;
    /* Align the current offset */
    size_t offset = a->head->used;
    size_t aligned = (offset + align - 1) & ~(align - 1);
    if (aligned + size <= a->head->size) {
        a->head->used = aligned + size;
        return a->head->data + aligned;
    }
    /* Need a new chunk — at least 2x current or enough for this alloc */
    size_t new_size = a->head->size * 2;
    if (new_size < size + align) new_size = size + align;
    ProveArenaChunk *c = chunk_new(new_size);
    if (!c) return NULL;
    c->next = NULL;
    a->head->next = c;
    a->head = c;
    /* Align within the fresh chunk (offset is 0, so aligned == 0 for power-of-2 align) */
    size_t fresh_aligned = (align - 1) & ~(align - 1);  /* always 0 */
    c->used = fresh_aligned + size;
    return c->data + fresh_aligned;
}

void prove_arena_reset(ProveArena *a) {
    if (!a) return;
    ProveArenaChunk *c = a->first;
    while (c) {
        c->used = 0;
        c = c->next;
    }
    a->head = a->first;
}

void prove_arena_free(ProveArena *a) {
    if (!a) return;
    ProveArenaChunk *c = a->first;
    while (c) {
        ProveArenaChunk *next = c->next;
        free(c);
        c = next;
    }
    free(a);
}
