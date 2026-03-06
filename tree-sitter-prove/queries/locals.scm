; Scoping for Prove

(function_definition) @local.scope
(main_definition) @local.scope
(lambda_expression) @local.scope
(match_arm) @local.scope

; Function definitions are definitions, not references
(function_definition (identifier) @local.definition)
(main_definition "main" @local.definition)

; Parameters and variable declarations are definitions
(parameter (identifier) @local.definition)
(variable_declaration (identifier) @local.definition)
(lambda_expression (identifier) @local.definition)

; Function calls are references, not definitions
(call_expression (identifier) @local.reference)
(valid_expression (identifier) @local.reference)

; Other identifiers are references
(identifier) @local.reference
