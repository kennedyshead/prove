#ifndef PROVE_PROVE_H
#define PROVE_PROVE_H

#include "prove_runtime.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_option.h"
#include "prove_result.h"
#include <tree_sitter/api.h>

/* ── Forward declare tree-sitter-prove language ──────────────── */

const TSLanguage *tree_sitter_prove(void);

/* ── Opaque types ────────────────────────────────────────────── */

typedef struct {
    Prove_Header header;    /* refcount (must be first for prove_retain/release) */
    TSTree     *ts_tree;
    char       *source;     /* owned copy of source text */
    uint32_t    source_len;
} Prove_Tree_Impl;

typedef Prove_Tree_Impl *Prove_Tree;

typedef struct {
    Prove_Header header;    /* refcount (must be first for prove_retain/release) */
    Prove_Tree  tree;       /* back-pointer (owns source + TSTree) */
    TSNode      node;       /* 24-byte value copy */
} Prove_Node_Impl;

typedef Prove_Node_Impl *Prove_Node;

/* ── Parse (registered under Parse module as tree()) ─────────── */

Prove_Result prove_parse_tree(Prove_String *source);
Prove_String *prove_parse_string_tree(Prove_Tree tree);

/* ── Tree accessors ──────────────────────────────────────────── */

Prove_Node prove_prove_root(Prove_Tree tree);

/* ── Node accessors ──────────────────────────────────────────── */

Prove_String *prove_prove_kind(Prove_Node node);
Prove_String *prove_prove_string(Prove_Node node);
Prove_List   *prove_prove_children(Prove_Node node);
Prove_Option  prove_prove_child(Prove_Node node, Prove_String *name);
int64_t       prove_prove_line(Prove_Node node);
int64_t       prove_prove_column(Prove_Node node);
bool          prove_prove_error(Prove_Node node);
int64_t       prove_prove_count(Prove_Node node);
Prove_List   *prove_prove_named_children(Prove_Node node);

#endif /* PROVE_PROVE_H */
