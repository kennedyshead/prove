#ifndef PROVE_RUNTIME_H
#define PROVE_RUNTIME_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

/* ── Reference-counted header ─────────────────────────────────── */

typedef struct {
    int32_t refcount;
} Prove_Header;

static inline void prove_retain(void *obj) {
    if (obj) {
        ((Prove_Header *)obj)->refcount++;
    }
}

static inline void prove_release(void *obj) {
    if (obj) {
        Prove_Header *h = (Prove_Header *)obj;
        if (--h->refcount <= 0) {
            free(obj);
        }
    }
}

static inline void *prove_alloc(size_t size) {
    void *ptr = calloc(1, size);
    if (!ptr) {
        fprintf(stderr, "prove: out of memory\n");
        exit(1);
    }
    ((Prove_Header *)ptr)->refcount = 1;
    return ptr;
}

/* ── Panic ────────────────────────────────────────────────────── */

static inline _Noreturn void prove_panic(const char *msg) {
    fprintf(stderr, "prove: panic: %s\n", msg);
    exit(1);
}

/* ── Clamp ────────────────────────────────────────────────────── */

static inline int64_t prove_clamp(int64_t val, int64_t lo, int64_t hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

/* ── Runtime lifecycle ────────────────────────────────────────── */

void prove_runtime_init(void);
void prove_runtime_cleanup(void);

#endif /* PROVE_RUNTIME_H */
