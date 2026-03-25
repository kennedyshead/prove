#include "prove_prove.h"
#include <stdlib.h>
#include <string.h>

/* ── Helpers ─────────────────────────────────────────────────── */

static Prove_Node prove_node_wrap(Prove_Tree tree, TSNode tsnode) {
    Prove_Node n = (Prove_Node)prove_alloc(sizeof(Prove_Node_Impl));
    n->tree = tree;
    n->node = tsnode;
    return n;
}

/* ── Parse ───────────────────────────────────────────────────── */

Prove_Result prove_parse_tree(Prove_String *source) {
    TSParser *parser = ts_parser_new();
    if (!parser) {
        return prove_result_err(prove_string_from_cstr("failed to create parser"));
    }
    ts_parser_set_language(parser, tree_sitter_prove());

    /* Copy source — tree-sitter does NOT own the input buffer. */
    char *src_copy = (char *)malloc((size_t)source->length + 1);
    if (!src_copy) {
        ts_parser_delete(parser);
        return prove_result_err(prove_string_from_cstr("out of memory"));
    }
    memcpy(src_copy, source->data, (size_t)source->length);
    src_copy[source->length] = '\0';

    TSTree *ts_tree = ts_parser_parse_string(
        parser, NULL, src_copy, (uint32_t)source->length);
    ts_parser_delete(parser);

    if (!ts_tree) {
        free(src_copy);
        return prove_result_err(prove_string_from_cstr("parse failed"));
    }

    Prove_Tree tree = (Prove_Tree)prove_alloc(sizeof(Prove_Tree_Impl));
    tree->ts_tree   = ts_tree;
    tree->source    = src_copy;
    tree->source_len = (uint32_t)source->length;

    return prove_result_ok_ptr(tree);
}

Prove_String *prove_parse_string_tree(Prove_Tree tree) {
    if (!tree->source || tree->source_len == 0) {
        return prove_string_from_cstr("");
    }
    return prove_string_new(tree->source, (int64_t)tree->source_len);
}

/* ── Tree accessors ──────────────────────────────────────────── */

Prove_Node prove_prove_root(Prove_Tree tree) {
    TSNode root = ts_tree_root_node(tree->ts_tree);
    return prove_node_wrap(tree, root);
}

/* ── Node accessors ──────────────────────────────────────────── */

Prove_String *prove_prove_kind(Prove_Node node) {
    const char *kind = ts_node_type(node->node);
    return prove_string_from_cstr(kind);
}

Prove_String *prove_prove_string(Prove_Node node) {
    uint32_t start = ts_node_start_byte(node->node);
    uint32_t end   = ts_node_end_byte(node->node);
    const char *src = node->tree->source;
    uint32_t src_len = node->tree->source_len;

    if (!src || start >= src_len) {
        return prove_string_from_cstr("");
    }
    if (end > src_len) end = src_len;

    return prove_string_new(src + start, (int64_t)(end - start));
}

Prove_List *prove_prove_children(Prove_Node node) {
    uint32_t count = ts_node_child_count(node->node);
    Prove_List *list = prove_list_new((int64_t)count);
    for (uint32_t i = 0; i < count; i++) {
        TSNode child = ts_node_child(node->node, i);
        prove_list_push(list, prove_node_wrap(node->tree, child));
    }
    return list;
}

Prove_Option prove_prove_child(Prove_Node node, Prove_String *name) {
    TSNode child = ts_node_child_by_field_name(
        node->node, name->data, (uint32_t)name->length);
    if (ts_node_is_null(child)) {
        return prove_option_none();
    }
    return prove_option_some((Prove_Value *)prove_node_wrap(node->tree, child));
}

int64_t prove_prove_line(Prove_Node node) {
    TSPoint p = ts_node_start_point(node->node);
    return (int64_t)(p.row + 1); /* tree-sitter 0-based → Prove 1-based */
}

int64_t prove_prove_column(Prove_Node node) {
    TSPoint p = ts_node_start_point(node->node);
    return (int64_t)p.column;
}

bool prove_prove_error(Prove_Node node) {
    return ts_node_is_error(node->node) || ts_node_is_missing(node->node);
}

int64_t prove_prove_count(Prove_Node node) {
    return (int64_t)ts_node_child_count(node->node);
}

Prove_List *prove_prove_named_children(Prove_Node node) {
    uint32_t count = ts_node_named_child_count(node->node);
    Prove_List *list = prove_list_new((int64_t)count);
    for (uint32_t i = 0; i < count; i++) {
        TSNode child = ts_node_named_child(node->node, i);
        prove_list_push(list, prove_node_wrap(node->tree, child));
    }
    return list;
}
