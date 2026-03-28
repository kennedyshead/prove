"""Convert tree-sitter CST to Prove AST.

Maps every tree-sitter node type to the corresponding ast_nodes.py class.
The checker, emitter, and optimizer see no difference — they consume the
same 52 AST node types regardless of whether the Python parser or tree-sitter
produced them.
"""

from __future__ import annotations

from typing import Any

from tree_sitter import Node as TSNode
from tree_sitter import Tree as TSTree

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    AsyncCallExpr,
    BinaryDef,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    CommentStmt,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    Declaration,
    ExplainBlock,
    ExplainEntry,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FieldDef,
    FieldExpr,
    FloatLit,
    ForeignBlock,
    ForeignFunction,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    ImportDecl,
    ImportItem,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupEntry,
    LookupPattern,
    LookupTypeDef,
    MainDef,
    MatchArm,
    MatchExpr,
    ModifiedType,
    Module,
    ModuleDecl,
    NearMiss,
    Param,
    Pattern,
    PipeExpr,
    RawStringLit,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    Stmt,
    StringInterp,
    StringLit,
    TodoStmt,
    TripleStringLit,
    TypeBody,
    TypeDef,
    TypeExpr,
    TypeIdentifierExpr,
    TypeModifier,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    Variant,
    VariantPattern,
    WildcardPattern,
    WithConstraint,
)
from prove.source import Span


