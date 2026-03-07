#ifndef PROVE_REGION_H
#define PROVE_REGION_H

#include <stddef.h>
#include <stdbool.h>

typedef struct ProveRegionFrame ProveRegionFrame;

typedef struct {
    ProveRegionFrame *current;
} ProveRegion;

ProveRegion *prove_region_new(void);

void *prove_region_alloc(ProveRegion *r, size_t size);

void prove_region_enter(ProveRegion *r);

void prove_region_exit(ProveRegion *r);

void prove_region_free(ProveRegion *r);

#endif /* PROVE_REGION_H */
