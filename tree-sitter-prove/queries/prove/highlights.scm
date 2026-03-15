; Tree-sitter highlight queries for Prove
; ========================================

; Strings must be captured first to prevent keyword highlighting inside strings
(string_literal) @string

; ─── Verbs (function declaration keywords) ──────────────────

; Only highlight verbs in function definition context
(function_definition (verb) @keyword.function)

; PROVE-EXPORT-BEGIN: verbs
[
  "creates"
  "inputs"
  "matches"
  "outputs"
  "reads"
  "transforms"
  "validates"
  "types"
] @keyword.function
; PROVE-EXPORT-END: verbs

"main" @keyword.function

; ─── Core Keywords ──────────────────────────────────────────

; PROVE-EXPORT-BEGIN: keywords
[
  "as"
  "binary"
  "comptime"
  "domain"
  "foreign"
  "from"
  "is"
  "match"
  "module"
  "type"
  "valid"
  "where"
] @keyword
; PROVE-EXPORT-END: keywords

; ─── Contract Keywords ──────────────────────────────────────

; PROVE-EXPORT-BEGIN: contract-keywords
[
  "ensures"
  "explain"
  "requires"
  "terminates"
  "when"
] @keyword.control
; PROVE-EXPORT-END: contract-keywords

; ─── Explain Lines ─────────────────────────────────────────

(explain_line) @string.documentation

; ─── AI-Resistance Keywords ────────────────────────────────

; PROVE-EXPORT-BEGIN: ai-keywords
[
  "assume"
  "believe"
  "chosen"
  "intent"
  "invariant_network"
  "know"
  "narrative"
  "near_miss"
  "satisfies"
  "temporal"
  "why_not"
] @keyword.directive
; PROVE-EXPORT-END: ai-keywords

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

; PROVE-EXPORT-BEGIN: builtin-types
; Built-in types
((type_identifier) @type.builtin
 (#any-of? @type.builtin
  "Attached" "Boolean" "Byte" "Character" "Decimal" "Error" "Float" "Integer" "List" "Option" "Result" "Source" "String" "Table" "Unit" "Value" "Verb"))
; PROVE-EXPORT-END: builtin-types

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

(character_literal) @character

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

; ─── Module annotations ────────────────────────────────────

(domain_annotation
  (type_identifier) @type
  (#set! "priority" 101))

(temporal_annotation
  "->" @punctuation.delimiter
  (#set! "priority" 101))

(temporal_annotation
  (identifier) @variable
  (#set! "priority" 101))

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

; Module name in imports
(import_declaration
  (type_identifier) @module)

; Verb in import groups
(import_group
  (verb) @keyword.function
  (#set! "priority" 101))

; Function names in import groups
(import_group
  (identifier) @function
  (#set! "priority" 101))

; Type names in import groups (from 'types' keyword)
(import_group
  (type_identifier) @type
  (#set! "priority" 101))

; ─── Variable references (fallback) ───────────────────────────
; Low priority so more specific patterns above win.

((identifier) @variable
 (#set! "priority" 90))