class CSTConverter:
    """Convert a tree-sitter CST to Prove AST nodes."""

    def __init__(self, source: str, tree: TSTree, filename: str = "") -> None:
        self.source = source
        self.tree = tree
        self.filename = filename

    # ── Helpers ───────────────────────────────────────────────────

    def _span(self, node: TSNode) -> Span:
        """Convert tree-sitter node position to Span (1-based lines and columns)."""
        sr, sc = node.start_point
        er, ec = node.end_point
        return Span(self.filename, sr + 1, sc + 1, er + 1, ec + 1)

    def _text(self, node: TSNode) -> str:
        """Get the UTF-8 text of a node."""
        return node.text.decode("utf-8") if node.text else ""

    def _named_children(self, node: TSNode) -> list[TSNode]:
        """Get all named children of a node."""
        return [c for c in node.children if c.is_named]

    def _children_of_type(self, node: TSNode, *types: str) -> list[TSNode]:
        """Get named children matching any of the given types."""
        return [c for c in node.children if c.is_named and c.type in types]

    def _child(self, node: TSNode, typ: str) -> TSNode | None:
        """Get the first named child of the given type, or None."""
        for c in node.children:
            if c.is_named and c.type == typ:
                return c
        return None

    def _child_text(self, node: TSNode, typ: str) -> str | None:
        """Get text of first named child of given type."""
        c = self._child(node, typ)
        return self._text(c) if c else None

    def _has_child(self, node: TSNode, typ: str) -> bool:
        return any(c.is_named and c.type == typ for c in node.children)

    def _has_token(self, node: TSNode, text: str) -> bool:
        """Check if node has an anonymous child with the given text."""
        return any(not c.is_named and self._text(c) == text for c in node.children)

    # ── Root conversion ──────────────────────────────────────────

    def convert(self) -> Module:
        """Convert root node to Module AST.

        The old Python parser puts ModuleDecl and its body functions as
        separate sibling declarations in the Module. Tree-sitter nests
        functions inside module_declaration. We flatten: ModuleDecl gets
        an empty body, and its functions become top-level declarations.
        """
        root = self.tree.root_node
        declarations: list[Declaration] = []

        for child in self._named_children(root):
            if child.type == "module_declaration":
                mod_decl = self._convert_module_decl(child)
                # Flatten: move body functions to top-level declarations
                body_funcs = list(mod_decl.body)
                flattened = ModuleDecl(
                    name=mod_decl.name,
                    narrative=mod_decl.narrative,
                    domain=mod_decl.domain,
                    temporal=mod_decl.temporal,
                    imports=mod_decl.imports,
                    types=mod_decl.types,
                    constants=mod_decl.constants,
                    invariants=mod_decl.invariants,
                    foreign_blocks=mod_decl.foreign_blocks,
                    body=[],
                    span=mod_decl.span,
                )
                declarations.append(flattened)
                declarations.extend(body_funcs)
            elif child.type == "function_definition":
                declarations.append(self._convert_function_def(child))
            elif child.type == "main_definition":
                declarations.append(self._convert_main_def(child))
            elif child.type == "intent_file":
                pass  # Intent files handled separately

        return Module(declarations, self._span(root))

    # ── Module declaration ───────────────────────────────────────

    def _convert_module_decl(self, node: TSNode) -> ModuleDecl:
        name = self._child_text(node, "type_identifier") or ""

        narrative: str | None = None
        domain: str | None = None
        temporal: list[str] | None = None
        imports: list[ImportDecl] = []
        types: list[TypeDef] = []
        constants: list[ConstantDef] = []
        invariants: list[InvariantNetwork] = []
        foreign_blocks: list[ForeignBlock] = []
        body: list[Declaration] = []

        for child in self._named_children(node):
            if child.type == "narrative_annotation":
                sl = self._child(child, "string_literal")
                if sl:
                    narrative = self._extract_string_value(sl)
            elif child.type == "domain_annotation":
                ti = self._child(child, "type_identifier")
                sl = self._child(child, "string_literal")
                if ti:
                    domain = self._text(ti)
                elif sl:
                    domain = self._extract_string_value(sl)
            elif child.type == "temporal_annotation":
                ids = self._children_of_type(child, "identifier")
                sl = self._child(child, "string_literal")
                if ids:
                    temporal = [self._text(i) for i in ids]
                elif sl:
                    temporal = [s.strip() for s in self._extract_string_value(sl).split("->")]
            elif child.type == "import_declaration":
                imports.append(self._convert_import_decl(child))
            elif child.type == "import_group":
                # Check if this is a bare module name (type_identifier only,
                # no verb) that starts a multi-line import block.
                group_children = self._named_children(child)
                is_bare_module = (
                    len(group_children) == 1 and group_children[0].type == "type_identifier"
                )
                if is_bare_module:
                    module_name = self._text(group_children[0])
                    imports.append(
                        ImportDecl(
                            module=module_name,
                            items=[],
                            span=self._span(child),
                        )
                    )
                elif imports:
                    self._extend_last_import(imports, child)
                else:
                    imports.append(self._convert_orphan_import_group(child))
            elif child.type == "type_definition":
                types.append(self._convert_type_def(child))
            elif child.type == "binary_type_definition":
                types.append(self._convert_binary_type_def(child))
            elif child.type == "constant_definition":
                constants.append(self._convert_constant_def(child))
            elif child.type == "invariant_network":
                invariants.append(self._convert_invariant_network(child))
            elif child.type == "foreign_block":
                foreign_blocks.append(self._convert_foreign_block(child))
            elif child.type == "function_definition":
                body.append(self._convert_function_def(child))
            elif child.type == "main_definition":
                body.append(self._convert_main_def(child))

        return ModuleDecl(
            name=name,
            narrative=narrative,
            domain=domain,
            temporal=temporal,
            imports=imports,
            types=types,
            constants=constants,
            invariants=invariants,
            foreign_blocks=foreign_blocks,
            body=body,
            span=self._span(node),
        )

    # ── Imports ──────────────────────────────────────────────────

    def _convert_import_decl(self, node: TSNode) -> ImportDecl:
        local = self._has_child(node, "local_module_marker")
        module_name = self._child_text(node, "type_identifier") or ""
        items: list[ImportItem] = []

        # Track verb across groups so bare type/constant groups inherit it
        last_verb: str | None = None
        for group in self._children_of_type(node, "import_group"):
            new_items, last_verb = self._extract_import_items(group, last_verb)
            items.extend(new_items)

        return ImportDecl(module=module_name, items=items, span=self._span(node), local=local)

    def _extract_import_items(
        self, group: TSNode, inherited_verb: str | None = None
    ) -> tuple[list[ImportItem], str | None]:
        items: list[ImportItem] = []
        verb: str | None = inherited_verb

        for child in self._named_children(group):
            if child.type == "import_verb":
                verb_node = self._child(child, "verb") or self._child(child, "async_verb")
                if verb_node:
                    verb = self._text(verb_node)
                else:
                    verb = self._text(child)
            elif child.type == "verb":
                verb = self._text(child)
            elif child.type == "identifier":
                items.append(ImportItem(verb=verb, name=self._text(child), span=self._span(child)))
            elif child.type == "type_identifier":
                items.append(ImportItem(verb=verb, name=self._text(child), span=self._span(child)))
            elif child.type == "constant_identifier":
                items.append(ImportItem(verb=verb, name=self._text(child), span=self._span(child)))

        return items, verb

    def _extend_last_import(self, imports: list[ImportDecl], group: TSNode) -> None:
        """Extend the last import with items from an orphan import group."""
        new_items, _ = self._extract_import_items(group)
        last = imports[-1]
        combined = list(last.items) + new_items
        imports[-1] = ImportDecl(
            module=last.module, items=combined, span=last.span, local=last.local
        )

    def _convert_orphan_import_group(self, group: TSNode) -> ImportDecl:
        """Convert an import_group that appears without a preceding type_identifier."""
        items, _ = self._extract_import_items(group)
        return ImportDecl(module="", items=items, span=self._span(group))

    # ── Type definitions ─────────────────────────────────────────

    def _convert_type_def(self, node: TSNode) -> TypeDef:
        name = self._child_text(node, "type_identifier") or ""
        doc = self._extract_doc_comment(node)

        type_params: list[str] = []
        tp_node = self._child(node, "type_parameters")
        if tp_node:
            type_params = [
                self._text(c) for c in self._children_of_type(tp_node, "type_identifier")
            ]

        modifiers: list[TypeModifier] = []
        mod_node = self._child(node, "type_modifier_bracket")
        if mod_node:
            modifiers = self._extract_type_modifiers_from_bracket(mod_node)

        body = self._convert_type_body(node)
        return TypeDef(
            name=name,
            type_params=type_params,
            modifiers=modifiers,
            body=body,
            span=self._span(node),
            doc_comment=doc,
        )

    def _convert_binary_type_def(self, node: TSNode) -> TypeDef:
        """Convert `binary TypeName Col1 Col2 where entries` shorthand."""
        doc = self._extract_doc_comment(node)
        name = self._child_text(node, "type_identifier") or ""

        # Columns
        type_exprs = self._children_of_type(node, "type_expression")
        named_cols = self._children_of_type(node, "named_lookup_column")
        is_runtime = self._has_token(node, "runtime")

        all_types: list[TypeExpr] = []
        all_names: list[str | None] = []

        for col in named_cols:
            col_name = self._child_text(col, "identifier")
            col_te = self._child(col, "type_expression")
            all_names.append(col_name)
            all_types.append(
                self._convert_type_expr(col_te) if col_te else SimpleType("String", self._span(col))
            )

        for te in type_exprs:
            all_names.append(None)
            all_types.append(self._convert_type_expr(te))

        value_type = all_types[0] if all_types else SimpleType("String", self._span(node))

        # Entries
        entries: list[LookupEntry] = []
        for lv in self._children_of_type(node, "lookup_variant"):
            entries.append(self._convert_lookup_entry(lv))

        body = LookupTypeDef(
            value_type=value_type,
            entries=entries,
            span=self._span(node),
            value_types=tuple(all_types),
            column_names=tuple(all_names),
            is_binary=True,
            is_store_backed=is_runtime,
        )

        return TypeDef(
            name=name,
            type_params=[],
            modifiers=[],
            body=body,
            span=self._span(node),
            doc_comment=doc,
        )

    def _convert_type_body(self, type_def_node: TSNode) -> TypeBody:
        for child in self._named_children(type_def_node):
            if child.type == "algebraic_type_body":
                return self._convert_algebraic(child)
            elif child.type == "record_type_body":
                return self._convert_record(child)
            elif child.type == "refinement_type_body":
                return self._convert_refinement(child)
            elif child.type == "binary_type_body":
                return BinaryDef(span=self._span(child))
            elif child.type in (
                "lookup_type_body",
                "named_lookup_type_body",
                "runtime_lookup_type_body",
                "dispatch_lookup_type_body",
            ):
                return self._convert_lookup(child)

        # Fallback — shouldn't happen with valid grammar
        return BinaryDef(span=self._span(type_def_node))

    def _convert_algebraic(self, node: TSNode) -> AlgebraicTypeDef:
        variants: list[Variant] = []
        for child in self._children_of_type(node, "algebraic_variant"):
            variants.append(self._convert_variant(child))
        return AlgebraicTypeDef(variants=variants, span=self._span(node))

    def _convert_variant(self, node: TSNode) -> Variant:
        name = self._child_text(node, "type_identifier") or ""
        fields: list[FieldDef] = []
        vf = self._child(node, "variant_fields")
        if vf:
            for fd in self._children_of_type(vf, "field_declaration"):
                fields.append(self._convert_field_def(fd))
        return Variant(name=name, fields=fields, span=self._span(node))

    def _convert_field_def(self, node: TSNode) -> FieldDef:
        name = self._child_text(node, "identifier") or ""
        te = self._child(node, "type_expression")
        type_expr = self._convert_type_expr(te) if te else SimpleType("Unit", self._span(node))

        constraint: Expr | None = None
        # Check for where constraint
        if self._has_token(node, "where"):
            sc = self._child(node, "shorthand_constraint")
            expr = self._child(node, "expression")
            if sc:
                constraint = self._convert_shorthand_constraint(sc)
            elif expr:
                constraint = self._convert_expr(expr)

        return FieldDef(
            name=name, type_expr=type_expr, constraint=constraint, span=self._span(node)
        )

    def _convert_record(self, node: TSNode) -> RecordTypeDef:
        fields: list[FieldDef] = []
        for fd in self._children_of_type(node, "field_declaration"):
            fields.append(self._convert_field_def(fd))
        return RecordTypeDef(fields=fields, span=self._span(node))

    def _convert_refinement(self, node: TSNode) -> RefinementTypeDef:
        te = self._child(node, "type_expression")
        base_type = self._convert_type_expr(te) if te else SimpleType("Unit", self._span(node))

        sc = self._child(node, "shorthand_constraint")
        expr = self._child(node, "expression")
        if sc:
            constraint = self._convert_shorthand_constraint(sc)
        elif expr:
            constraint = self._convert_expr(expr)
        else:
            constraint = BooleanLit(True, self._span(node))

        return RefinementTypeDef(base_type=base_type, constraint=constraint, span=self._span(node))

    def _convert_lookup(self, node: TSNode) -> LookupTypeDef:
        is_binary = node.type == "named_lookup_type_body"
        is_runtime = node.type == "runtime_lookup_type_body"
        is_dispatch = node.type == "dispatch_lookup_type_body"
        is_pipe_entry = is_dispatch

        # Extract type expressions (columns)
        type_exprs = self._children_of_type(node, "type_expression")
        named_cols = self._children_of_type(node, "named_lookup_column")

        value_type: TypeExpr
        value_types: tuple[TypeExpr, ...] = ()
        column_names: tuple[str | None, ...] = ()

        if named_cols:
            # Mixed named and bare columns — preserve source order
            all_types: list[TypeExpr] = []
            all_names: list[str | None] = []
            # Collect all column children (named + bare) in source order
            col_children = [
                c for c in node.children if c.type in ("named_lookup_column", "type_expression")
            ]
            for col in col_children:
                if col.type == "named_lookup_column":
                    col_name = self._child_text(col, "identifier")
                    col_te = self._child(col, "type_expression")
                    all_names.append(col_name)
                    all_types.append(
                        self._convert_type_expr(col_te)
                        if col_te
                        else SimpleType("String", self._span(col))
                    )
                else:
                    all_names.append(None)
                    all_types.append(self._convert_type_expr(col))
            value_type = all_types[0] if all_types else SimpleType("String", self._span(node))
            value_types = tuple(all_types)
            column_names = tuple(all_names)
            is_binary = True
        elif type_exprs:
            value_type = self._convert_type_expr(type_exprs[0])
            if len(type_exprs) > 1:
                value_types = tuple(self._convert_type_expr(te) for te in type_exprs)
                is_binary = True
        else:
            value_type = SimpleType("String", self._span(node))

        # Extract entries
        entries: list[LookupEntry] = []
        for lv in self._children_of_type(node, "lookup_variant"):
            if is_binary:
                entries.append(self._convert_lookup_entry(lv))
            else:
                entries.extend(self._convert_lookup_entries_stacked(lv))
        for dv in self._children_of_type(node, "dispatch_lookup_variant"):
            entries.append(self._convert_dispatch_entry(dv))

        return LookupTypeDef(
            value_type=value_type,
            entries=entries,
            span=self._span(node),
            value_types=value_types,
            column_names=column_names,
            is_binary=is_binary,
            is_store_backed=is_runtime,
            is_pipe_entry_format=is_pipe_entry,
            is_dispatch=is_dispatch,
        )

    def _convert_lookup_entry(self, node: TSNode) -> LookupEntry:
        variant_name = self._child_text(node, "type_identifier") or ""
        values: list[str] = []
        value_kinds: list[str] = []

        for child in self._named_children(node):
            if child.type in (
                "string_literal",
                "integer_literal",
                "decimal_literal",
                "boolean_literal",
            ):
                val, kind = self._extract_lookup_value(child)
                values.append(val)
                value_kinds.append(kind)

        value = values[0] if values else ""
        value_kind = value_kinds[0] if value_kinds else "string"

        # For binary lookups (multi-column), ALL values go into the values tuple
        # (including the first). For single-column lookups, values stays empty.
        if len(values) > 1:
            return LookupEntry(
                variant=variant_name,
                value=value,
                value_kind=value_kind,
                span=self._span(node),
                values=tuple(values),
                value_kinds=tuple(value_kinds),
            )
        return LookupEntry(
            variant=variant_name,
            value=value,
            value_kind=value_kind,
            span=self._span(node),
        )

    def _convert_lookup_entries_stacked(self, node: TSNode) -> list[LookupEntry]:
        """For non-binary lookups, a variant with multiple values produces one entry per value."""
        variant_name = self._child_text(node, "type_identifier") or ""
        values: list[tuple[str, str]] = []

        for child in self._named_children(node):
            if child.type in (
                "string_literal",
                "integer_literal",
                "decimal_literal",
                "boolean_literal",
            ):
                val, kind = self._extract_lookup_value(child)
                values.append((val, kind))

        if not values:
            return [
                LookupEntry(
                    variant=variant_name, value="", value_kind="string", span=self._span(node)
                )
            ]

        return [
            LookupEntry(variant=variant_name, value=val, value_kind=kind, span=self._span(node))
            for val, kind in values
        ]

    def _convert_dispatch_entry(self, node: TSNode) -> LookupEntry:
        sl = self._child(node, "string_literal")
        ident = self._child(node, "identifier")
        value = self._extract_string_value(sl) if sl else ""
        name = self._text(ident) if ident else ""
        return LookupEntry(variant=name, value=value, value_kind="string", span=self._span(node))

    def _extract_lookup_value(self, node: TSNode) -> tuple[str, str]:
        if node.type == "string_literal":
            return self._extract_string_value(node), "string"
        elif node.type == "integer_literal":
            return self._text(node), "integer"
        elif node.type == "decimal_literal":
            return self._text(node), "decimal"
        elif node.type == "boolean_literal":
            return self._text(node), "boolean"
        return self._text(node), "string"

    # ── Type expressions ─────────────────────────────────────────

    def _parse_type_from_text(self, text: str, ref_node: TSNode) -> TypeExpr | None:
        """Best-effort type expr from raw text inside an ERROR node."""
        text = text.strip()
        if not text or not text[0].isupper():
            return None
        return SimpleType(text, self._span(ref_node))

    def _convert_type_expr(self, node: TSNode) -> TypeExpr:
        if node.type == "type_expression":
            # type_expression wraps simple_type, generic_type, or modified_type
            inner = self._named_children(node)
            if inner:
                return self._convert_type_expr(inner[0])
            return SimpleType(self._text(node), self._span(node))

        if node.type == "simple_type":
            name = self._child_text(node, "type_identifier") or self._text(node)
            return SimpleType(name, self._span(node))

        if node.type == "generic_type":
            name = self._child_text(node, "type_identifier") or ""
            args: list[TypeExpr] = []
            for te in self._children_of_type(node, "type_expression"):
                args.append(self._convert_type_expr(te))
            return GenericType(name, args, self._span(node))

        if node.type == "modified_type":
            name = self._child_text(node, "type_identifier") or ""
            modifiers = self._extract_type_modifiers(node)
            # Check for generic args
            type_exprs = self._children_of_type(node, "type_expression")
            if type_exprs:
                args = [self._convert_type_expr(te) for te in type_exprs]
                return GenericType(name, args, self._span(node), modifiers=modifiers)
            return ModifiedType(name, modifiers, self._span(node))

        # Fallback
        return SimpleType(self._text(node), self._span(node))

    def _extract_type_modifiers(self, node: TSNode) -> list[TypeModifier]:
        modifiers: list[TypeModifier] = []
        for child in self._named_children(node):
            if child.type == "named_modifier":
                mod_name = self._child_text(child, "type_identifier")
                mod_val = (
                    self._child_text(child, "integer_literal")
                    or self._child_text(child, "identifier")
                    or ""
                )
                modifiers.append(TypeModifier(mod_name, mod_val, self._span(child)))
            elif child.type == "type_identifier":
                # Skip the main type name (first type_identifier is the type name)
                if child == self._child(node, "type_identifier"):
                    continue
                modifiers.append(TypeModifier(None, self._text(child), self._span(child)))
            elif child.type == "identifier":
                modifiers.append(TypeModifier(None, self._text(child), self._span(child)))
            elif child.type == "integer_literal":
                modifiers.append(TypeModifier(None, self._text(child), self._span(child)))
        return modifiers

    def _extract_type_modifiers_from_bracket(self, node: TSNode) -> list[TypeModifier]:
        """Extract modifiers from type_modifier_bracket (on type definitions)."""
        modifiers: list[TypeModifier] = []
        for child in self._children_of_type(node, "type_identifier"):
            modifiers.append(TypeModifier(None, self._text(child), self._span(child)))
        return modifiers

    # ── Function definitions ─────────────────────────────────────

    def _convert_function_def(self, node: TSNode) -> FunctionDef:
        doc = self._extract_doc_comment(node)

        verb_node = self._child(node, "verb") or self._child(node, "async_verb")
        verb = self._text(verb_node) if verb_node else ""

        name = self._child_text(node, "identifier") or ""

        params: list[Param] = []
        pl = self._child(node, "parameter_list")
        if pl:
            params = self._convert_params(pl)

        # Return type: first type_expression that's not inside parameter_list
        return_type: TypeExpr | None = None
        for child in self._named_children(node):
            if child.type == "type_expression" and (not pl or child.start_byte > pl.end_byte):
                return_type = self._convert_type_expr(child)
                break

        can_fail = self._has_child(node, "fail_marker")
        binary = self._has_token(node, "binary")

        # Annotations
        ensures: list[Expr] = []
        requires: list[Expr] = []
        explain: ExplainBlock | None = None
        terminates: Expr | None = None
        trusted: str | None = None
        why_not: list[str] = []
        chosen: str | None = None
        near_misses: list[NearMiss] = []
        know: list[Expr] = []
        assume: list[Expr] = []
        believe: list[Expr] = []
        with_constraints: list[WithConstraint] = []
        intent: str | None = None
        satisfies: list[str] = []
        event_type: TypeExpr | None = None
        state_init: Expr | None = None
        state_type: TypeExpr | None = None

        for child in self._named_children(node):
            if child.type == "ensures_clause":
                e = self._child(child, "expression")
                if e:
                    ensures.append(self._convert_expr(e))
            elif child.type == "requires_clause":
                e = self._child(child, "expression")
                if e:
                    requires.append(self._convert_expr(e))
            elif child.type == "explain_annotation":
                explain = self._convert_explain(child)
            elif child.type == "terminates_annotation":
                e = self._child(child, "expression")
                if e:
                    terminates = self._convert_expr(e)
            elif child.type == "trusted_annotation":
                sl = self._child(child, "string_literal")
                trusted = self._extract_string_value(sl) if sl else ""
            elif child.type == "why_not_annotation":
                sl = self._child(child, "string_literal")
                if sl:
                    why_not.append(self._extract_string_value(sl))
            elif child.type == "chosen_annotation":
                sl = self._child(child, "string_literal")
                if sl:
                    chosen = self._extract_string_value(sl)
            elif child.type == "near_miss_annotation":
                nm = self._convert_near_miss(child)
                if nm:
                    near_misses.append(nm)
            elif child.type == "know_annotation":
                e = self._child(child, "expression")
                if e:
                    know.append(self._convert_expr(e))
            elif child.type == "assume_annotation":
                e = self._child(child, "expression")
                if e:
                    assume.append(self._convert_expr(e))
            elif child.type == "believe_annotation":
                e = self._child(child, "expression")
                if e:
                    believe.append(self._convert_expr(e))
            elif child.type == "with_constraint":
                wc = self._convert_with_constraint(child)
                if wc:
                    with_constraints.append(wc)
            elif child.type == "intent_annotation":
                sl = self._child(child, "string_literal")
                if sl:
                    intent = self._extract_string_value(sl)
            elif child.type == "satisfies_clause":
                ti = self._child(child, "type_identifier")
                if ti:
                    satisfies.append(self._text(ti))
            elif child.type == "event_type_annotation":
                te = self._child(child, "type_expression")
                if te:
                    event_type = self._convert_type_expr(te)
            elif child.type == "state_init_annotation":
                e = self._child(child, "expression")
                if e:
                    state_init = self._convert_expr(e)
            elif child.type == "state_type_annotation":
                te = self._child(child, "type_expression")
                if te:
                    state_type = self._convert_type_expr(te)

        # Body
        body: list[Stmt | MatchExpr] = []
        if not binary:
            body = self._extract_body(node)

        return FunctionDef(
            verb=verb,
            name=name,
            params=params,
            return_type=return_type,
            can_fail=can_fail,
            ensures=ensures,
            requires=requires,
            explain=explain,
            terminates=terminates,
            trusted=trusted,
            binary=binary,
            why_not=why_not,
            chosen=chosen,
            near_misses=near_misses,
            know=know,
            assume=assume,
            believe=believe,
            with_constraints=with_constraints,
            intent=intent,
            satisfies=satisfies,
            event_type=event_type,
            state_init=state_init,
            state_type=state_type,
            body=body,
            doc_comment=doc,
            span=self._span(node),
        )

    def _convert_main_def(self, node: TSNode) -> MainDef:
        doc = self._extract_doc_comment(node)

        return_type: TypeExpr | None = None
        te = self._child(node, "type_expression")
        if te:
            return_type = self._convert_type_expr(te)

        can_fail = self._has_child(node, "fail_marker")
        body = self._extract_body(node)

        return MainDef(
            return_type=return_type,
            can_fail=can_fail,
            body=body,
            doc_comment=doc,
            span=self._span(node),
        )

    def _convert_params(self, node: TSNode) -> list[Param]:
        params: list[Param] = []
        for p in self._children_of_type(node, "parameter"):
            params.append(self._convert_param(p))
        return params

    def _convert_param(self, node: TSNode) -> Param:
        name = self._child_text(node, "identifier") or ""
        te = self._child(node, "type_expression")
        type_expr = self._convert_type_expr(te) if te else SimpleType("Unit", self._span(node))

        constraint: Expr | None = None
        sc = self._child(node, "shorthand_constraint")
        expr = self._child(node, "expression")
        if sc:
            constraint = self._convert_shorthand_constraint(sc)
        elif self._has_token(node, "where") and expr:
            constraint = self._convert_expr(expr)

        return Param(name=name, type_expr=type_expr, constraint=constraint, span=self._span(node))

    def _convert_explain(self, node: TSNode) -> ExplainBlock:
        entries: list[ExplainEntry] = []
        for line in self._children_of_type(node, "explain_line"):
            text = self._text(line).strip()
            # Check for "name: text [when condition]" pattern
            name: str | None = None
            condition: Expr | None = None

            colon_idx = text.find(": ")
            if colon_idx > 0 and text[:colon_idx].isidentifier():
                name = text[:colon_idx]
                text = text[colon_idx + 2 :]

            # Check for "when" condition at the end
            when_idx = text.rfind(" when ")
            if when_idx > 0:
                cond_text = text[when_idx + 6 :].strip()
                text = text[:when_idx].strip()
                # Parse the condition expression by wrapping in a minimal function
                from prove.tree_sitter_setup import ts_parse as _ts_parse

                cond_tree = _ts_parse(f"module _X\nreads _f() Unit\n    from\n        {cond_text}")
                cond_root = cond_tree.root_node
                # Find the function_definition, then get its body expression
                for fn in self._walk_all(cond_root):
                    if fn.type == "function_definition":
                        # Get direct expression children after 'from'
                        found_from = False
                        for c in fn.children:
                            if not c.is_named and self._text(c) == "from":
                                found_from = True
                            elif found_from and c.is_named and c.type == "expression":
                                condition = self._convert_expr(c)
                                break
                        break

            entries.append(
                ExplainEntry(name=name, text=text, condition=condition, span=self._span(line))
            )
        return ExplainBlock(entries=entries, span=self._span(node))

    def _walk_all(self, node: TSNode) -> list[TSNode]:
        """Walk all descendants of a node."""
        result = [node]
        for c in node.children:
            result.extend(self._walk_all(c))
        return result

    def _convert_near_miss(self, node: TSNode) -> NearMiss | None:
        inp = node.child_by_field_name("input")
        exp = node.child_by_field_name("expected")
        if inp and exp:
            return NearMiss(
                input=self._convert_expr(inp),
                expected=self._convert_expr(exp),
                span=self._span(node),
            )
        return None

    def _convert_with_constraint(self, node: TSNode) -> WithConstraint | None:
        ids = self._children_of_type(node, "identifier")
        te = self._child(node, "type_expression")
        if len(ids) >= 2 and te:
            return WithConstraint(
                param_name=self._text(ids[0]),
                field_name=self._text(ids[1]),
                field_type=self._convert_type_expr(te),
                span=self._span(node),
            )
        return None

    def _convert_shorthand_constraint(self, node: TSNode) -> Expr:
        """Convert shorthand constraint like `> 0` to BinaryExpr(self, >, 0)."""
        op = node.child_by_field_name("op")
        value = node.child_by_field_name("value")
        op_str = self._text(op) if op else ">"
        right = self._convert_expr(value) if value else IntegerLit("0", self._span(node))
        return BinaryExpr(
            IdentifierExpr("self", self._span(node)),
            op_str,
            right,
            self._span(node),
        )

    # ── Constants ────────────────────────────────────────────────

    def _convert_constant_def(self, node: TSNode) -> ConstantDef:
        doc = self._extract_doc_comment(node)
        name = (
            self._child_text(node, "constant_identifier")
            or self._child_text(node, "type_identifier")
            or ""
        )

        type_expr: TypeExpr | None = None
        te = self._child(node, "type_expression")
        if te:
            type_expr = self._convert_type_expr(te)

        comptime = self._child(node, "comptime_block")
        expr = self._child(node, "expression")
        if comptime:
            value: Expr = self._convert_comptime(comptime)
        elif expr:
            value = self._convert_expr(expr)
        else:
            value = IntegerLit("0", self._span(node))

        return ConstantDef(
            name=name,
            type_expr=type_expr,
            value=value,
            span=self._span(node),
            doc_comment=doc,
        )

    # ── Invariant networks ───────────────────────────────────────

    def _convert_invariant_network(self, node: TSNode) -> InvariantNetwork:
        name = self._child_text(node, "type_identifier") or ""
        constraints: list[Expr] = []
        for e in self._children_of_type(node, "expression"):
            constraints.append(self._convert_expr(e))
        return InvariantNetwork(name=name, constraints=constraints, span=self._span(node))

    # ── Foreign blocks ───────────────────────────────────────────

    def _convert_foreign_block(self, node: TSNode) -> ForeignBlock:
        sl = self._child(node, "string_literal")
        library = self._extract_string_value(sl) if sl else ""

        functions: list[ForeignFunction] = []
        for ff in self._children_of_type(node, "foreign_function"):
            functions.append(self._convert_foreign_function(ff))

        return ForeignBlock(library=library, functions=functions, span=self._span(node))

    def _convert_foreign_function(self, node: TSNode) -> ForeignFunction:
        name = self._child_text(node, "identifier") or ""
        params: list[Param] = []
        pl = self._child(node, "parameter_list")
        if pl:
            params = self._convert_params(pl)
        te = self._child(node, "type_expression")
        return_type = self._convert_type_expr(te) if te else None
        return ForeignFunction(
            name=name, params=params, return_type=return_type, span=self._span(node)
        )

    # ── Body / statements ────────────────────────────────────────

    def _extract_body(self, node: TSNode) -> list[Any]:
        """Extract body statements from a function/main definition.

        Body content starts after the 'from' keyword. Statements and match arms
        appear as direct children of the function/main definition node.

        Orphan match_arm nodes (siblings of a match_expression in the CST) are
        merged into the preceding MatchExpr's arms list.

        Statements following a match_arm that are more indented than the arm's
        pattern are appended to the last arm's body (tree-sitter doesn't track
        indent/dedent, so we use column position as a heuristic).
        """
        body: list[Any] = []
        in_body = False
        # Track the last match expression and the column of its last arm's pattern
        # so we can absorb continuation statements into that arm.
        last_match_idx: int | None = None
        last_arm_col: int | None = None
        # When the last absorbed item was VarDecl(match), the next expression
        # is the match subject and must be absorbed even at arm-pattern level.
        pending_match_subject = False
        # Buffer comments between implicit match arms so they can be
        # prepended to the next arm's body instead of breaking grouping.
        pending_arm_comments: list[Any] = []
        # Buffer bare literal expressions that precede a match_arm — they
        # become extra patterns sharing the next arm's body (multi-match).
        pending_multi_patterns: list[Pattern] = []

        for child in node.children:
            if not child.is_named and self._text(child) == "from":
                in_body = True
                continue

            if not in_body:
                continue

            if not child.is_named:
                continue

            child_col = child.start_point[1]

            # Detect bare literal expressions that are multi-match patterns:
            # a standalone literal (string, integer, boolean, identifier)
            # followed later by a match_arm shares that arm's body.
            # Only trigger when a match_arm sibling follows (lookahead)
            # AND the literal is at arm-pattern indent (not deeper — a deeper
            # literal is a body statement, e.g. a return value).
            if child.type == "expression" and self._is_bare_match_pattern(child):
                is_at_arm_indent = last_arm_col is None or child_col <= last_arm_col
                if is_at_arm_indent and self._has_following_match_arm(child):
                    pattern = self._literal_to_pattern(child)
                    if pattern is not None:
                        pending_multi_patterns.append(pattern)
                        continue

            if child.type == "match_arm":
                arm = self._convert_match_arm(child)
                # Prepend any buffered comments to this arm's body
                if pending_arm_comments:
                    arm = MatchArm(
                        arm.pattern,
                        pending_arm_comments + list(arm.body),
                        arm.span,
                    )
                    pending_arm_comments = []
                # Desugar multi-pattern: bare literal expressions buffered
                # before this arm become extra arms with the same body.
                extra_patterns = pending_multi_patterns
                pending_multi_patterns = []
                pat_node = self._child(child, "pattern")
                arm_col = pat_node.start_point[1] if pat_node else child_col

                all_arms = [MatchArm(p, list(arm.body), arm.span) for p in extra_patterns]
                all_arms.append(arm)

                for a in all_arms:
                    # Merge into preceding MatchExpr if there is one
                    tracked = (
                        body[last_match_idx]
                        if (last_match_idx is not None and last_match_idx < len(body))
                        else None
                    )
                    assert last_match_idx is not None
                    if isinstance(tracked, MatchExpr):
                        body[last_match_idx] = self._merge_arm_into_match(tracked, a, arm_col)
                    elif isinstance(tracked, VarDecl) and isinstance(tracked.value, MatchExpr):
                        new_match = self._merge_arm_into_match(tracked.value, a, arm_col)
                        body[last_match_idx] = VarDecl(
                            name=tracked.name,
                            type_expr=tracked.type_expr,
                            value=new_match,
                            span=tracked.span,
                        )
                    else:
                        # Wrap in MatchExpr immediately so continuation
                        # statements can be absorbed into the arm's body.
                        body.append(
                            MatchExpr(
                                subject=None,
                                arms=[a],
                                span=a.span,
                            )
                        )
                    last_match_idx = len(body) - 1

                last_arm_col = arm_col
            else:
                # Check if this statement should be absorbed into the last match arm.
                # If it's more indented than the arm pattern, it's a continuation.
                # Also absorb when the last absorbed item was VarDecl(match) —
                # the next expression is the match subject.
                tracked_item = (
                    body[last_match_idx]
                    if (last_match_idx is not None and last_match_idx < len(body))
                    else None
                )
                # Extract MatchExpr from tracked item (bare or inside VarDecl)
                tracked_match: MatchExpr | None = None
                if isinstance(tracked_item, MatchExpr):
                    tracked_match = tracked_item
                elif isinstance(tracked_item, VarDecl) and isinstance(
                    tracked_item.value, MatchExpr
                ):
                    tracked_match = tracked_item.value
                should_absorb = (
                    tracked_match is not None
                    and last_arm_col is not None
                    and (child_col > last_arm_col or pending_match_subject)
                )
                if should_absorb:
                    assert last_match_idx is not None
                    pending_match_subject = False
                    match_expr = tracked_match
                    stmt = self._convert_body_item(child)
                    if stmt is not None:
                        new_match = self._absorb_stmt_into_match(match_expr, stmt, child_col)
                        if isinstance(tracked_item, VarDecl):
                            body[last_match_idx] = VarDecl(
                                name=tracked_item.name,
                                type_expr=tracked_item.type_expr,
                                value=new_match,
                                span=tracked_item.span,
                            )
                        else:
                            body[last_match_idx] = new_match
                        # Check if we just absorbed a VarDecl(match) — next
                        # expression is the match subject.
                        last_arm = new_match.arms[-1]
                        if last_arm.body:
                            tail = last_arm.body[-1]
                            if (
                                isinstance(tail, VarDecl)
                                and isinstance(tail.value, IdentifierExpr)
                                and tail.value.name == "match"
                            ):
                                pending_match_subject = True
                elif (
                    last_match_idx is not None
                    and last_arm_col is not None
                    and child.type in ("comment", "line_comment")
                    and child_col <= last_arm_col
                ):
                    # Comment at arm-pattern indent level between implicit
                    # match arms — buffer it so it can be prepended to the
                    # next arm's body without breaking arm grouping.
                    stmt = self._convert_body_item(child)
                    if stmt is not None:
                        pending_arm_comments.append(stmt)
                else:
                    # Not a match continuation — reset tracking
                    last_match_idx = None
                    last_arm_col = None
                    stmt = self._convert_body_item(child)
                    if stmt is not None:
                        body.append(stmt)
                        # If we just appended a MatchExpr (or VarDecl with
                        # MatchExpr value), start tracking so subsequent orphan
                        # arms/statements can be merged into it.
                        track_match = None
                        if isinstance(stmt, MatchExpr) and stmt.arms:
                            track_match = stmt
                        elif (
                            isinstance(stmt, VarDecl)
                            and isinstance(stmt.value, MatchExpr)
                            and stmt.value.arms
                        ):
                            track_match = stmt.value
                        if track_match is not None:
                            last_match_idx = len(body) - 1
                            arm_nodes = self._children_of_type(child, "match_arm")
                            if arm_nodes:
                                pat_node = self._child(arm_nodes[-1], "pattern")
                                last_arm_col = (
                                    pat_node.start_point[1]
                                    if pat_node
                                    else arm_nodes[-1].start_point[1]
                                )
                            else:
                                last_arm_col = child_col

        # Post-process: fix VarDecl(value=match identifier) followed by
        # call expr + match arms.  Tree-sitter splits "x as T = match expr"
        # into VarDecl(value=match) + ExprStmt(call) + MatchExpr.  Reassemble.
        body = self._fix_match_assignments(body)

        return body

    @classmethod
    def _fix_match_assignments(cls, body: list) -> list:
        """Reassemble split match-in-assignment patterns, recursively."""
        # First, recurse into match arm bodies
        fixed: list = []
        for stmt in body:
            if isinstance(stmt, MatchExpr):
                new_arms = []
                for arm in stmt.arms:
                    new_body = cls._fix_match_assignments(list(arm.body))
                    new_arms.append(MatchArm(arm.pattern, new_body, arm.span))
                fixed.append(MatchExpr(stmt.subject, new_arms, stmt.span))
            elif isinstance(stmt, ExprStmt) and isinstance(stmt.expr, MatchExpr):
                me = stmt.expr
                new_arms = []
                for arm in me.arms:
                    new_body = cls._fix_match_assignments(list(arm.body))
                    new_arms.append(MatchArm(arm.pattern, new_body, arm.span))
                fixed.append(ExprStmt(MatchExpr(me.subject, new_arms, me.span), stmt.span))
            else:
                fixed.append(stmt)
        body = fixed

        # Then fix VarDecl(match) + ExprStmt(subject) + MatchExpr patterns
        i = 0
        result: list = []
        while i < len(body):
            stmt = body[i]
            if (
                isinstance(stmt, VarDecl)
                and isinstance(stmt.value, IdentifierExpr)
                and stmt.value.name == "match"
                and i + 1 < len(body)
            ):
                # Next item should be ExprStmt (the match subject) or MatchExpr
                next_stmt = body[i + 1]
                subject: Expr | None = None
                match_idx = i + 1

                if isinstance(next_stmt, ExprStmt):
                    subject = next_stmt.expr
                    match_idx = i + 2
                elif isinstance(next_stmt, MatchExpr):
                    # match without explicit subject after var decl
                    subject = next_stmt.subject
                    match_idx = i + 1

                if match_idx < len(body) and isinstance(body[match_idx], MatchExpr):
                    match_expr = body[match_idx]
                    if subject is not None and match_expr.subject is None:
                        match_expr = MatchExpr(subject, match_expr.arms, match_expr.span)
                    elif subject is not None:
                        match_expr = MatchExpr(subject, match_expr.arms, match_expr.span)
                    result.append(
                        VarDecl(
                            name=stmt.name,
                            type_expr=stmt.type_expr,
                            value=match_expr,
                            span=stmt.span,
                        )
                    )
                    i = match_idx + 1
                    continue

            result.append(stmt)
            i += 1
        return result

    @staticmethod
    def _tail_match(body: list) -> MatchExpr | None:
        """Return the trailing MatchExpr from an arm body, bare or ExprStmt-wrapped."""
        if not body:
            return None
        tail = body[-1]
        if isinstance(tail, MatchExpr):
            return tail
        if isinstance(tail, ExprStmt) and isinstance(tail.expr, MatchExpr):
            return tail.expr
        if isinstance(tail, VarDecl) and isinstance(tail.value, MatchExpr):
            return tail.value
        return None

    @staticmethod
    def _replace_tail_match(body: list, new_match: MatchExpr) -> list:
        """Replace the trailing MatchExpr in *body*, preserving wrapper type."""
        tail = body[-1]
        if isinstance(tail, MatchExpr):
            return list(body[:-1]) + [new_match]
        if isinstance(tail, VarDecl) and isinstance(tail.value, MatchExpr):
            new_var = VarDecl(
                name=tail.name,
                type_expr=tail.type_expr,
                value=new_match,
                span=tail.span,
            )
            return list(body[:-1]) + [new_var]
        # ExprStmt wrapper
        return list(body[:-1]) + [ExprStmt(new_match, tail.span)]

    def _absorb_stmt_into_match(self, match_expr: MatchExpr, stmt: Any, stmt_col: int) -> MatchExpr:
        """Absorb a statement into the deepest nested match arm by column."""
        last_arm = match_expr.arms[-1]

        # Check if the last arm body ends with a nested MatchExpr
        inner = self._tail_match(last_arm.body)
        if inner is not None and inner.arms:
            inner_last = inner.arms[-1]
            if inner_last.body:
                inner_body_col = inner_last.body[0].span.start_col - 1  # 0-based
                if stmt_col >= inner_body_col:
                    new_inner = self._absorb_stmt_into_match(inner, stmt, stmt_col)
                    new_body = self._replace_tail_match(last_arm.body, new_inner)
                    new_arm = MatchArm(last_arm.pattern, new_body, last_arm.span)
                    return MatchExpr(
                        match_expr.subject,
                        list(match_expr.arms[:-1]) + [new_arm],
                        match_expr.span,
                    )

        # Default: absorb into this match's last arm
        new_arm = MatchArm(
            last_arm.pattern,
            list(last_arm.body) + [stmt],
            last_arm.span,
        )
        return MatchExpr(
            match_expr.subject,
            list(match_expr.arms[:-1]) + [new_arm],
            match_expr.span,
        )

    def _merge_arm_into_match(
        self, match_expr: MatchExpr, arm: MatchArm, arm_col: int
    ) -> MatchExpr:
        """Merge an orphan arm into the deepest nested match by column."""
        last_arm = match_expr.arms[-1]

        # Check if the last arm body ends with a nested MatchExpr
        inner = self._tail_match(last_arm.body)
        if inner is not None and inner.arms:
            inner_arm_col = inner.arms[0].span.start_col - 1  # 0-based
            if arm_col >= inner_arm_col:
                new_inner = self._merge_arm_into_match(inner, arm, arm_col)
                new_body = self._replace_tail_match(last_arm.body, new_inner)
                new_arm_outer = MatchArm(last_arm.pattern, new_body, last_arm.span)
                return MatchExpr(
                    match_expr.subject,
                    list(match_expr.arms[:-1]) + [new_arm_outer],
                    match_expr.span,
                )

        # Check if the last arm body has a pending VarDecl(match) + ExprStmt
        # pattern that should absorb this orphan arm as part of an inner match.
        body = last_arm.body
        if len(body) >= 2:
            tail2, tail1 = body[-2], body[-1]
            if (
                isinstance(tail2, VarDecl)
                and isinstance(tail2.value, IdentifierExpr)
                and tail2.value.name == "match"
                and isinstance(tail1, ExprStmt)
            ):
                inner_match = MatchExpr(tail1.expr, [arm], arm.span)
                new_var = VarDecl(
                    name=tail2.name,
                    type_expr=tail2.type_expr,
                    value=inner_match,
                    span=tail2.span,
                )
                new_body = list(body[:-2]) + [new_var]
                new_arm_outer = MatchArm(last_arm.pattern, new_body, last_arm.span)
                return MatchExpr(
                    match_expr.subject,
                    list(match_expr.arms[:-1]) + [new_arm_outer],
                    match_expr.span,
                )

        # Default: merge into this match
        return MatchExpr(
            match_expr.subject,
            list(match_expr.arms) + [arm],
            match_expr.span,
        )

    def _convert_body_item(self, node: TSNode) -> Any | None:
        """Convert a single body item (statement or match arm)."""
        if node.type == "variable_declaration":
            return self._convert_var_decl(node)
        elif node.type == "assignment":
            return self._convert_assignment(node)
        elif node.type == "match_expression":
            return self._convert_match_expr(node)
        elif node.type == "match_arm":
            return self._convert_match_arm(node)
        elif node.type == "expression":
            return self._convert_expr_stmt(node)
        elif node.type == "line_comment":
            return CommentStmt(self._text(node)[2:].strip(), self._span(node))
        return None

    def _convert_var_decl(self, node: TSNode) -> VarDecl:
        name = self._child_text(node, "identifier") or ""
        te = self._child(node, "type_expression")
        type_expr = self._convert_type_expr(te) if te else None
        expr = self._child(node, "expression")
        value = self._convert_expr(expr) if expr else IntegerLit("0", self._span(node))
        return VarDecl(name=name, type_expr=type_expr, value=value, span=self._span(node))

    def _convert_assignment(self, node: TSNode) -> Assignment | FieldAssignment | VarDecl:
        expr = self._child(node, "expression")
        value = self._convert_expr(expr) if expr else IntegerLit("0", self._span(node))

        # tree-sitter parses "name as = value" and "name as Type = value"
        # as assignment with ERROR on "as [Type]"; recover as VarDecl.
        error_node = self._child(node, "ERROR")
        if error_node and "as" in self._text(error_node):
            ident = self._child(node, "identifier")
            name = self._text(ident) if ident else ""
            # Try to extract type from the ERROR text (e.g. "as Integer")
            err_text = self._text(error_node).strip()
            type_expr = None
            if err_text.startswith("as "):
                type_part = err_text[3:].strip()
                if type_part:
                    type_expr = self._parse_type_from_text(type_part, error_node)
            return VarDecl(name=name, type_expr=type_expr, value=value, span=self._span(node))

        # Check if target is a field expression
        fe = self._child(node, "field_expression")
        if fe:
            obj_expr = self._child(fe, "expression")
            field_id = self._child(fe, "identifier")
            if obj_expr and field_id:
                return FieldAssignment(
                    target=self._convert_expr(obj_expr),
                    field=self._text(field_id),
                    value=value,
                    span=self._span(node),
                )

        ident = self._child(node, "identifier")
        target = self._text(ident) if ident else ""
        return Assignment(target=target, value=value, span=self._span(node))

    def _convert_expr_stmt(self, node: TSNode) -> Stmt:
        """Convert an expression node that appears as a statement.

        Handles the `todo` keyword specially — the Python parser treats
        `todo` or `todo "message"` as TodoStmt.
        """
        expr = self._convert_expr(node)

        # Check for `todo` identifier
        if isinstance(expr, IdentifierExpr) and expr.name == "todo":
            return TodoStmt(message=None, span=self._span(node))

        return ExprStmt(expr=expr, span=self._span(node))

    # ── Expressions ──────────────────────────────────────────────

    def _convert_expr(self, node: TSNode) -> Expr:
        """Convert any expression node to an AST Expr."""
        typ = node.type

        if typ == "expression":
            # Wrapper — unwrap to the single named child
            children = self._named_children(node)
            if len(children) == 1:
                return self._convert_expr(children[0])
            # Edge case: expression with no named children means it's a bare literal/identifier
            return self._convert_expr_leaf(node)

        if typ == "binary_expression":
            return self._convert_binary_expr(node)
        if typ == "unary_expression":
            return self._convert_unary_expr(node)
        if typ == "call_expression":
            return self._convert_call_expr(node)
        if typ == "field_expression":
            return self._convert_field_expr(node)
        if typ == "pipe_expression":
            return self._convert_pipe_expr(node)
        if typ == "fail_propagation":
            return self._convert_fail_prop(node)
        if typ == "async_marker":
            return self._convert_async_call(node)
        if typ == "valid_expression":
            return self._convert_valid_expr(node)
        if typ == "invalid_expression":
            return self._convert_valid_expr(node, negated=True)
        if typ == "lambda_expression":
            return self._convert_lambda_expr(node)
        if typ == "match_expression":
            return self._convert_match_expr(node)
        if typ == "parenthesized_expression":
            expr = self._child(node, "expression")
            return self._convert_expr(expr) if expr else IntegerLit("0", self._span(node))
        if typ == "list_literal":
            return self._convert_list_literal(node)
        if typ == "lookup_access_expression":
            return self._convert_lookup_access(node)
        if typ == "index_expression":
            return self._convert_index_expr(node)
        if typ == "comptime_block":
            return self._convert_comptime(node)

        # Literals
        if typ == "string_literal":
            return self._convert_string_literal(node)
        if typ == "integer_literal":
            return IntegerLit(self._text(node), self._span(node))
        if typ == "decimal_literal":
            text = self._text(node)
            if text.endswith("f"):
                return FloatLit(text, self._span(node))
            return DecimalLit(text, self._span(node))
        if typ == "boolean_literal":
            return BooleanLit(self._text(node) == "true", self._span(node))
        if typ == "character_literal":
            return self._convert_char_literal(node)
        if typ == "regex_literal":
            text = self._text(node)
            # Strip leading/trailing slashes
            return RegexLit(text[1:-1], self._span(node))

        # Identifiers
        if typ == "identifier":
            return IdentifierExpr(self._text(node), self._span(node))
        if typ == "type_identifier":
            return TypeIdentifierExpr(self._text(node), self._span(node))
        if typ == "constant_identifier":
            return IdentifierExpr(self._text(node), self._span(node))

        # Fallback
        return self._convert_expr_leaf(node)

    def _convert_expr_leaf(self, node: TSNode) -> Expr:
        """Convert a leaf node or unknown expression."""
        text = self._text(node)
        span = self._span(node)

        # Try to determine type from text content
        if (
            text.startswith('"')
            or text.startswith('f"')
            or text.startswith('r"')
            or text.startswith('"""')
        ):
            return StringLit(text.strip('"'), span)
        if text == "true":
            return BooleanLit(True, span)
        if text == "false":
            return BooleanLit(False, span)
        if text.isdigit() or (
            text.startswith("0x") or text.startswith("0b") or text.startswith("0o")
        ):
            return IntegerLit(text, span)
        if text[0:1].isupper():
            return TypeIdentifierExpr(text, span)

        return IdentifierExpr(text, span)

    def _convert_binary_expr(self, node: TSNode) -> BinaryExpr:
        exprs = self._children_of_type(node, "expression")
        if len(exprs) >= 2:
            left = self._convert_expr(exprs[0])
            right = self._convert_expr(exprs[1])
        else:
            left = IdentifierExpr("_", self._span(node))
            right = IntegerLit("0", self._span(node))

        # Find the operator (anonymous child between the expressions)
        op = ""
        for child in node.children:
            if not child.is_named:
                text = self._text(child)
                if text in (
                    "==",
                    "!=",
                    "<",
                    ">",
                    "<=",
                    ">=",
                    "+",
                    "-",
                    "*",
                    "/",
                    "%",
                    "||",
                    "&&",
                    "..",
                ):
                    op = text
                    break

        return BinaryExpr(left, op, right, self._span(node))

    def _convert_unary_expr(self, node: TSNode) -> UnaryExpr:
        expr = self._child(node, "expression")
        operand = self._convert_expr(expr) if expr else IntegerLit("0", self._span(node))

        op = ""
        for child in node.children:
            if not child.is_named:
                text = self._text(child)
                if text in ("!", "-"):
                    op = text
                    break

        return UnaryExpr(op, operand, self._span(node))

    def _convert_call_expr(self, node: TSNode) -> CallExpr:
        # func is identifier, type_identifier, or field_expression
        func_node = (
            self._child(node, "field_expression")
            or self._child(node, "identifier")
            or self._child(node, "type_identifier")
        )
        func: Expr = (
            self._convert_expr(func_node) if func_node else IdentifierExpr("_", self._span(node))
        )

        args: list[Expr] = []
        children = list(node.children)
        i = 0
        while i < len(children):
            child = children[i]
            if child.type == "expression":
                expr = self._convert_expr(child)
                # Variant access recovery: expression(TypeIdentifier) + ERROR(.Field)
                # Tree-sitter doesn't recognise Type.Variant as an expression,
                # so it emits type_identifier + ERROR(.Variant).
                if (
                    isinstance(expr, TypeIdentifierExpr)
                    and i + 1 < len(children)
                    and children[i + 1].type == "ERROR"
                ):
                    err_text = self._text(children[i + 1])
                    if err_text.startswith(".") and err_text[1:].isidentifier():
                        expr = FieldExpr(expr, err_text[1:], self._span(child))
                        i += 1  # skip the ERROR node
                args.append(expr)
            i += 1

        return CallExpr(func, args, self._span(node))

    def _convert_field_expr(self, node: TSNode) -> FieldExpr:
        expr = self._child(node, "expression")
        obj = self._convert_expr(expr) if expr else IdentifierExpr("_", self._span(node))
        field = self._child_text(node, "identifier") or ""
        return FieldExpr(obj, field, self._span(node))

    def _convert_pipe_expr(self, node: TSNode) -> PipeExpr:
        exprs = self._children_of_type(node, "expression")
        left = (
            self._convert_expr(exprs[0])
            if len(exprs) > 0
            else IdentifierExpr("_", self._span(node))
        )
        right = (
            self._convert_expr(exprs[1])
            if len(exprs) > 1
            else IdentifierExpr("_", self._span(node))
        )
        return PipeExpr(left, right, self._span(node))

    def _convert_fail_prop(self, node: TSNode) -> FailPropExpr:
        expr = self._child(node, "expression")
        inner = self._convert_expr(expr) if expr else IdentifierExpr("_", self._span(node))
        return FailPropExpr(inner, self._span(node))

    def _convert_async_call(self, node: TSNode) -> AsyncCallExpr:
        expr = self._child(node, "expression")
        inner = self._convert_expr(expr) if expr else IdentifierExpr("_", self._span(node))
        return AsyncCallExpr(inner, self._span(node))

    def _convert_valid_expr(self, node: TSNode, *, negated: bool = False) -> ValidExpr:
        name = self._child_text(node, "identifier") or ""
        exprs = self._children_of_type(node, "expression")
        args: list[Expr] | None = None
        # If there's a parenthesized arg list (has `(` token)
        if self._has_token(node, "("):
            args = [self._convert_expr(e) for e in exprs]
        return ValidExpr(name, args, self._span(node), negated=negated)

    def _convert_lambda_expr(self, node: TSNode) -> LambdaExpr:
        ids = self._children_of_type(node, "identifier")
        expr = self._child(node, "expression")
        # The last expression is the body, identifiers before it are params
        param_names = [self._text(i) for i in ids]
        body = self._convert_expr(expr) if expr else IdentifierExpr("_", self._span(node))
        return LambdaExpr(param_names, body, self._span(node))

    def _convert_match_expr(self, node: TSNode) -> MatchExpr:
        # Subject
        subject_node = self._child(node, "expression")
        subject = self._convert_expr(subject_node) if subject_node else None

        arms: list[MatchArm] = []
        for arm_node in self._children_of_type(node, "match_arm"):
            arms.append(self._convert_match_arm(arm_node))

        return MatchExpr(subject, arms, self._span(node))

    def _convert_match_arm(self, node: TSNode) -> MatchArm:
        pat_node = self._child(node, "pattern")
        pattern = self._convert_pattern(pat_node) if pat_node else WildcardPattern(self._span(node))

        body: list[Stmt] = []
        for child in self._named_children(node):
            if child.type == "pattern":
                continue
            if child.type == "expression":
                body.append(self._convert_expr_stmt(child))
            elif child.type == "variable_declaration":
                body.append(self._convert_var_decl(child))
            elif child.type == "assignment":
                body.append(self._convert_assignment(child))
            elif child.type == "match_expression":
                body.append(ExprStmt(self._convert_match_expr(child), self._span(child)))
            elif child.type in ("comment", "line_comment"):
                text = self._text(child).lstrip("/").strip()
                body.append(CommentStmt(text, self._span(child)))

        return MatchArm(pattern, body, self._span(node))

    @staticmethod
    def _has_following_match_arm(node: TSNode) -> bool:
        """Check if any later named sibling of *node* is a match_arm."""
        sib = node.next_named_sibling
        while sib is not None:
            if sib.type == "match_arm":
                return True
            # Stop at non-literal expressions (they can't be multi-patterns)
            if sib.type not in ("expression", "comment", "line_comment"):
                return False
            sib = sib.next_named_sibling
        return False

    _MULTI_MATCH_LITERAL_TYPES = frozenset(
        {
            "string_literal",
            "integer_literal",
            "decimal_literal",
            "boolean_literal",
        }
    )

    def _is_bare_match_pattern(self, expr_node: TSNode) -> bool:
        """True if an expression node contains only a bare literal (multi-match candidate)."""
        children = self._named_children(expr_node)
        if len(children) != 1:
            return False
        return children[0].type in self._MULTI_MATCH_LITERAL_TYPES

    def _literal_to_pattern(self, expr_node: TSNode) -> Pattern | None:
        """Convert a bare literal expression node to a match Pattern."""
        children = self._named_children(expr_node)
        if not children:
            return None
        child = children[0]
        span = self._span(child)
        if child.type == "string_literal":
            return LiteralPattern(self._extract_string_value(child), span, kind="string")
        if child.type == "integer_literal":
            return LiteralPattern(self._text(child), span, kind="integer")
        if child.type == "decimal_literal":
            return LiteralPattern(self._text(child), span, kind="decimal")
        if child.type == "boolean_literal":
            return LiteralPattern(self._text(child), span, kind="boolean")
        return None

    def _convert_index_expr(self, node: TSNode) -> IndexExpr:
        exprs = self._children_of_type(node, "expression")
        obj = (
            self._convert_expr(exprs[0])
            if len(exprs) > 0
            else IdentifierExpr("_", self._span(node))
        )
        index = (
            self._convert_expr(exprs[1]) if len(exprs) > 1 else IntegerLit("0", self._span(node))
        )
        return IndexExpr(obj, index, self._span(node))

    def _convert_list_literal(self, node: TSNode) -> ListLiteral:
        elements: list[Expr] = []
        for e in self._children_of_type(node, "expression"):
            elements.append(self._convert_expr(e))
        return ListLiteral(elements, self._span(node))

    def _convert_lookup_access(self, node: TSNode) -> LookupAccessExpr:
        type_name = ""
        operand_expr: Expr = IdentifierExpr("_", self._span(node))

        children = self._named_children(node)
        if children:
            # First child is the type name
            type_name = self._text(children[0])
            # Second child is the operand
            if len(children) > 1:
                operand_expr = self._convert_expr(children[1])

        return LookupAccessExpr(type_name, operand_expr, self._span(node))

    def _convert_comptime(self, node: TSNode) -> ComptimeExpr:
        body: list[Any] = []
        in_body = False
        for child in node.children:
            if not child.is_named and self._text(child) == "comptime":
                in_body = True
                continue
            if in_body and child.is_named:
                if child.type == "match_arm":
                    # Orphan match_arm: merge into preceding MatchExpr
                    arm = self._convert_match_arm(child)
                    if body and isinstance(body[-1], MatchExpr):
                        body[-1] = MatchExpr(
                            subject=body[-1].subject,
                            arms=list(body[-1].arms) + [arm],
                            span=body[-1].span,
                        )
                        continue
                item = self._convert_body_item(child)
                if item is not None:
                    body.append(item)
        return ComptimeExpr(body, self._span(node))

    # ── Patterns ─────────────────────────────────────────────────

    def _convert_pattern(self, node: TSNode) -> Pattern:
        # Pattern node wraps the actual pattern
        children = self._named_children(node)
        if not children:
            text = self._text(node)
            if text == "_":
                return WildcardPattern(self._span(node))
            return BindingPattern(text, self._span(node))

        child = children[0]
        if child.type == "variant_pattern":
            return self._convert_variant_pattern(child)
        if child.type == "wildcard_pattern":
            return WildcardPattern(self._span(child))
        if child.type == "lookup_pattern":
            return self._convert_lookup_pattern(child)
        if child.type == "string_literal":
            return LiteralPattern(
                self._extract_string_value(child), self._span(child), kind="string"
            )
        if child.type == "integer_literal":
            return LiteralPattern(self._text(child), self._span(child), kind="integer")
        if child.type == "decimal_literal":
            return LiteralPattern(self._text(child), self._span(child), kind="decimal")
        if child.type == "boolean_literal":
            return LiteralPattern(self._text(child), self._span(child), kind="boolean")
        if child.type == "identifier":
            return BindingPattern(self._text(child), self._span(child))

        return WildcardPattern(self._span(node))

    def _convert_variant_pattern(self, node: TSNode) -> VariantPattern:
        name = self._child_text(node, "type_identifier") or ""
        fields: list[Pattern] = []
        for p in self._children_of_type(node, "pattern"):
            fields.append(self._convert_pattern(p))
        return VariantPattern(name, fields, self._span(node))

    def _convert_lookup_pattern(self, node: TSNode) -> LookupPattern:
        children = self._named_children(node)
        type_name = self._text(children[0]) if children else ""

        lookup_value = ""
        value_kind = "identifier"
        if len(children) > 1:
            val_node = children[1]
            lookup_value = self._text(val_node)
            if val_node.type == "string_literal":
                lookup_value = self._extract_string_value(val_node)
                value_kind = "string"
            elif val_node.type == "integer_literal":
                value_kind = "integer"
            elif val_node.type == "type_identifier":
                value_kind = "identifier"
            elif val_node.type == "identifier":
                value_kind = "identifier"

        return LookupPattern(type_name, lookup_value, self._span(node), value_kind=value_kind)

    # ── String handling ──────────────────────────────────────────

    def _convert_string_literal(self, node: TSNode) -> Expr:
        """Convert a string_literal node. Dispatches based on string kind."""
        # Check children for format_string, raw_string, triple_string
        fs = self._child(node, "format_string")
        if fs:
            return self._convert_format_string(fs)

        rs = self._child(node, "raw_string")
        if rs:
            return self._convert_raw_string(rs)

        # Check for triple string (starts with """)
        text = self._text(node)
        if text.startswith('"""'):
            inner = text[3:-3] if text.endswith('"""') else text[3:]
            return TripleStringLit(inner, self._span(node))

        # Simple string — extract value between quotes
        return StringLit(self._extract_string_value(node), self._span(node))

    def _convert_format_string(self, node: TSNode) -> StringInterp:
        """Convert f"..." format string to StringInterp."""
        parts: list[Expr] = []
        for child in self._named_children(node):
            if child.type == "interpolation":
                expr = self._child(child, "expression")
                if expr:
                    parts.append(self._convert_expr(expr))
            elif child.type == "escape_sequence":
                parts.append(StringLit(self._unescape(self._text(child)), self._span(child)))
            else:
                parts.append(StringLit(self._text(child), self._span(child)))

        # Walk children and collect text from byte gaps between them.
        # Tree-sitter doesn't emit static text between interpolations as
        # child nodes — they exist only as byte gaps in the source.
        # Use UTF-8 bytes for gap extraction because tree-sitter offsets
        # are byte offsets, not character offsets.
        result_parts: list[Expr] = []
        current_text = ""
        src_bytes = self.source.encode("utf-8")
        pos = node.start_byte
        for child in node.children:
            # Collect any gap text between previous position and this child
            if child.start_byte > pos:
                gap = src_bytes[pos : child.start_byte].decode("utf-8")
                current_text += gap

            if child.type == "interpolation":
                if current_text:
                    result_parts.append(StringLit(current_text, self._span(child)))
                    current_text = ""
                expr = self._child(child, "expression")
                if expr:
                    result_parts.append(self._convert_expr(expr))
            elif child.type == "escape_sequence":
                current_text += self._unescape(self._text(child))
            elif not child.is_named:
                # Skip f", ", {, } delimiters — they're part of syntax
                text = self._text(child)
                if text not in ('f"', '"', "{", "}"):
                    current_text += text
            else:
                current_text += self._text(child)

            pos = child.end_byte

        # Gap after last child before closing quote
        if node.end_byte > pos:
            gap = src_bytes[pos : node.end_byte].decode("utf-8")
            if gap not in ('"',):
                current_text += gap

        if current_text:
            result_parts.append(StringLit(current_text, self._span(node)))

        return StringInterp(result_parts, self._span(node))

    def _convert_raw_string(self, node: TSNode) -> RawStringLit:
        """Convert r"..." raw/regex string."""
        # Collect all text between the r" and closing "
        text = self._text(node)
        if text.startswith('r"') and text.endswith('"'):
            inner = text[2:-1]
        else:
            inner = text
        return RawStringLit(inner, self._span(node))

    def _convert_char_literal(self, node: TSNode) -> CharLit:
        text = self._text(node)
        # Strip surrounding single quotes
        if text.startswith("'") and text.endswith("'"):
            inner = text[1:-1]
        else:
            inner = text
        # Unescape if needed
        if inner.startswith("\\"):
            inner = self._unescape(inner)
        return CharLit(inner, self._span(node))

    def _extract_string_value(self, node: TSNode) -> str:
        """Extract the unquoted string value from a string_literal node."""
        text = self._text(node)

        # Triple string
        if text.startswith('"""'):
            return text[3:-3] if text.endswith('"""') else text[3:]

        # Format string
        if text.startswith('f"'):
            return text[2:-1] if text.endswith('"') else text[2:]

        # Raw string
        if text.startswith('r"'):
            return text[2:-1] if text.endswith('"') else text[2:]

        # Simple string
        if text.startswith('"') and text.endswith('"'):
            inner = text[1:-1]
            return self._unescape_string(inner)

        return text

    def _unescape(self, s: str) -> str:
        """Unescape a single escape sequence."""
        _MAP = {
            "\\n": "\n",
            "\\r": "\r",
            "\\t": "\t",
            "\\\\": "\\",
            '\\"': '"',
            "\\0": "\0",
            "\\{": "{",
            "\\}": "}",
        }
        return _MAP.get(s, s)

    def _unescape_string(self, s: str) -> str:
        """Unescape all escape sequences in a string."""
        result = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                esc = s[i : i + 2]
                result.append(self._unescape(esc))
                i += 2
            else:
                result.append(s[i])
                i += 1
        return "".join(result)

    # ── Doc comments ─────────────────────────────────────────────

    def _extract_doc_comment(self, node: TSNode) -> str | None:
        """Extract doc comment text from a doc_comment_block child."""
        block = self._child(node, "doc_comment_block")
        if not block:
            return None

        lines: list[str] = []
        for dc in self._children_of_type(block, "doc_comment"):
            text = self._text(dc)
            # Strip the /// prefix
            if text.startswith("///"):
                text = text[3:]
            lines.append(text.strip())

        return "\n".join(lines) if lines else None
