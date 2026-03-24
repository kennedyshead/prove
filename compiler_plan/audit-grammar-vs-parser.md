# Audit: grammar.js vs parser.py

**Date:** 2026-03-24
**Tool:** `scripts/audit_grammar.py`

## Summary

| Metric | Count |
|--------|-------|
| Total .prv files audited | 109 |
| Both parsers OK | 107 |
| Tree-sitter FAIL, Python OK | 2 |
| Python FAIL, tree-sitter OK | 0 |
| Both FAIL | 0 |

**Result: 98.2% compatibility.** The 2 failing files are the same `graphic.prv`
in two locations (`proof/src/stdlib/` and `prove-py/src/prove/stdlib/`).

## Grammar Fixes Applied

### 1. Doc comments before type definitions

**Problem:** `type_definition` lacked `optional($.doc_comment_block)`, so
tree-sitter greedily matched doc comments into `function_definition` then
failed on the `type` keyword.

**Fix:** Added `optional($.doc_comment_block)` as the first element of
`type_definition` in grammar.js. No conflict entry needed — tree-sitter
resolves the ambiguity via the `type` keyword vs verb lookahead.

**Impact:** Fixed `ui.prv`, `terminal.prv` (both locations), and all other
files with doc-commented type definitions.

### 2. `constant_identifier` matching variant names like `F10`

**Problem:** The regex `/[A-Z]([A-Z0-9]*_[A-Z0-9_]*|[A-Z0-9][A-Z0-9][A-Z0-9_]*)/`
matched `F10`, `F11`, `F12` as constant identifiers (3+ chars, starts uppercase,
all uppercase/digits). These are variant names in the `Key` lookup type.

**Fix:** Changed the second alternative from `[A-Z0-9][A-Z0-9][A-Z0-9_]*` to
`[A-Z][A-Z][A-Z0-9_]*`, requiring at least **two uppercase letters** before
digits. This correctly matches `HTTP`, `SHA`, `BLAKE3`, `JSON` but not `F10`.

**Impact:** Fixed `ui.prv` Key lookup type variants.

## Remaining Gap

### graphic.prv: Algebraic variant without `|` separator

**File:** `proof/src/stdlib/graphic.prv` (and `prove-py/src/prove/stdlib/graphic.prv`)

**Pattern:**
```prove
type GraphicAppEvent is AppEvent
    Visible(state Value)
    | Hidden(state Value)
    | Focused(state Value)
```

**Problem:** `Visible(state Value)` follows `AppEvent` on a new line without
a `|` separator. The Python parser accepts this (treating `AppEvent` as first
variant, `Visible` as second), but tree-sitter's `algebraic_type_body` rule
requires `|` between all variants after the first.

**Root cause:** LR parsers cannot determine whether an identifier on a new line
is a continuation variant or a new declaration without a delimiter. The `|` is
necessary for unambiguous parsing.

**Fix required:** Add `|` before `Visible` in graphic.prv:
```prove
type GraphicAppEvent is AppEvent
    | Visible(state Value)
    | Hidden(state Value)
    | Focused(state Value)
```

This is the only file in the corpus using this pattern. All other algebraic
types either use `|` between all variants or define variants inline.

## Skipped Files

The following directories/files were excluded from the audit:

- `prove-py/src/prove/data/` — Auto-generated LSP ML data files (not standard Prove source)
- `tree-sitter-prove/test.prv` — Scratch file with experimental syntax

## Parser Method → Grammar Rule Mapping

All 53 `_parse_*` methods in parser.py map to grammar.js rules:

