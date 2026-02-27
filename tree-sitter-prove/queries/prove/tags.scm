; Tags for code navigation (goto definition, symbol search)

(function_definition
  (identifier) @name) @definition.function

(main_definition) @definition.function

(type_definition
  (type_identifier) @name) @definition.type

(constant_definition
  (constant_identifier) @name) @definition.constant

(module_declaration
  (type_identifier) @name) @definition.module
