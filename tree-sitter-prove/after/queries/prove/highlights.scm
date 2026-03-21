; Tree-sitter highlight queries for Prove
; ========================================

; Strings must be captured first to prevent keyword highlighting inside strings
(string_literal) @string

; ─── Verbs (function declaration keywords) ──────────────────

; Only highlight verbs in function definition context
(function_definition (verb) @keyword.function)

"main" @keyword.function

; ─── Core Keywords ──────────────────────────────────────────

[
  "from"
  "type"
  "is"
  "as"
  "where"
  "match"
  "comptime"
  "valid"
  "module"
  "binary"
] @keyword

; ─── Contract Keywords ──────────────────────────────────────

[
  "ensures"
  "requires"
  "explain"
  "terminates"
  "trusted"
  "when"
] @keyword.control

; ─── Explain Lines ─────────────────────────────────────────

(explain_line) @string.documentation

; ─── AI-Resistance Keywords ────────────────────────────────

; These are only keywords in annotation positions
[
  "intent"
  "narrative"
  "why_not"
  "chosen"
  "near_miss"
  "know"
  "assume"
  "believe"
  "temporal"
  "satisfies"
  "invariant_network"
] @keyword.directive

; ─── Types ──────────────────────────────────────────────────

(type_identifier) @type

(type_definition
  (type_identifier) @type.definition)

(type_parameters
  (type_identifier) @type.parameter)

(modified_type
  (type_identifier) @type
  (named_modifier
    (type_identifier) @type.qualifier))

; Built-in types
((type_identifier) @type.builtin
 (#any-of? @type.builtin
  "Integer" "Decimal" "Float" "Boolean" "String" "Byte" "Character"
  "List" "Option" "Result" "Unit" "NonEmpty" "Map"))

; ─── Functions ──────────────────────────────────────────────

(function_definition
  (identifier) @function.definition)

(main_definition
  "main" @function.definition)

(call_expression
  (identifier) @function.call)

(valid_expression
  (identifier) @function.call)

; ─── Variables and Parameters ───────────────────────────────

(parameter
  (identifier) @variable.parameter)

(variable_declaration
  (identifier) @variable)

; Field access
(field_expression
  (identifier) @property)

(field_declaration
  (identifier) @property)

; ─── Constants ──────────────────────────────────────────────

(constant_identifier) @constant

(constant_definition
  (constant_identifier) @constant)

; ─── Literals ───────────────────────────────────────────────

(string_literal) @string

(interpolation
  "{" @punctuation.special
  "}" @punctuation.special)

(escape_sequence) @string.escape

; ─── Regex Internals ──────────────────────────────────────

(raw_string) @string.regex
(regex_escape) @string.escape
(regex_class) @string.special
(regex_quantifier) @operator
(regex_anchor) @operator
(regex_group_open) @punctuation.bracket
(regex_group_close) @punctuation.bracket
(regex_alternation) @operator
(regex_dot) @operator

(integer_literal) @number
(decimal_literal) @number.float

; Only highlight booleans in expression contexts
(expression (boolean_literal) @boolean)

(boolean_literal) @boolean

; ─── Operators ──────────────────────────────────────────────

[
  "+"
  "-"
  "*"
  "/"
  "%"
  "=="
  "!="
  "<"
  ">"
  "<="
  ">="
  "&&"
  "||"
] @operator

"|>" @operator

"=>" @punctuation.delimiter

".." @operator

; ─── Fail marker ────────────────────────────────────────────

(fail_marker) @keyword.exception
(fail_propagation "!" @keyword.exception)

; ─── Punctuation ────────────────────────────────────────────

["(" ")" "[" "]" "<" ">"] @punctuation.bracket

["," "." ":" "|"] @punctuation.delimiter

"=" @operator

; ─── Comments ───────────────────────────────────────────────

(doc_comment) @comment.documentation
(line_comment) @comment

; ─── Near-miss annotations ──────────────────────────────────

(near_miss_annotation
  (expression) @number
  (expression) @boolean)

; ─── Patterns ───────────────────────────────────────────────

(variant_pattern
  (type_identifier) @constructor)

(wildcard_pattern) @variable.builtin

; ─── Algebraic Variants (in type definitions) ───────────────

(algebraic_variant
  (type_identifier) @type)

; ─── Import items ───────────────────────────────────────────

; Only highlight imports that have the 'types' keyword
(import_declaration
  (import_group
    (type_identifier) @module))

(import_group
  (import_verb) @keyword.function)

(import_group
  (identifier) @function)

(import_group
  (type_identifier) @type)

; ─── Variable references (fallback) ───────────────────────────
; Low priority so more specific patterns above win.

((identifier) @variable
 (#set! "priority" 90))
