/*
 * External scanner for Prove tree-sitter grammar.
 *
 * Provides a _newline token that matches when a newline (or EOF) appears
 * in the upcoming whitespace.  Used to terminate import groups so that
 * `repeat1($.type_identifier)` in a `types` import does not greedily
 * consume identifiers on the next line.
 */

#include "tree_sitter/parser.h"

enum TokenType {
    NEWLINE,
};

void *tree_sitter_prove_external_scanner_create(void) {
    return NULL;
}

void tree_sitter_prove_external_scanner_destroy(void *payload) {
    (void)payload;
}

unsigned tree_sitter_prove_external_scanner_serialize(void *payload, char *buffer) {
    (void)payload;
    (void)buffer;
    return 0;
}

void tree_sitter_prove_external_scanner_deserialize(
    void *payload,
    const char *buffer,
    unsigned length
) {
    (void)payload;
    (void)buffer;
    (void)length;
}

bool tree_sitter_prove_external_scanner_scan(
    void *payload,
    TSLexer *lexer,
    const bool *valid_symbols
) {
    (void)payload;

    if (!valid_symbols[NEWLINE]) {
        return false;
    }

    /* Skip horizontal whitespace only (spaces and tabs). */
    while (lexer->lookahead == ' ' || lexer->lookahead == '\t') {
        lexer->advance(lexer, true);
    }

    /* Match if the next character is a newline or we reached EOF. */
    if (lexer->lookahead == '\n' || lexer->lookahead == '\r' || lexer->eof(lexer)) {
        lexer->result_symbol = NEWLINE;
        return true;
    }

    return false;
}
