#ifndef PROVE_LIST_H
#define PROVE_LIST_H

#include "prove_runtime.h"

/* ── Prove_List ───────────────────────────────────────────────── */

typedef struct {
    Prove_Header header;
    int64_t      length;
    int64_t      capacity;
    size_t       elem_size;
    char         data[];  /* flexible array member */
} Prove_List;

Prove_List *prove_list_new(size_t elem_size, int64_t initial_cap);
void        prove_list_push(Prove_List **list, const void *elem);
void       *prove_list_get(Prove_List *list, int64_t index);
int64_t     prove_list_len(Prove_List *list);

#endif /* PROVE_LIST_H */
