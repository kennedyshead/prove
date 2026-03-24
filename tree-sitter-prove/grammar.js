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

  externals: $ => [
    $._newline,
  ],

  extras: $ => [
    /\s/,
    $.doc_comment,
    $.line_comment,
  ],

  conflicts: $ => [
    [$.expression, $.pattern],
    [$.algebraic_variant, $.simple_type],
    [$.refinement_type_body, $.lookup_type_body, $._lookup_column],
    [$.lookup_type_body, $.runtime_lookup_type_body],
    [$.import_verb, $.async_verb],
    [$.import_verb, $.function_definition],
    [$.intent_verb_phrase],
  ],

  rules: {
    source_file: $ => choice(
      $.intent_file,
      repeat($._top_level),
    ),

    _top_level: $ => choice(
      $.module_declaration,
      $.function_definition,
      $.main_definition,
    ),

    // ─── .intent file ─────────────────────────────────────────────

    intent_file: $ => seq(
      $.intent_project,
      repeat(choice(
        $.intent_vocabulary,
        $.intent_module,
        $.intent_flow,
        $.intent_constraints,
      )),
    ),

    intent_project: $ => seq(
      'project',
      $.type_identifier,
      optional(seq('purpose', ':', /[^\n]+/)),
      optional(seq('domain', ':', /[^\n]+/)),
    ),

    intent_vocabulary: $ => seq(
      'vocabulary',
      repeat1($.intent_vocab_entry),
    ),

    intent_vocab_entry: $ => seq(
      $.type_identifier,
      'is',
      /[^\n]+/,
    ),

    intent_module: $ => seq(
      'module',
      $.type_identifier,
      repeat1($.intent_verb_phrase),
    ),

    intent_verb_phrase: $ => seq(
      $.intent_verb,
      repeat1(choice($.identifier, $.type_identifier)),
    ),

    intent_verb: $ => choice(
      'validates', 'transforms', 'reads', 'creates', 'matches',
      'inputs', 'outputs', 'streams', 'listens', 'detached', 'attached', 'renders',
    ),

    intent_flow: $ => seq(
      'flow',
      repeat1($.intent_flow_step),
    ),

    intent_flow_step: $ => seq(
      $.type_identifier,
      $.intent_verb_phrase,
      optional(seq('->', $.intent_flow_step)),
    ),

    intent_constraints: $ => seq(
      'constraints',
      repeat1(/[^\n]+/),
    ),

    // ─── Comments ──────────────────────────────────────────────

    doc_comment: $ => token(seq('///', /.*/)),

    line_comment: $ => token(prec(-1, seq('//', /[^/\n][^\n]*/))),

    // ─── Module ────────────────────────────────────────────────

    module_declaration: $ => prec.right(seq(
      'module',
      $.type_identifier,
      repeat(choice(
        $.type_definition,
        prec(-1, $.import_declaration),
        prec(-2, $.import_group),
        $.constant_definition,
        $.invariant_network,
        $.narrative_annotation,
        $.domain_annotation,
        $.temporal_annotation,
        $.foreign_block,
        $.function_definition,
        $.main_definition,
      )),
    )),

    // ─── Imports ───────────────────────────────────────────────

    import_declaration: $ => seq(
      $.type_identifier,
      $.import_group,
    ),

    import_group: $ => choice(
      prec.right(seq(alias('types', $.import_verb), repeat1($.type_identifier), optional(prec.dynamic(10, $._newline)))),
      prec.right(seq(alias('constants', $.import_verb), repeat1($.constant_identifier), optional(prec.dynamic(10, $._newline)))),
      prec.right(seq($.import_verb, $.identifier, repeat($.identifier))),
      prec.right(-1, seq($.identifier, repeat($.identifier))),
    ),

    import_verb: $ => choice(
      $.verb,
      'detached',
      'attached',
      'listens',
      'streams',
      'renders',
    ),

    // ─── Type Definitions ──────────────────────────────────────

    type_definition: $ => seq(
      optional($.doc_comment_block),
      'type',
      $.type_identifier,
      optional(seq(':', $.type_modifier_bracket)),
      optional($.type_parameters),
      'is',
      $._type_body,
    ),

    type_modifier_bracket: $ => seq(
      '[',
      repeat1($.type_identifier),
      ']',
    ),

    _type_body: $ => choice(
      $.algebraic_type_body,
      $.record_type_body,
      $.refinement_type_body,
      $.binary_type_body,
      $.lookup_type_body,
      $.named_lookup_type_body,
      $.runtime_lookup_type_body,
      $.dispatch_lookup_type_body,
    ),

    binary_type_body: $ => 'binary',

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

    record_type_body: $ => prec.right(repeat1($.field_declaration)),

    field_declaration: $ => prec(10, seq(
      $.identifier,
      $.type_expression,
    )),

    refinement_type_body: $ => seq(
      $.type_expression,
      'where',
      $.expression,
    ),

    lookup_type_body: $ => prec.dynamic(2, prec.right(seq(
      $.type_expression,
      repeat(seq(optional('|'), $.type_expression)),
      'where',
      repeat1($.lookup_variant),
    ))),

    named_lookup_type_body: $ => prec.right(seq(
      $._lookup_column,
      repeat(seq('|', $._lookup_column)),
      'where',
      repeat1($.lookup_variant),
    )),

    lookup_variant: $ => prec.left(seq(
      $.type_identifier,
      '|',
      $._lookup_value,
      repeat(seq('|', $._lookup_value)),
    )),

    runtime_lookup_type_body: $ => prec(1, seq(
      $.type_expression,
      repeat(seq('|', $.type_expression)),
      'runtime',
    )),

    dispatch_lookup_type_body: $ => prec.right(2, seq(
      $._lookup_column,
      repeat1(seq('|', $._lookup_column)),
      repeat1($.dispatch_lookup_variant),
    )),

    dispatch_lookup_variant: $ => seq(
      $.string_literal,
      '|',
      $.identifier,
    ),

    _lookup_column: $ => choice(
      $.named_lookup_column,
      $.type_expression,
    ),

    named_lookup_column: $ => seq(
      $.identifier,
      ':',
      $.type_expression,
    ),

    _lookup_value: $ => choice(
      $.string_literal,
      $.integer_literal,
      $.decimal_literal,
      $.boolean_literal,
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
      optional(seq('<', sep1($.type_expression, ','), '>')),
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

    type_parameters: $ => choice(
      seq('<', sep1($.type_identifier, ','), '>'),
      seq('[', sep1($.type_identifier, ','), ']'),
    ),

    // ─── Function Definitions ──────────────────────────────────

    verb: $ => choice(
      'creates',
      'inputs',
      'matches',
      'outputs',
      'reads',
      'transforms',
      'validates',
    ),

    async_verb: $ => choice(
      'attached',
      'detached',
      'listens',
      'renders',
      'streams',
    ),

    function_definition: $ => prec.right(seq(
      optional($.doc_comment_block),
      choice($.verb, $.async_verb),
      $.identifier,
      $.parameter_list,
      optional($.type_expression),
      optional($.fail_marker),
      repeat($._annotation),
      choice(
        seq('from', $._body_content),
        'binary',
      ),
    )),

    doc_comment_block: $ => repeat1($.doc_comment),

    main_definition: $ => prec.right(seq(
      optional($.doc_comment_block),
      'main',
      '(',
      ')',
      optional($.type_expression),
      optional($.fail_marker),
      'from',
      $._body_content,
    )),

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
      $.explain_annotation,
      $.terminates_annotation,
      $.trusted_annotation,
      $.why_not_annotation,
      $.chosen_annotation,
      $.near_miss_annotation,
      $.know_annotation,
      $.assume_annotation,
      $.believe_annotation,
      $.intent_annotation,
      $.satisfies_clause,
      $.when_annotation,
      $.event_type_annotation,
      $.state_init_annotation,
      $.state_type_annotation,
    ),

    ensures_clause: $ => seq('ensures', $.expression),

    requires_clause: $ => seq('requires', $.expression),

    when_annotation: $ => seq('when', $.expression),

    satisfies_clause: $ => seq('satisfies', $.type_identifier),

    event_type_annotation: $ => seq('event_type', $.type_expression),
    state_init_annotation: $ => seq('state_init', $.expression),
    state_type_annotation: $ => seq('state_type', $.type_expression),

    explain_annotation: $ => seq('explain', repeat1($.explain_line)),

    explain_line: $ => token(prec(-1, /[a-z][^\n]*/)),

    terminates_annotation: $ => seq('terminates', ':', $.expression),

    trusted_annotation: $ => seq('trusted', ':', $.string_literal),

    // ─── AI-Resistance Annotations ─────────────────────────────

    why_not_annotation: $ => seq('why_not', ':', $.string_literal),
    chosen_annotation: $ => seq('chosen', ':', $.string_literal),

    near_miss_annotation: $ => seq(
      'near_miss', optional(':'),
      field('input', $.expression),
      '=>',
      field('expected', $.expression),
    ),

    know_annotation: $ => seq('know', ':', $.expression),
    assume_annotation: $ => seq('assume', ':', $.expression),
    believe_annotation: $ => seq('believe', ':', $.expression),
    intent_annotation: $ => seq('intent', ':', $.string_literal),

    narrative_annotation: $ => seq('narrative', ':', $.string_literal),

    domain_annotation: $ => seq(
      'domain', optional(':'),
      choice($.type_identifier, $.string_literal),
    ),

    temporal_annotation: $ => seq(
      'temporal', optional(':'),
      choice(
        $.string_literal,
        seq($.identifier, repeat(seq('->', $.identifier))),
      ),
    ),

    foreign_block: $ => prec.right(seq(
      'foreign',
      $.string_literal,
      repeat($.foreign_function),
    )),

    foreign_function: $ => prec.right(seq(
      $.identifier,
      $.parameter_list,
      $.type_expression,
    )),

    // ─── Invariant Networks ────────────────────────────────────

    invariant_network: $ => prec.left(seq(
      'invariant_network',
      $.type_identifier,
      repeat1($.expression),
    )),

    // ─── Constants ─────────────────────────────────────────────

    constant_definition: $ => choice(
      seq(
        $.constant_identifier,
        optional(seq('as', $.type_expression)),
        '=',
        choice($.comptime_block, $.expression),
      ),
      // Short all-caps constants like PI that match type_identifier
      prec(1, seq(
        $.type_identifier,
        'as',
        $.type_expression,
        '=',
        choice($.comptime_block, $.expression),
      )),
    ),

    comptime_block: $ => prec.left(seq(
      'comptime',
      $._body_content,
    )),

    // ─── Statements ────────────────────────────────────────────

    _statement: $ => choice(
      $.variable_declaration,
      $.assignment,
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
      choice($.identifier, $.field_expression),
      '=',
      $.expression,
    )),

    // ─── Expressions ───────────────────────────────────────────

    expression: $ => choice(
      $.pipe_expression,
      $.binary_expression,
      $.unary_expression,
      $.fail_propagation,
      $.async_marker,
      $.call_expression,
      $.lookup_access_expression,
      $.field_expression,
      $.valid_expression,
      $.lambda_expression,
      $.parenthesized_expression,
      $.list_literal,
      $._literal,
      $.identifier,
      $.type_identifier,
      $.constant_identifier,
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
      choice($.identifier, $.type_identifier, $.field_expression),
      '(',
      optional(sep1($.expression, ',')),
      ')',
    )),

    lookup_access_expression: $ => prec(PREC.CALL, seq(
      choice($.type_identifier, $.identifier),
      token.immediate(':'),
      choice(
        $.string_literal,
        $.type_identifier,
        $.identifier,
        $.integer_literal,
      ),
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

    async_marker: $ => prec.left(PREC.POSTFIX, seq(
      $.expression,
      token.immediate('&'),
    )),

    valid_expression: $ => prec.right(PREC.CALL, seq(
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

    match_expression: $ => prec.left(seq(
      'match',
      field('subject', $.expression),
      repeat1($.match_arm),
    )),

    match_arm: $ => prec.left(seq(
      $.pattern,
      '=>',
      repeat1($._statement),
    )),

    // ─── Patterns ──────────────────────────────────────────────

    pattern: $ => choice(
      $.lookup_pattern,
      $.variant_pattern,
      $.wildcard_pattern,
      $._literal,
      $.identifier,
    ),

    variant_pattern: $ => prec(1, seq(
      $.type_identifier,
      optional(seq('(', sep1($.pattern, ','), ')')),
    )),

    lookup_pattern: $ => prec(2, seq(
      $.type_identifier,
      token.immediate(':'),
      choice(
        $.string_literal,
        $.type_identifier,
        $.identifier,
        $.integer_literal,
      ),
    )),

    wildcard_pattern: $ => '_',

    // ─── Literals ──────────────────────────────────────────────

    _literal: $ => choice(
      $.string_literal,
      $.character_literal,
      $.integer_literal,
      $.decimal_literal,
      $.boolean_literal,
      $.regex_literal,
    ),

    character_literal: $ => seq(
      "'",
      choice(
        $.escape_sequence,
        token.immediate(prec(1, /[^'\\]/)),
      ),
      token.immediate("'"),
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

    // r-string — regex string with internal highlighting
    raw_string: $ => seq(
      'r"',
      repeat(choice(
        $.regex_escape,
        $.regex_class,
        $.regex_quantifier,
        $.regex_group_open,
        $.regex_group_close,
        $.regex_anchor,
        $.regex_alternation,
        $.regex_dot,
        token.immediate(prec(-1, /[^"\\.|()\[\]{}+*?^$]+/)),
      )),
      '"',
    ),

    regex_escape: $ => token.immediate(/\\[dDwWsStrnbBfv0\\.|(){}\[\]+*?^$/]/),

    regex_class: $ => token.immediate(/\[\^?\]?([^\]\\]|\\.|\[:\w+:\])*\]/),

    regex_quantifier: $ => token.immediate(choice(
      /[+*?]/,
      /\{[0-9]+(?:,[0-9]*)?\}/,
    )),

    regex_group_open: $ => token.immediate(choice(
      '(',
      /\(\?[=!:]/,
    )),

    regex_group_close: $ => token.immediate(')'),

    regex_anchor: $ => token.immediate(/[\^$]/),

    regex_alternation: $ => token.immediate('|'),

    regex_dot: $ => token.immediate('.'),

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

    decimal_literal: $ => token(/[0-9][0-9_]*\.[0-9][0-9_]*[fF]?/),

    boolean_literal: $ => choice('true', 'false'),

    list_literal: $ => seq(
      '[',
      optional(sep1($.expression, ',')),
      ']',
    ),

    // ─── Identifiers ──────────────────────────────────────────

    identifier: $ => /[a-z_][a-z0-9_]*/,

    type_identifier: $ => /[A-Z][a-zA-Z0-9]*/,

    constant_identifier: $ => token(prec(1, /[A-Z]([A-Z0-9]*_[A-Z0-9_]*|[A-Z][A-Z][A-Z0-9_]*)/)),
  },
});

function sep1(rule, separator) {
  return seq(rule, repeat(seq(separator, rule)));
}
