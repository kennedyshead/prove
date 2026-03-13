#ifndef PROVE_LIST_H
#define PROVE_LIST_H

#include "prove_runtime.h"
#include "prove_region.h"

/* ── Prove_List (pointer array) ───────────────────────────────── */

typedef struct {
    Prove_Header  header;
    bool          is_region; /* true if data was region-allocated (no realloc) */
    int64_t       length;
    int64_t       capacity;
    void        **data;
} Prove_List;

Prove_List *prove_list_new(int64_t initial_cap);
Prove_List *prove_list_new_region(ProveRegion *r, int64_t initial_cap);
void        prove_list_push(Prove_List *list, void *elem);
void       *prove_list_get(Prove_List *list, int64_t index);
int64_t     prove_list_len(Prove_List *list);
void        prove_list_free(Prove_List *list);

#endif /* PROVE_LIST_H */
