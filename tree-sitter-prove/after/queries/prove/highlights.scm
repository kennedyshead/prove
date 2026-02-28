; Tree-sitter highlight queries for Prove
; ========================================

; ─── Verbs (function declaration keywords) ──────────────────

[
  "transforms"
  "inputs"
  "outputs"
  "validates"
] @keyword.function

"main" @keyword.function

; ─── Core Keywords ──────────────────────────────────────────

[
  "from"
  "type"
  "is"
  "as"
  "where"
  "match"
  "if"
  "else"
  "comptime"
  "valid"
  "module"
] @keyword

; ─── Contract Keywords ──────────────────────────────────────

[
  "ensures"
  "requires"
  "proof"
] @keyword.control

; ─── AI-Resistance Keywords ────────────────────────────────

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

(integer_literal) @number
(decimal_literal) @number.float

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

; ─── Proof Obligations ──────────────────────────────────────

(proof_obligation
  (identifier) @label
  (proof_text) @string.documentation)

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
  (type_identifier) @constructor)

; ─── Import items ───────────────────────────────────────────

(import_declaration
  (type_identifier) @module)

(import_group
  (identifier) @function)

; ─── Variable references (fallback) ───────────────────────────
; Must be last — more specific patterns above take precedence.

; Binary expressions, unary expressions, etc. contain identifier operands
(binary_expression (identifier) @variable)
(unary_expression (identifier) @variable)
(match_arm (identifier) @variable)
