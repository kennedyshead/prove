/// <reference types="tree-sitter-cli/dsl" />
// Tree-sitter grammar for the Prove programming language

const PREC = {
  PIPE: 1,
  OR: 2,
  AND: 3,
  COMPARE: 4,
  RANGE: 5,
  ADD: 6,
  MULT: 7,
  UNARY: 8,
  POSTFIX: 9,
  CALL: 10,
  FIELD: 11,
};

module.exports = grammar({
  name: 'prove',

  extras: $ => [
    /\s/,
    $.doc_comment,
    $.line_comment,
  ],

  word: $ => $.identifier,

  conflicts: $ => [
    [$.expression, $.pattern],
  ],

  rules: {
    source_file: $ => repeat($._top_level),

    _top_level: $ => choice(
      $.module_declaration,
      $.function_definition,
      $.main_definition,
    ),

    // ─── Comments ──────────────────────────────────────────────

    doc_comment: $ => token(seq('///', /.*/)),

    line_comment: $ => token(prec(-1, seq('//', /[^/\n][^\n]*/))),

    // ─── Module ────────────────────────────────────────────────

    module_declaration: $ => seq(
      'module',
      $.type_identifier,
      repeat(choice(
        $.import_declaration,
        $.type_definition,
        $.constant_definition,
        $.invariant_network,
        $.narrative_annotation,
        $.temporal_annotation,
      )),
    ),

    // ─── Imports ───────────────────────────────────────────────

    import_declaration: $ => seq(
      $.type_identifier,
      sep1($.import_group, ','),
    ),

    import_group: $ => prec.right(seq(
      optional(choice($.verb, 'types')),
      repeat1(choice($.identifier, $.type_identifier)),
    )),

    // ─── Type Definitions ──────────────────────────────────────

    type_definition: $ => seq(
      'type',
      $.type_identifier,
      optional($.type_parameters),
      'is',
      $._type_body,
    ),

    _type_body: $ => choice(
      $.algebraic_type_body,
      $.record_type_body,
      $.refinement_type_body,
    ),

    algebraic_type_body: $ => prec.left(seq(
      $.algebraic_variant,
      repeat(seq('|', $.algebraic_variant)),
    )),

    algebraic_variant: $ => seq(
      $.type_identifier,
      optional($.variant_fields),
    ),

    variant_fields: $ => seq(
      '(',
      sep1($.field_declaration, ','),
      ')',
    ),

    record_type_body: $ => repeat1($.field_declaration),

    field_declaration: $ => seq(
      $.identifier,
      $.type_expression,
    ),

    refinement_type_body: $ => seq(
      $.type_expression,
      'where',
      $.expression,
    ),

    // ─── Type Expressions ──────────────────────────────────────

    type_expression: $ => choice(
      $.modified_type,
      $.generic_type,
      $.simple_type,
    ),

    simple_type: $ => $.type_identifier,

    generic_type: $ => prec(1, seq(
      $.type_identifier,
      '<',
      sep1($.type_expression, ','),
      '>',
    )),

    modified_type: $ => seq(
      $.type_identifier,
      ':',
      '[',
      repeat1($._type_modifier),
      ']',
    ),

    _type_modifier: $ => choice(
      $.named_modifier,
      $.type_identifier,
      $.identifier,
      $.integer_literal,
    ),

    named_modifier: $ => seq(
      $.type_identifier,
      ':',
      choice($.integer_literal, $.identifier),
    ),

    type_parameters: $ => seq(
      '<',
      sep1($.type_identifier, ','),
      '>',
    ),

    // ─── Function Definitions ──────────────────────────────────

    verb: $ => choice(
      'transforms',
      'inputs',
      'outputs',
      'validates',
    ),

    function_definition: $ => seq(
      optional($.doc_comment_block),
      $.verb,
      $.identifier,
      $.parameter_list,
      optional($.type_expression),
      optional($.fail_marker),
      repeat($._annotation),
      'from',
      $._body_content,
    ),

    doc_comment_block: $ => repeat1($.doc_comment),

    main_definition: $ => seq(
      optional($.doc_comment_block),
      'main',
      '(',
      ')',
      optional($.type_expression),
      optional($.fail_marker),
      'from',
      $._body_content,
    ),

    fail_marker: $ => token('!'),

    parameter_list: $ => seq(
      '(',
      optional(sep1($.parameter, ',')),
      ')',
    ),

    parameter: $ => seq(
      $.identifier,
      $.type_expression,
      optional(seq('where', $.expression)),
    ),

    _body_content: $ => repeat1(choice(
      $._statement,
      $.match_arm,
    )),

    // ─── Annotations ───────────────────────────────────────────

    _annotation: $ => choice(
      $.ensures_clause,
      $.requires_clause,
      $.proof_block,
      $.why_not_annotation,
      $.chosen_annotation,
      $.near_miss_annotation,
      $.know_annotation,
      $.assume_annotation,
      $.believe_annotation,
      $.intent_annotation,
      $.satisfies_clause,
    ),

    ensures_clause: $ => seq('ensures', $.expression),

    requires_clause: $ => seq('requires', $.expression),

    proof_block: $ => seq(
      'proof',
      repeat1($.proof_obligation),
    ),

    proof_obligation: $ => seq(
      field('name', $.identifier),
      ':',
      field('text', $.proof_text),
    ),

    // Each proof_text line is a single token (rest of line after `:` or
    // an indented continuation).  Continuations are separate proof_text
    // tokens so the repeat absorbs them.
    proof_text: $ => repeat1(token(prec(-1, /[^\n]*[a-zA-Z0-9\)][^\n]*/))),

    satisfies_clause: $ => seq('satisfies', $.type_identifier),

    // ─── AI-Resistance Annotations ─────────────────────────────

    why_not_annotation: $ => seq('why_not', ':', $.string_literal),
    chosen_annotation: $ => seq('chosen', ':', $.string_literal),

    near_miss_annotation: $ => seq(
      'near_miss', ':',
      field('input', $.expression),
      '=>',
      field('expected', $.expression),
    ),

    know_annotation: $ => seq('know', ':', $.expression),
    assume_annotation: $ => seq('assume', ':', $.expression),
    believe_annotation: $ => seq('believe', ':', $.expression),
    intent_annotation: $ => seq('intent', ':', $.string_literal),

    narrative_annotation: $ => seq('narrative', ':', $.string_literal),

    temporal_annotation: $ => seq(
      'temporal', ':',
      $.identifier,
      repeat(seq('->', $.identifier)),
    ),

    // ─── Invariant Networks ────────────────────────────────────

    invariant_network: $ => prec.left(seq(
      'invariant_network',
      $.type_identifier,
      repeat1($.expression),
    )),

    // ─── Constants ─────────────────────────────────────────────

    constant_definition: $ => seq(
      $.constant_identifier,
      optional(seq('as', $.type_expression)),
      '=',
      choice($.comptime_block, $.expression),
    ),

    comptime_block: $ => prec.left(seq(
      'comptime',
      repeat1($._statement),
    )),

    // ─── Statements ────────────────────────────────────────────

    _statement: $ => choice(
      $.variable_declaration,
      $.assignment,
      $.if_expression,
      $.match_expression,
      $.expression,
    ),

    variable_declaration: $ => prec(1, seq(
      $.identifier,
      'as',
      $.type_expression,
      '=',
      $.expression,
    )),

    assignment: $ => prec(1, seq(
      $.identifier,
      '=',
      $.expression,
    )),

    // ─── Expressions ───────────────────────────────────────────

    expression: $ => choice(
      $.pipe_expression,
      $.binary_expression,
      $.unary_expression,
      $.fail_propagation,
      $.call_expression,
      $.field_expression,
      $.valid_expression,
      $.lambda_expression,
      $.parenthesized_expression,
      $.list_literal,
      $._literal,
      $.identifier,
      $.type_identifier,
    ),

    pipe_expression: $ => prec.left(PREC.PIPE, seq(
      $.expression,
      '|>',
      $.expression,
    )),

    binary_expression: $ => choice(
      prec.left(PREC.OR, seq($.expression, '||', $.expression)),
      prec.left(PREC.AND, seq($.expression, '&&', $.expression)),
      prec.left(PREC.COMPARE, seq($.expression, choice('==', '!=', '<', '>', '<=', '>='), $.expression)),
      prec.left(PREC.RANGE, seq($.expression, '..', $.expression)),
      prec.left(PREC.ADD, seq($.expression, choice('+', '-'), $.expression)),
      prec.left(PREC.MULT, seq($.expression, choice('*', '/', '%'), $.expression)),
    ),

    unary_expression: $ => prec(PREC.UNARY, seq(
      choice('!', '-'),
      $.expression,
    )),

    call_expression: $ => prec(PREC.CALL, seq(
      choice($.identifier, $.type_identifier),
      '(',
      optional(sep1($.expression, ',')),
      ')',
    )),

    field_expression: $ => prec.left(PREC.FIELD, seq(
      $.expression,
      '.',
      $.identifier,
    )),

    fail_propagation: $ => prec.left(PREC.POSTFIX, seq(
      $.expression,
      token.immediate('!'),
    )),

    valid_expression: $ => prec.left(PREC.CALL, seq(
      'valid',
      $.identifier,
      optional(seq('(', optional(sep1($.expression, ',')), ')')),
    )),

    lambda_expression: $ => seq(
      '|',
      optional(sep1($.identifier, ',')),
      '|',
      $.expression,
    ),

    parenthesized_expression: $ => seq('(', $.expression, ')'),

    if_expression: $ => prec.right(seq(
      'if',
      field('condition', $.expression),
      repeat1($._statement),
      optional(seq('else', repeat1($._statement))),
    )),

    match_expression: $ => prec.left(seq(
      'match',
      field('subject', $.expression),
      repeat1($.match_arm),
    )),

    match_arm: $ => seq(
      $.pattern,
      '=>',
      $.expression,
    ),

    // ─── Patterns ──────────────────────────────────────────────

    pattern: $ => choice(
      $.variant_pattern,
      $.wildcard_pattern,
      $._literal,
      $.identifier,
    ),

    variant_pattern: $ => prec(1, seq(
      $.type_identifier,
      optional(seq('(', sep1($.pattern, ','), ')')),
    )),

    wildcard_pattern: $ => '_',

    // ─── Literals ──────────────────────────────────────────────

    _literal: $ => choice(
      $.string_literal,
      $.integer_literal,
      $.decimal_literal,
      $.boolean_literal,
      $.regex_literal,
    ),

    // Regex literals: /pattern/ (deprecated — prefer r"pattern")
    regex_literal: $ => token(seq('/', /[^\s\/]([^\/\n\\]|\\.)*/, '/')),

    string_literal: $ => choice(
      $._simple_string,
      $._triple_string,
      $.format_string,
      $.raw_string,
    ),

    // Plain string — no interpolation, { is literal
    _simple_string: $ => seq(
      '"',
      repeat(choice(
        $.escape_sequence,
        token.immediate(prec(1, /[^"\\]+/)),
      )),
      '"',
    ),

    // f-string — explicit interpolation with {expr}
    format_string: $ => seq(
      'f"',
      repeat(choice(
        $.escape_sequence,
        $.interpolation,
        token.immediate(prec(1, /[^"\\{]+/)),
      )),
      '"',
    ),

    // r-string — raw string, no escapes, no interpolation
    raw_string: $ => seq(
      'r"',
      token.immediate(/[^"]*/),
      '"',
    ),

    _triple_string: $ => seq(
      '"""',
      repeat(choice(
        /[^"]+/,
        /"[^"]/,
        /""[^"]/,
      )),
      '"""',
    ),

    interpolation: $ => seq(
      '{',
      $.expression,
      '}',
    ),

    escape_sequence: $ => token.immediate(seq('\\', choice('n', 'r', 't', '\\', '"', '{', '}', '0'))),

    integer_literal: $ => token(choice(
      /[0-9][0-9_]*/,
      /0x[0-9a-fA-F][0-9a-fA-F_]*/,
      /0b[01][01_]*/,
      /0o[0-7][0-7_]*/,
    )),

    decimal_literal: $ => token(/[0-9][0-9_]*\.[0-9][0-9_]*/),

    boolean_literal: $ => choice('true', 'false'),

    list_literal: $ => seq(
      '[',
      optional(sep1($.expression, ',')),
      ']',
    ),

    // ─── Identifiers ──────────────────────────────────────────

    identifier: $ => /[a-z_][a-z0-9_]*/,

    type_identifier: $ => /[A-Z][a-zA-Z0-9]*/,

    constant_identifier: $ => /[A-Z][A-Z0-9_]+/,
  },
});

function sep1(rule, separator) {
  return seq(rule, repeat(seq(separator, rule)));
}