| Parser Method | Grammar Rule(s) | Status |
|---|---|---|
| `_parse_assignment` | `assignment` | OK |
| `_parse_binary_csv_path` | `runtime_lookup_type_body` | OK |
| `_parse_binary_entry_row` | `lookup_variant` | OK |
| `_parse_binary_lookup_def` | `named_lookup_type_body` | OK |
| `_parse_binary_lookup_entries` | `named_lookup_type_body` | OK |
| `_parse_body` | `_body_content` | OK |
| `_parse_call_expr` | `call_expression` | OK |
| `_parse_comptime_expr` | `comptime_block` | OK |
| `_parse_constant_def` | `constant_definition` | OK |
| `_parse_declaration` | `_top_level` | OK |
| `_parse_explain_block` | `explain_annotation` | OK |
| `_parse_explain_entry` | `explain_line` | OK |
| `_parse_expression` | `expression`, `binary_expression`, `unary_expression` | OK |
| `_parse_field_def` | `field_declaration` | OK |
| `_parse_foreign_block` | `foreign_block` | OK |
| `_parse_foreign_function` | `foreign_function` | OK |
| `_parse_function_def` | `function_definition` | OK |
| `_parse_implicit_match_arms` | `match_expression`, `match_arm` | OK |
| `_parse_import` | `import_declaration` | OK |
| `_parse_import_group` | `import_group` | OK |
| `_parse_indented_type_body` | `_type_body`, `algebraic_type_body` | OK |
| `_parse_inline_type_body` | `_type_body` | OK |
| `_parse_invariant_network` | `invariant_network` | OK |
| `_parse_lambda` | `lambda_expression` | OK |
| `_parse_list_literal` | `list_literal` | OK |
| `_parse_lookup_access_expr` | `lookup_access_expression` | OK |
| `_parse_lookup_entry` | `lookup_variant` | OK |
| `_parse_lookup_type_body` | `lookup_type_body` | OK |
| `_parse_lookup_value` | `_lookup_value` | OK |
| `_parse_main_def` | `main_definition` | OK |
| `_parse_match_arm` | `match_arm` | OK |
| `_parse_match_expr` | `match_expression` | OK |
| `_parse_module_decl` | `module_declaration` | OK |
| `_parse_multiline_algebraic` | `algebraic_type_body` | OK |
| `_parse_named_explain_entry` | `explain_line` | OK |
| `_parse_param` | `parameter` | OK |
| `_parse_param_list` | `parameter_list` | OK |
| `_parse_pattern` | `pattern` | OK |
| `_parse_pipe_lookup_entries` | `dispatch_lookup_type_body` | OK |
| `_parse_prefix` | `unary_expression` | OK |
| `_parse_refinement_constraint` | `refinement_type_body` | OK |
| `_parse_statement` | `_statement` | OK |
| `_parse_store_lookup_expr` | `lookup_access_expression` | OK |
| `_parse_string_or_interp` | `string_literal`, `format_string` | OK |
| `_parse_todo_stmt` | (internal — no grammar equivalent) | OK |
| `_parse_type_body` | `_type_body` | OK |
| `_parse_type_def` | `type_definition` | OK |
| `_parse_type_expr` | `type_expression` | OK |
| `_parse_type_modifier` | `type_modifier_bracket`, `_type_modifier` | OK |
| `_parse_valid_expr` | `valid_expression` | OK |
| `_parse_var_decl` | `variable_declaration` | OK |
| `_parse_variant` | `algebraic_variant` | OK |
| `_parse_variant_pattern` | `variant_pattern` | OK |

### Grammar rules with no parser method mapping

These grammar.js rules are sub-rules, terminals, or intent-file rules that
don't correspond to a dedicated `_parse_*` method (they are parsed inline by
parent methods or the Pratt expression parser):

**Annotations (13):** `assume_annotation`, `believe_annotation`,
`chosen_annotation`, `domain_annotation`, `ensures_clause`, `event_type_annotation`,
`intent_annotation`, `know_annotation`, `narrative_annotation`,
`near_miss_annotation`, `requires_clause`, `satisfies_clause`,
`state_init_annotation`, `state_type_annotation`, `temporal_annotation`,
`terminates_annotation`, `trusted_annotation`, `when_annotation`,
`why_not_annotation`

**Terminals/tokens (16):** `boolean_literal`, `character_literal`,
`constant_identifier`, `decimal_literal`, `doc_comment`, `doc_comment_block`,
`escape_sequence`, `identifier`, `integer_literal`, `regex_*` (6 rules),
`type_identifier`, `verb`

**Expression sub-rules (8):** `async_marker`, `fail_marker`, `fail_propagation`,
`field_expression`, `parenthesized_expression`, `pipe_expression`,
`interpolation`, `raw_string`

**Type sub-rules (8):** `binary_type_body`, `generic_type`, `modified_type`,
`named_lookup_column`, `named_modifier`, `record_type_body`, `simple_type`,
`type_parameters`, `variant_fields`

**Intent file rules (9):** `intent_file`, `intent_project`, `intent_vocabulary`,
`intent_vocab_entry`, `intent_module`, `intent_verb_phrase`, `intent_verb`,
`intent_flow`, `intent_flow_step`, `intent_constraints`

**Other (5):** `dispatch_lookup_variant`, `import_verb`, `line_comment`,
`lookup_pattern`, `wildcard_pattern`, `source_file`

**Infrastructure (3):** `conflicts`, `externals`, `extras`
