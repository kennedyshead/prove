#ifndef PROVE_LIST_OPS_H
#define PROVE_LIST_OPS_H

#include "prove_runtime.h"
#include "prove_list.h"
#include "prove_option.h"
#include "prove_string.h"

/* ── Length ───────────────────────────────────────────────────── */

int64_t prove_list_ops_length(Prove_List *list);

/* ── First / Last (typed variants) ──────────────────────────── */

Prove_Option prove_list_ops_first_int(Prove_List *list);
Prove_Option prove_list_ops_first_str(Prove_List *list);
Prove_Option prove_list_ops_last_int(Prove_List *list);
Prove_Option prove_list_ops_last_str(Prove_List *list);

/* ── Empty ───────────────────────────────────────────────────── */

bool prove_list_ops_empty(Prove_List *list);

/* ── Contains (typed variants) ──────────────────────────────── */

bool prove_list_ops_contains_int(Prove_List *list, int64_t value);
bool prove_list_ops_contains_str(Prove_List *list, Prove_String *value);

/* ── Index (typed variants) ─────────────────────────────────── */

Prove_Option prove_list_ops_index_int(Prove_List *list, int64_t value);
Prove_Option prove_list_ops_index_str(Prove_List *list, Prove_String *value);

/* ── Slice ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_slice(Prove_List *list, int64_t start, int64_t end);

/* ── Reverse ─────────────────────────────────────────────────── */

Prove_List *prove_list_ops_reverse(Prove_List *list);

/* ── Sort (typed variants) ──────────────────────────────────── */

Prove_List *prove_list_ops_sort_int(Prove_List *list);
Prove_List *prove_list_ops_sort_str(Prove_List *list);

/* ── Range ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_range(int64_t start, int64_t end);

#endif /* PROVE_LIST_OPS_H */
