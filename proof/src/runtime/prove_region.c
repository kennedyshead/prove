#include "prove_region.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PROVE_REGION_CHUNK_SIZE 4096

typedef struct ProveRegionFrame {
    struct ProveRegionFrame *prev;
    size_t capacity;
    size_t used;
    bool is_boundary;  /* true for frames pushed by prove_region_enter */
    char data[];
} ProveRegionFrame;

ProveRegion *prove_region_new(void) {
    ProveRegion *r = (ProveRegion *)malloc(sizeof(ProveRegion));
    if (!r) {
        return NULL;
    }
    r->current = NULL;
    return r;
}

void *prove_region_alloc(ProveRegion *r, size_t size) {
    if (!r || size == 0) {
        return NULL;
    }

    size = (size + 7) & ~7;

    if (r->current && !r->current->is_boundary &&
        r->current->used + size <= r->current->capacity) {
        void *ptr = r->current->data + r->current->used;
        r->current->used += size;
        return ptr;
    }

    size_t chunk_size = PROVE_REGION_CHUNK_SIZE;
    if (size > chunk_size) {
        chunk_size = size + sizeof(ProveRegionFrame);
    }

    ProveRegionFrame *frame = (ProveRegionFrame *)malloc(chunk_size);
    if (!frame) {
        return NULL;
    }

    frame->prev = r->current;
    frame->capacity = chunk_size - sizeof(ProveRegionFrame);
    frame->used = size;
    frame->is_boundary = false;

    r->current = frame;

    return frame->data;
}

void prove_region_enter(ProveRegion *r) {
    if (!r) {
        return;
    }

    /* Lazy: allocate only a lightweight boundary marker (~32 bytes).
       Real data chunks are allocated on first prove_region_alloc. */
    ProveRegionFrame *frame = (ProveRegionFrame *)malloc(sizeof(ProveRegionFrame));
    if (!frame) {
        fprintf(stderr, "prove: panic: region enter: out of memory\n");
        exit(1);
    }

    frame->prev = r->current;
    frame->capacity = 0;
    frame->used = 0;
    frame->is_boundary = true;

    r->current = frame;
}

void prove_region_exit(ProveRegion *r) {
    if (!r || !r->current) {
        return;
    }

    /* Free frames until we reach the boundary frame from prove_region_enter */
    ProveRegionFrame *frame = r->current;
    while (frame && !frame->is_boundary) {
        ProveRegionFrame *prev = frame->prev;
        free(frame);
        frame = prev;
    }
    /* Free the boundary frame itself and restore the previous state */
    if (frame && frame->is_boundary) {
        r->current = frame->prev;
        free(frame);
    } else {
        r->current = NULL;
    }
}

void prove_region_free(ProveRegion *r) {
    if (!r) {
        return;
    }

    ProveRegionFrame *frame = r->current;
    while (frame) {
        ProveRegionFrame *prev = frame->prev;
        free(frame);
        frame = prev;
    }

    free(r);
}
