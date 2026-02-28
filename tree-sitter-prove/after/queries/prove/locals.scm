; Scoping for Prove

(function_definition) @local.scope
(main_definition) @local.scope
(lambda_expression) @local.scope
(if_expression) @local.scope
(match_arm) @local.scope

(parameter (identifier) @local.definition)
(variable_declaration (identifier) @local.definition)
(lambda_expression (identifier) @local.definition)

; Function calls are references, not definitions
(call_expression (identifier) @local.reference)
(valid_expression (identifier) @local.reference)

; Other identifiers are references
(identifier) @local.reference
