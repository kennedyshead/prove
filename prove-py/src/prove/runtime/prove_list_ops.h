#ifndef PROVE_LIST_OPS_H
#define PROVE_LIST_OPS_H

#include "prove_runtime.h"
#include "prove_list.h"
#include "prove_string.h"
#include "prove_option.h"

/* ── Option types used by List module ────────────────────────── */

#ifndef PROVE_OPTION_INT64_T_DEFINED
#define PROVE_OPTION_INT64_T_DEFINED
PROVE_DEFINE_OPTION(int64_t, Prove_Option_int64_t)
#endif

#ifndef PROVE_OPTION_STRINGPTR_DEFINED
#define PROVE_OPTION_STRINGPTR_DEFINED
PROVE_DEFINE_OPTION(Prove_String*, Prove_Option_Prove_Stringptr)
#endif

/* ── Length ───────────────────────────────────────────────────── */

int64_t prove_list_ops_length(Prove_List *list);

/* ── First / Last ────────────────────────────────────────────── */

Prove_Option_int64_t       prove_list_ops_first_int(Prove_List *list);
Prove_Option_Prove_Stringptr prove_list_ops_first_str(Prove_List *list);
Prove_Option_int64_t       prove_list_ops_last_int(Prove_List *list);
Prove_Option_Prove_Stringptr prove_list_ops_last_str(Prove_List *list);

/* ── Empty ───────────────────────────────────────────────────── */

bool prove_list_ops_empty(Prove_List *list);

/* ── Contains ────────────────────────────────────────────────── */

bool prove_list_ops_contains_int(Prove_List *list, int64_t value);
bool prove_list_ops_contains_str(Prove_List *list, Prove_String *value);

/* ── Index ───────────────────────────────────────────────────── */

Prove_Option_int64_t prove_list_ops_index_int(Prove_List *list, int64_t value);
Prove_Option_int64_t prove_list_ops_index_str(Prove_List *list, Prove_String *value);

/* ── Slice ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_slice(Prove_List *list, int64_t start, int64_t end);

/* ── Reverse ─────────────────────────────────────────────────── */

Prove_List *prove_list_ops_reverse(Prove_List *list);

/* ── Sort ────────────────────────────────────────────────────── */

Prove_List *prove_list_ops_sort_int(Prove_List *list);
Prove_List *prove_list_ops_sort_str(Prove_List *list);

/* ── Range ───────────────────────────────────────────────────── */

Prove_List *prove_list_ops_range(int64_t start, int64_t end);

#endif /* PROVE_LIST_OPS_H */
