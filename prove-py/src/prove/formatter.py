"""AST-walking pretty-printer for Prove source code.

Produces canonical formatting for .prv files. Walks the parsed AST and
emits source text using the same isinstance-dispatch pattern as c_emitter.py.

v0.8: When a SymbolTable is provided, the formatter infers type annotations
for variable declarations whose RHS is a function call.

Standalone ``//`` comments (between declarations and inside function bodies)
are preserved. Trailing comments on the same line as code are not preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    AsyncCallExpr,
    BinaryExpr,
    BinaryLookupExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    CommentDecl,
    CommentStmt,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    ExplainBlock,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FieldExpr,
    FloatLit,
    ForeignBlock,
    ForeignFunction,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    ImportDecl,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupPattern,
    LookupTypeDef,
    MainDef,
    MatchArm,
    MatchExpr,
    ModifiedType,
    Module,
    ModuleDecl,
    PathLit,
    PipeExpr,
    RawStringLit,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TodoStmt,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    VariantPattern,
    WildcardPattern,
)

if TYPE_CHECKING:
    from prove.errors import Diagnostic
    from prove.symbols import SymbolTable
    from prove.types import Type

_STRING_ESCAPE_MAP = {
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    '"': '\\"',
    "\0": "\\0",
}


def _escape_string(value: str) -> str:
    """Re-escape a string value for source output."""
    return value.translate(str.maketrans(_STRING_ESCAPE_MAP))


# Operator precedence table (higher binds tighter)
_PRECEDENCE: dict[str, int] = {
    "||": 1,
    "&&": 2,
    "==": 3,
    "!=": 3,
    "<": 4,
    ">": 4,
    "<=": 4,
    ">=": 4,
    "..": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
}

if TYPE_CHECKING:
    from prove.errors import Diagnostic
    from prove.symbols import SymbolTable
    from prove.types import Type


class ProveFormatter:
    """Format a parsed Prove Module back to canonical source text."""

    def __init__(
        self,
        symbols: SymbolTable | None = None,
        diagnostics: list[Diagnostic] | None = None,
    ) -> None:
        self._symbols = symbols
        # Local type context: maps variable/parameter names to type strings
        # within the currently-formatted function body.
        self._local_types: dict[str, str] = {}
        # Build span lookup sets for auto-fixable diagnostics
        self._unused_var_spans: set[tuple[str, int, int]] = set()
        self._unused_type_spans: set[tuple[str, int, int]] = set()
        self._unused_constant_spans: set[tuple[str, int, int]] = set()
        self._unused_import_spans: set[tuple[str, int, int]] = set()
        self._unknown_module_spans: set[tuple[str, int, int]] = set()
        self._strip_async_marker_spans: set[tuple[str, int, int]] = set()
        self._add_async_marker_spans: set[tuple[str, int, int]] = set()
        self._indent_level = 0  # current nesting depth (in 4-space units)
        self._extra_col = 0  # extra prefix width (e.g. match arm pattern)
        for d in diagnostics or []:
            if d.code == "I375":
                for lbl in d.labels:
                    s = lbl.span
                    self._strip_async_marker_spans.add((s.file, s.start_line, s.start_col))
            elif d.code == "I378":
                for lbl in d.labels:
                    s = lbl.span
                    self._add_async_marker_spans.add((s.file, s.start_line, s.start_col))
            elif d.code == "I300":
                for lbl in d.labels:
                    s = lbl.span
                    self._unused_var_spans.add((s.file, s.start_line, s.start_col))
            elif d.code == "I302":
                for lbl in d.labels:
                    s = lbl.span
                    self._unused_import_spans.add((s.file, s.start_line, s.start_col))
            elif d.code == "I303":
                for lbl in d.labels:
                    s = lbl.span
                    self._unused_type_spans.add((s.file, s.start_line, s.start_col))
            elif d.code == "I304":
                for lbl in d.labels:
                    s = lbl.span
                    self._unused_constant_spans.add((s.file, s.start_line, s.start_col))
            elif d.code == "I314":
                for lbl in d.labels:
                    s = lbl.span
                    self._unknown_module_spans.add((s.file, s.start_line, s.start_col))

    # ── Public API ─────────────────────────────────────────────

    def format(self, module: Module) -> str:
        """Format a module to canonical source text."""
        parts: list[str] = []
        for i, decl in enumerate(module.declarations):
            if i > 0:
                parts.append("")  # blank line between top-level decls
            parts.append(self._format_declaration(decl))
        result = "\n".join(parts)
        if not result.endswith("\n"):
            result += "\n"
        return result

    # ── Declaration dispatch ───────────────────────────────────

    def _format_declaration(self, decl: object) -> str:
        if isinstance(decl, FunctionDef):
            return self._format_function_def(decl)
        if isinstance(decl, MainDef):
            return self._format_main_def(decl)
        if isinstance(decl, ModuleDecl):
            return self._format_module_decl(decl)
        if isinstance(decl, CommentDecl):
            return f"// {decl.text}" if decl.text else "//"
        return ""

    # ── Function definitions ───────────────────────────────────

    def _format_function_def(self, fd: FunctionDef) -> str:
        lines: list[str] = []

        # Doc comment
        if fd.doc_comment:
            for doc_line in fd.doc_comment.splitlines():
                lines.append(f"/// {doc_line}" if doc_line else "///")

        # Signature: verb name(params) ReturnType[!]
        param_strs = [
            f"{p.name} {self._format_type_expr(p.type_expr)}"
            + (f" where {self._format_expr(p.constraint)}" if p.constraint else "")
            for p in fd.params
        ]
        verb = fd.verb
        params_inline = ", ".join(param_strs)
        sig = f"{verb} {fd.name}({params_inline})"
        if fd.return_type and fd.verb != "validates":
            sig += f" {self._format_type_expr(fd.return_type)}"
        if fd.can_fail:
            sig += "!"

        if len(sig) > self.MAX_LINE_LENGTH and len(param_strs) > 1:
            # Group params: one per line, 4-space indent
            grouped = ",\n    ".join(param_strs)
            sig = f"{verb} {fd.name}(\n    {grouped}\n)"
            if fd.return_type and fd.verb != "validates":
                sig += f" {self._format_type_expr(fd.return_type)}"
            if fd.can_fail:
                sig += "!"

        lines.append(sig)

        # Annotations (2-space indent relative to signature)
        lines.extend(self._format_annotations(fd))

        # binary or from + body (4-space indent)
        if fd.binary:
            lines.append("binary")
        else:
            # Register parameter types for expression-level inference
            self._local_types.clear()
            for p in fd.params:
                self._local_types[p.name] = self._format_type_expr(p.type_expr)
            lines.append("from")
            self._indent_level += 1
            for stmt in fd.body:
                lines.append(self._indent(self._format_stmt(stmt), 1))
            self._indent_level -= 1
            self._local_types.clear()

        return "\n".join(lines)

    def _format_main_def(self, md: MainDef) -> str:
        lines: list[str] = []

        if md.doc_comment:
            for doc_line in md.doc_comment.splitlines():
                lines.append(f"/// {doc_line}" if doc_line else "///")

        sig = "main()"
        if md.return_type:
            sig += f" {self._format_type_expr(md.return_type)}"
        if md.can_fail:
            sig += "!"
        lines.append(sig)

        lines.append("from")
        self._indent_level += 1
        for stmt in md.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))
        self._indent_level -= 1

        return "\n".join(lines)

    def _format_annotations(self, fd: FunctionDef) -> list[str]:
        """Format contract annotations with 2-space indent."""
        lines: list[str] = []
        for expr in fd.ensures:
            lines.append(f"  ensures {self._format_expr(expr)}")
        for expr in fd.requires:
            lines.append(f"  requires {self._format_expr(expr)}")
        if fd.explain:
            lines.extend(self._format_explain_block(fd.explain, 2))
        if fd.terminates is not None:
            lines.append(f"  terminates: {self._format_expr(fd.terminates)}")
        if fd.trusted is not None:
            if fd.trusted:
                lines.append(f'  trusted: "{fd.trusted}"')
            else:
                lines.append("  trusted")
        for text in fd.why_not:
            lines.append(f'  why_not: "{text}"')
        if fd.chosen:
            lines.append(f'  chosen: "{fd.chosen}"')
        for nm in fd.near_misses:
            lines.append(
                f"  near_miss {self._format_expr(nm.input)} => {self._format_expr(nm.expected)}"
            )
        for expr in fd.know:
            lines.append(f"  know: {self._format_expr(expr)}")
        for expr in fd.assume:
            lines.append(f"  assume: {self._format_expr(expr)}")
        for expr in fd.believe:
            lines.append(f"  believe: {self._format_expr(expr)}")
        for wc in fd.with_constraints:
            lines.append(
                f"  with {wc.param_name}.{wc.field_name} {self._format_type_expr(wc.field_type)}"
            )
        if fd.intent:
            lines.append(f'  intent: "{fd.intent}"')
        for name in fd.satisfies:
            lines.append(f"  satisfies {name}")
        if fd.event_type is not None:
            lines.append(f"  event_type {self._format_type_expr(fd.event_type)}")
        if fd.state_init is not None:
            lines.append(f"  state_init {self._format_expr(fd.state_init)}")
        if fd.state_type is not None:
            lines.append(f"  state_type {self._format_type_expr(fd.state_type)}")
        return lines

    def _format_explain_block(self, explain: ExplainBlock, indent: int) -> list[str]:
        prefix = " " * indent
        lines = [f"{prefix}explain"]
        for entry in explain.entries:
            if entry.name is not None:
                line = f"{prefix}    {entry.name}: {entry.text}"
                if entry.condition is not None:
                    line += f" when {self._format_expr(entry.condition)}"
                lines.append(line)
            else:
                lines.append(f"{prefix}    {entry.text}")
        return lines

    # ── Type definitions ───────────────────────────────────────

    def _format_type_def(self, td: TypeDef) -> str:
        result = self._format_type_def_body(td)
        if td.doc_comment:
            doc_lines: list[str] = []
            for doc_line in td.doc_comment.splitlines():
                doc_lines.append(f"/// {doc_line}" if doc_line else "///")
            doc_lines.append(result)
            return "\n".join(doc_lines)
        return result

    def _format_type_def_body(self, td: TypeDef) -> str:
        params = ""
        if td.type_params:
            params = "<" + ", ".join(td.type_params) + ">"

        # Format modifiers (e.g., :[Lookup])
        mods = ""
        if td.modifiers:
            mod_parts = []
            for m in td.modifiers:
                if m.name is not None:
                    mod_parts.append(f"{m.name}:{m.value}")
                else:
                    mod_parts.append(m.value)
            mods = ":[" + ", ".join(mod_parts) + "]"

        body = td.body
        if isinstance(body, LookupTypeDef):
            if body.is_store_backed:
                col_types = " | ".join(self._format_type_expr(vt) for vt in body.value_types)
                return f"type {td.name}{mods}{params} is {col_types}\n  runtime"
            if body.is_dispatch:
                return self._format_pipe_entry_lookup(td.name, body, mods, params)
            if body.is_binary:
                return self._format_binary_lookup_type_def(td.name, body, mods, params)
            return self._format_lookup_type_def(td.name, mods, params, body)

        if isinstance(body, RecordTypeDef):
            lines = [f"type {td.name}{mods}{params} is"]
            for f in body.fields:
                constraint = ""
                if f.constraint:
                    constraint = f" where {self._format_expr(f.constraint)}"
                lines.append(f"  {f.name} {self._format_type_expr(f.type_expr)}{constraint}")
            return "\n".join(lines)

        if isinstance(body, AlgebraicTypeDef):
            parts: list[str] = []
            for v in body.variants:
                if v.fields:
                    fields = ", ".join(
                        f"{f.name} {self._format_type_expr(f.type_expr)}"
                        + (f" where {self._format_expr(f.constraint)}" if f.constraint else "")
                        for f in v.fields
                    )
                    parts.append(f"{v.name}({fields})")
                else:
                    parts.append(v.name)
            if len(parts) == 1:
                return f"type {td.name}{mods}{params} is {parts[0]}"
            # Multi-variant: first on same line, rest with | prefix
            variant_str = parts[0]
            for p in parts[1:]:
                variant_str += f"\n  | {p}"
            return f"type {td.name}{mods}{params} is {variant_str}"

        if isinstance(body, RefinementTypeDef):
            base = self._format_type_expr(body.base_type)
            constraint = self._format_expr(body.constraint)
            return f"type {td.name}{mods}{params} is {base} where {constraint}"

        from prove.ast_nodes import BinaryDef

        if isinstance(body, BinaryDef):
            return f"type {td.name}{mods}{params} is binary"

        return f"type {td.name}{mods}{params} is ..."

    def _format_lookup_type_def(
        self, name: str, mods: str, params: str, body: LookupTypeDef
    ) -> str:
        """Format a [Lookup] type definition with stacking support."""
        value_type = self._format_type_expr(body.value_type)
        lines = [f"type {name}{mods}{params} is {value_type} where"]

        # Group entries by variant for stacking
        i = 0
        while i < len(body.entries):
            entry = body.entries[i]
            val = self._format_lookup_value(entry)
            lines.append(f"  {entry.variant} | {val}")
            # Check for stacked entries (same variant)
            pad = " " * len(entry.variant)
            i += 1
            while i < len(body.entries) and body.entries[i].variant == entry.variant:
                stacked = body.entries[i]
                val = self._format_lookup_value(stacked)
                lines.append(f"  {pad} | {val}")
                i += 1

        return "\n".join(lines)

    def _format_lookup_value(self, entry: object) -> str:
        """Format a lookup entry value."""
        from prove.ast_nodes import LookupEntry

        assert isinstance(entry, LookupEntry)
        if entry.value_kind == "string":
            return f'"{_escape_string(entry.value)}"'
        return entry.value

    def _format_binary_lookup_type_def(
        self, name: str, body: LookupTypeDef, mods: str = "", params: str = ""
    ) -> str:
        """Format a binary lookup type definition."""
        if body.is_pipe_entry_format:
            return self._format_pipe_entry_lookup(name, body, mods, params)

        # Format columns with optional name: prefix
        col_parts: list[str] = []
        for i, vt in enumerate(body.value_types):
            formatted_type = self._format_type_expr(vt)
            col_name = (
                body.column_names[i] if body.column_names and i < len(body.column_names) else None
            )
            if col_name:
                col_parts.append(f"{col_name}:{formatted_type}")
            else:
                col_parts.append(formatted_type)
        col_types = " ".join(col_parts)
        if mods:
            # Parsed via type Name:[Lookup] is Type1 Type2 where
            lines = [f"type {name}{mods}{params} is {col_types} where"]
        else:
            # Parsed via binary Name Type1 Type2 where
            lines = [f"binary {name} {col_types} where"]

        for entry in body.entries:
            if entry.values:
                vals = " | ".join(
                    f'"{_escape_string(v)}"' if k == "string" else v
                    for v, k in zip(entry.values, entry.value_kinds)
                )
                lines.append(f"  {entry.variant} | {vals}")
            else:
                val = self._format_lookup_value(entry)
                lines.append(f"  {entry.variant} | {val}")

        return "\n".join(lines)

    def _format_pipe_entry_lookup(
        self, name: str, body: LookupTypeDef, mods: str = "", params: str = ""
    ) -> str:
        """Format a pipe-separated lookup: type X:[Lookup] is T1 | T2 with entries."""
        col_types = " | ".join(self._format_type_expr(vt) for vt in body.value_types)
        lines = [f"type {name}{mods}{params} is {col_types}"]

        for entry in body.entries:
            if entry.values:
                vals = " | ".join(
                    f'"{_escape_string(v)}"' if k == "string" else v
                    for v, k in zip(entry.values, entry.value_kinds)
                )
                lines.append(f"  {vals}")
            else:
                val = self._format_lookup_value(entry)
                lines.append(f"  {val}")

        return "\n".join(lines)

    # ── Constant definitions ───────────────────────────────────

    def _format_constant_def(self, cd: ConstantDef) -> str:
        type_ann = ""
        if cd.type_expr:
            type_ann = f" {self._format_type_expr(cd.type_expr)}"

        if isinstance(cd.value, ComptimeExpr):
            lines = [f"{cd.name} as{type_ann} = comptime"]
            self._indent_level += 1
            for stmt in cd.value.body:
                lines.append(self._indent(self._format_stmt(stmt), 1))
            self._indent_level -= 1
            return "\n".join(lines)

        return f"{cd.name} as{type_ann} = {self._format_expr(cd.value)}"

    # ── Import declarations ────────────────────────────────────

    MAX_LINE_LENGTH = 90

    # Canonical ordering for verb groups in import lines.
    _VERB_ORDER = {
        "types": 0,
        "derives": 1,
        "creates": 2,
        "validates": 3,
        "transforms": 4,
        "matches": 5,
        "dispatches": 6,
        "inputs": 7,
        "attached": 8,
        "outputs": 9,
        "detached": 10,
        "streams": 11,
        "listens": 12,
        "constants": 13,
    }

    def _format_import_decl(self, imp: ImportDecl) -> str | None:
        # Filter out unused import items (W302)
        items = [item for item in imp.items if not self._is_unused_import(item.span)]
        if not items:
            return None  # entire import line is unused

        # Group items by verb, merging duplicates and ensuring unique names.
        groups: dict[str | None, list[str]] = {}
        for item in items:
            if item.verb not in groups:
                groups[item.verb] = []
            if item.name not in groups[item.verb]:
                groups[item.verb].append(item.name)

        # Sort verb groups by canonical order.
        sorted_groups = sorted(
            groups.items(),
            key=lambda kv: self._VERB_ORDER.get(kv[0] or "", 99),
        )

        # Build verb group strings
        group_strings = []
        for verb, names in sorted_groups:
            if verb:
                group_strings.append(f"{verb} {' '.join(names)}")
            else:
                group_strings.append(" ".join(names))

        prefix = f".{imp.module}" if getattr(imp, "local", False) else imp.module
        line = f"{prefix} {' '.join(group_strings)}"
        # If within line length, use single line
        if len(line) <= self.MAX_LINE_LENGTH:
            return line

        # Over line length: module name on its own line, one verb group per continuation
        # line; names within a group wrap with deeper indent if needed.
        GROUP_INDENT = "  "  # 2 spaces (becomes 4 in module context)
        CONT_INDENT = "    "  # 4 spaces (becomes 6 in module context)
        result_lines = [prefix]

        for verb, names in sorted_groups:
            line_start = f"{GROUP_INDENT}{verb}" if verb else GROUP_INDENT

            current_line = line_start
            for name in names:
                candidate = current_line + " " + name
                if len(candidate) <= self.MAX_LINE_LENGTH:
                    current_line = candidate
                else:
                    result_lines.append(current_line)
                    current_line = CONT_INDENT + name
            result_lines.append(current_line)

        return "\n".join(result_lines)

    # ── Module declarations ────────────────────────────────────

    def _format_module_decl(self, mod: ModuleDecl) -> str:
        lines = [f"module {mod.name}"]

        if mod.narrative:
            lines.append(f'  narrative: """{mod.narrative}"""')

        if mod.domain:
            lines.append(f"  domain {mod.domain}")

        if mod.temporal:
            lines.append(f"  temporal {' -> '.join(mod.temporal)}")

        # Merge duplicate module imports into a single ImportDecl per module.
        merged_imports: dict[tuple[str, bool], ImportDecl] = {}
        import_order: list[tuple[str, bool]] = []
        for imp in mod.imports:
            if self._is_unknown_module(imp.span):
                continue
            key = (imp.module, getattr(imp, "local", False))
            if key in merged_imports:
                merged_imports[key].items.extend(imp.items)
            else:
                from prove.ast_nodes import ImportDecl as _ID

                merged_imports[key] = _ID(
                    module=imp.module,
                    items=list(imp.items),
                    span=imp.span,
                    local=getattr(imp, "local", False),
                )
                import_order.append(key)

        for key in import_order:
            formatted_imp = self._format_import_decl(merged_imports[key])
            if formatted_imp is not None:
                for imp_line in formatted_imp.split("\n"):
                    lines.append(f"  {imp_line}")

        for fb in mod.foreign_blocks:
            lines.append("")
            formatted = self._format_foreign_block(fb)
            lines.append(self._indent_spaces(formatted, 2))

        for td in mod.types:
            if self._is_unused_type(td.span):
                continue  # W303: drop unused type definitions
            lines.append("")
            formatted = self._format_type_def(td)
            # Indent type definition by 2 spaces inside module
            lines.append(self._indent_spaces(formatted, 2))

        for cd in mod.constants:
            if self._is_unused_constant(cd.span):
                continue  # I304: drop unused constant definitions
            lines.append("")
            formatted = self._format_constant_def(cd)
            lines.append(self._indent_spaces(formatted, 2))

        for inv in mod.invariants:
            lines.append("")
            formatted = self._format_invariant_network(inv)
            lines.append(self._indent_spaces(formatted, 2))

        for decl in mod.body:
            lines.append("")
            formatted = self._format_declaration(decl)
            lines.append(self._indent_spaces(formatted, 2))

        return "\n".join(lines)

    # ── Invariant network ──────────────────────────────────────

    def _format_invariant_network(self, inv: InvariantNetwork) -> str:
        lines = [f"invariant_network {inv.name}"]
        for constraint in inv.constraints:
            lines.append(f"  {self._format_expr(constraint)}")
        return "\n".join(lines)

    # ── Foreign blocks ──────────────────────────────────────────

    def _format_foreign_block(self, fb: ForeignBlock) -> str:
        lines = [f'foreign "{fb.library}"']
        for ff in fb.functions:
            lines.append(f"  {self._format_foreign_function(ff)}")
        return "\n".join(lines)

    def _format_foreign_function(self, ff: ForeignFunction) -> str:
        params = ", ".join(f"{p.name} {self._format_type_expr(p.type_expr)}" for p in ff.params)
        sig = f"{ff.name}({params})"
        if ff.return_type is not None:
            sig += f" {self._format_type_expr(ff.return_type)}"
        return sig

    # ── Lookup declarations ─────────────────────────────────────

    # ── Statement formatting ───────────────────────────────────

    def _format_stmt(self, stmt: object) -> str:
        if isinstance(stmt, VarDecl):
            return self._format_var_decl(stmt)
        if isinstance(stmt, Assignment):
            return self._format_assignment(stmt)
        if isinstance(stmt, FieldAssignment):
            return (
                f"{self._format_expr(stmt.target)}.{stmt.field} = {self._format_expr(stmt.value)}"
            )
        if isinstance(stmt, ExprStmt):
            return self._format_expr(stmt.expr)
        if isinstance(stmt, MatchExpr):
            return self._format_match_expr(stmt)
        if isinstance(stmt, CommentStmt):
            return f"// {stmt.text}" if stmt.text else "//"
        if isinstance(stmt, TodoStmt):
            if stmt.message:
                return f'todo "{stmt.message}"'
            return "todo"
        return ""

    def _format_var_decl(self, vd: VarDecl) -> str:
        type_ann = ""
        if vd.type_expr:
            type_ann = f" {self._format_type_expr(vd.type_expr)}"
            self._local_types[vd.name] = self._format_type_expr(vd.type_expr)
        elif self._symbols is not None:
            inferred = self._infer_var_type(vd.value)
            if inferred:
                type_ann = f" {inferred}"
                self._local_types[vd.name] = inferred
        name = vd.name
        if not name.startswith("_") and self._is_unused_var(vd.span):
            name = f"_{name}"
        value = self._format_expr(vd.value)
        line = f"{name} as{type_ann} = {value}"
        if self._indent_level * 4 + len(line) > self.MAX_LINE_LENGTH:
            # For match expressions, keep "name = match subject" on one line
            # so the tree-sitter parser can parse it as match-in-assignment.
            if isinstance(vd.value, MatchExpr) and "\n" in value:
                first_line = value.split("\n", 1)[0]
                rest = value.split("\n", 1)[1]
                line = f"{name} as{type_ann} = {first_line}\n{rest}"
            else:
                line = f"{name} as{type_ann} =\n    {value}"
        return line

    def _format_assignment(self, assign: Assignment) -> str:
        """Format an assignment, promoting to VarDecl syntax when possible.

        When the RHS type can be inferred (function call, binary expression,
        literal, etc.), emit ``name as Type = expr`` (variable declaration)
        instead of plain ``name = expr``.
        """
        name = assign.target
        if not name.startswith("_") and self._is_unused_var(assign.span):
            name = f"_{name}"
        if self._symbols is not None:
            inferred = self._infer_var_type(assign.value)
            if inferred:
                self._local_types[assign.target] = inferred
                value = self._format_expr(assign.value)
                line = f"{name} as {inferred} = {value}"
                if self._indent_level * 4 + len(line) > self.MAX_LINE_LENGTH:
                    line = f"{name} as {inferred} =\n    {value}"
                return line
        value = self._format_expr(assign.value)
        line = f"{name} = {value}"
        if self._indent_level * 4 + len(line) > self.MAX_LINE_LENGTH:
            line = f"{name} =\n    {value}"
        return line

    # ── Expression formatting ──────────────────────────────────

    def _format_expr(self, expr: object, parent_prec: int = 0) -> str:
        if isinstance(expr, IntegerLit):
            return expr.value
        if isinstance(expr, DecimalLit):
            return expr.value
        if isinstance(expr, FloatLit):
            return expr.value
        if isinstance(expr, StringLit):
            return f'"{_escape_string(expr.value)}"'
        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"
        if isinstance(expr, CharLit):
            return f"'{_escape_string(expr.value)}'"
        if isinstance(expr, RegexLit):
            return f"/{expr.pattern}/"
        if isinstance(expr, RawStringLit):
            return f'r"{expr.value}"'
        if isinstance(expr, PathLit):
            return expr.value
        if isinstance(expr, TripleStringLit):
            return f'"""{expr.value}"""'
        if isinstance(expr, StringInterp):
            return self._format_string_interp(expr)
        if isinstance(expr, ListLiteral):
            elems = ", ".join(self._format_expr(e) for e in expr.elements)
            return f"[{elems}]"
        if isinstance(expr, IdentifierExpr):
            return expr.name
        if isinstance(expr, TypeIdentifierExpr):
            return expr.name
        if isinstance(expr, BinaryExpr):
            return self._format_binary(expr, parent_prec)
        if isinstance(expr, UnaryExpr):
            return self._format_unary(expr)
        if isinstance(expr, CallExpr):
            return self._format_call(expr)
        if isinstance(expr, FieldExpr):
            return f"{self._format_expr(expr.obj, 99)}.{expr.field}"
        if isinstance(expr, PipeExpr):
            return f"{self._format_expr(expr.left)} |> {self._format_expr(expr.right)}"
        if isinstance(expr, FailPropExpr):
            return f"{self._format_expr(expr.expr)}!"
        if isinstance(expr, AsyncCallExpr):
            s = expr.span
            key = (s.file, s.start_line, s.start_col)
            if key in self._strip_async_marker_spans:
                return self._format_expr(expr.expr)
            return f"{self._format_expr(expr.expr)}&"
        if isinstance(expr, LambdaExpr):
            return self._format_lambda(expr)
        if isinstance(expr, ValidExpr):
            keyword = "invalid" if expr.negated else "valid"
            if expr.args is not None:
                args = ", ".join(self._format_expr(a) for a in expr.args)
                return f"{keyword} {expr.name}({args})"
            return f"{keyword} {expr.name}"
        if isinstance(expr, MatchExpr):
            return self._format_match_expr(expr)
        if isinstance(expr, ComptimeExpr):
            return self._format_comptime(expr)
        if isinstance(expr, IndexExpr):
            return f"{self._format_expr(expr.obj, 99)}[{self._format_expr(expr.index)}]"
        if isinstance(expr, LookupAccessExpr):
            return f"{expr.type_name}:{self._format_expr(expr.operand, 99)}"
        if isinstance(expr, BinaryLookupExpr):
            return f"{expr.type_name}:{self._format_expr(expr.operand, 99)}"
        if isinstance(expr, StoreLookupExpr):
            return f"{expr.table_var}:{self._format_expr(expr.operand, 99)}"
        return "???"

    def _format_binary(self, expr: BinaryExpr, parent_prec: int) -> str:
        prec = _PRECEDENCE.get(expr.op, 0)
        left = self._format_expr(expr.left, prec)
        right = self._format_expr(expr.right, prec + 1)
        result = f"{left} {expr.op} {right}"
        if prec < parent_prec:
            return f"({result})"
        return result

    def _format_unary(self, expr: UnaryExpr) -> str:
        operand = self._format_expr(expr.operand, 99)
        if expr.op == "!":
            return f"!{operand}"
        return f"{expr.op}{operand}"

    def _format_call(self, expr: CallExpr) -> str:
        func = self._format_expr(expr.func, 99)
        arg_strs = [self._format_expr(a) for a in expr.args]
        args = ", ".join(arg_strs)
        s = expr.span
        key = (s.file, s.start_line, s.start_col)
        suffix = "&" if key in self._add_async_marker_spans else ""
        result = f"{func}({args}){suffix}"

        if self._indent_level * 4 + len(result) > self.MAX_LINE_LENGTH:
            # Try multiline string interp wrapping
            col = len(func) + 1  # column of f in f"
            for i, a in enumerate(expr.args):
                if isinstance(a, StringInterp):
                    wrapped = self._format_string_interp(a, col=col, force=True)
                    if "\n" in wrapped:
                        arg_strs[i] = wrapped
                        args = ", ".join(arg_strs)
                        return f"{func}({args}){suffix}"
                    break
                col += len(arg_strs[i]) + 2  # skip past this arg + ", "

            # Fall back to per-argument multiline: indent args 4 spaces
            # relative to the call (not absolute indent_level, since
            # _indent() from callers already adds the base indentation).
            if len(arg_strs) > 1:
                rel_indent = "    "
                sep = ",\n" + rel_indent
                return f"{func}(\n{rel_indent}{sep.join(arg_strs)}){suffix}"

        return result

    def _format_lambda(self, expr: LambdaExpr) -> str:
        params = ", ".join(expr.params)
        body = self._format_expr(expr.body)
        return f"|{params}| {body}"

    def _format_string_interp(
        self,
        expr: StringInterp,
        col: int = 0,
        force: bool = False,
    ) -> str:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, StringLit):
                parts.append(_escape_string(part.value))
            else:
                parts.append("{" + self._format_expr(part) + "}")
        single = 'f"' + "".join(parts) + '"'

        if not force and self._indent_level * 4 + col + len(single) <= self.MAX_LINE_LENGTH:
            return single

        # Check there are expression parts worth breaking
        has_exprs = any(not isinstance(p, StringLit) for p in expr.parts)
        if not has_exprs:
            return single

        # Multi-line: each interpolation on its own lines
        # Expressions align after f", closing } aligns with f
        expr_indent = " " * (col + 2)
        brace_indent = " " * col

        result_parts: list[str] = ['f"']
        for part in expr.parts:
            if isinstance(part, StringLit):
                result_parts.append(_escape_string(part.value))
            else:
                formatted = self._format_expr(part)
                result_parts.append("{\n" + expr_indent + formatted + "\n" + brace_indent + "}")
        result_parts.append('"')
        return "".join(result_parts)

    def _format_match_expr(self, expr: MatchExpr) -> str:
        lines: list[str] = []
        grouped = self._group_multi_pattern_arms(expr.arms)
        if expr.subject is not None:
            lines.append(f"match {self._format_expr(expr.subject)}")
            self._indent_level += 1
            for group in grouped:
                lines.extend(self._indent(line, 1) for line in self._format_arm_group(group))
                if isinstance(group[-1].pattern, WildcardPattern):
                    break  # W301: drop unreachable arms after wildcard
            self._indent_level -= 1
        else:
            # Implicit match — arms at current level (no extra indent)
            for group in grouped:
                lines.extend(self._format_arm_group(group))
                if isinstance(group[-1].pattern, WildcardPattern):
                    break  # W301: drop unreachable arms after wildcard
        return "\n".join(lines)

    def _group_multi_pattern_arms(self, arms: list[MatchArm]) -> list[list[MatchArm]]:
        """Group consecutive arms whose bodies are identical (desugared multi-pattern)."""
        if not arms:
            return []
        groups: list[list[MatchArm]] = [[arms[0]]]
        for arm in arms[1:]:
            prev = groups[-1][0]
            # Compare body by equality; desugared multi-pattern arms share
            # the same body objects so this is reliable.
            if arm.body == prev.body:
                groups[-1].append(arm)
            else:
                groups.append([arm])
        return groups

    def _format_arm_group(self, group: list[MatchArm]) -> list[str]:
        """Format a group of arms sharing the same body as multi-pattern syntax."""
        if len(group) == 1:
            return [self._format_arm(group[0])]
        # Multi-pattern: emit bare patterns on their own lines, last one gets => body
        result: list[str] = []
        for arm in group[:-1]:
            result.append(self._format_pattern(arm.pattern))
        result.append(self._format_arm(group[-1]))
        return result

    def _format_arm(self, arm: MatchArm) -> str:
        pat = self._format_pattern(arm.pattern)
        if len(arm.body) == 1:
            # Preserve multi-line layout: if body was on a different line
            # than the pattern in the original source, keep it multi-line.
            body_was_multiline = arm.body[0].span.start_line > arm.span.start_line
            if not body_was_multiline:
                body = self._format_stmt(arm.body[0])
                line = f"{pat} => {body}"
                if "\n" not in body and self._indent_level * 4 + len(line) <= self.MAX_LINE_LENGTH:
                    return line
        # Multi-statement arm (or single-stmt that doesn't fit / was multi-line)
        lines = [f"{pat} =>"]
        self._indent_level += 1
        for stmt in arm.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))
        self._indent_level -= 1
        return "\n".join(lines)

    def _format_comptime(self, expr: ComptimeExpr) -> str:
        lines = ["comptime"]
        self._indent_level += 1
        for stmt in expr.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))
        self._indent_level -= 1
        return "\n".join(lines)

    # ── Pattern formatting ─────────────────────────────────────

    def _format_pattern(self, pat: object) -> str:
        if isinstance(pat, VariantPattern):
            if pat.fields:
                fields = ", ".join(self._format_pattern(f) for f in pat.fields)
                return f"{pat.name}({fields})"
            return pat.name
        if isinstance(pat, WildcardPattern):
            return "_"
        if isinstance(pat, LiteralPattern):
            if pat.kind == "string":
                return f'"{_escape_string(pat.value)}"'
            return pat.value
        if isinstance(pat, BindingPattern):
            return pat.name
        if isinstance(pat, LookupPattern):
            if pat.value_kind == "string":
                return f'{pat.type_name}:"{_escape_string(pat.lookup_value)}"'
            return f"{pat.type_name}:{pat.lookup_value}"
        return "???"

    # ── Type expression formatting ─────────────────────────────

    def _format_type_expr(self, te: object) -> str:
        if isinstance(te, SimpleType):
            return te.name
        if isinstance(te, GenericType):
            args = ", ".join(self._format_type_expr(a) for a in te.args)
            base = f"{te.name}<{args}>"
            if te.modifiers:
                mods = " ".join(
                    (f"{m.name}:{m.value}" if m.name else m.value) for m in te.modifiers
                )
                return f"{base}:[{mods}]"
            return base
        if isinstance(te, ModifiedType):
            mods = " ".join((f"{m.name}:{m.value}" if m.name else m.value) for m in te.modifiers)
            return f"{te.name}:[{mods}]"
        return "???"

    # ── Type inference (v0.8) ────────────────────────────────────

    def _infer_var_type(self, value: object) -> str | None:
        """Infer a type annotation string from a value expression.

        Handles literals, identifiers (via local type context), binary and
        unary expressions, function calls, and FailProp.  Returns None if
        no inference is possible.
        """
        assert self._symbols is not None
        return self._infer_expr_type_str(value)

    def _infer_expr_type_str(self, expr: object) -> str | None:
        """Infer a type string for an arbitrary expression.

        Returns the source-level type name (e.g. "Integer") or None.
        """
        # Literals
        if isinstance(expr, IntegerLit):
            return "Integer"
        if isinstance(expr, DecimalLit):
            return "Decimal"
        if isinstance(expr, FloatLit):
            return "Float"
        if isinstance(
            expr, (StringLit, RawStringLit, TripleStringLit, PathLit, RegexLit, StringInterp)
        ):
            return "String"
        if isinstance(expr, BooleanLit):
            return "Boolean"
        if isinstance(expr, CharLit):
            return "Character"

        # Identifier — look up in local type context
        if isinstance(expr, IdentifierExpr):
            return self._local_types.get(expr.name)

        # Binary expression
        if isinstance(expr, BinaryExpr):
            # Comparison and logical operators always return Boolean
            if expr.op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||"):
                return "Boolean"
            # Arithmetic — infer from operands
            if expr.op in ("+", "-", "*", "/", "%"):
                left = self._infer_expr_type_str(expr.left)
                right = self._infer_expr_type_str(expr.right)
                if left is not None:
                    return left
                if right is not None:
                    return right
            return None

        # Unary expression
        if isinstance(expr, UnaryExpr):
            if expr.op == "!":
                return "Boolean"
            return self._infer_expr_type_str(expr.operand)

        # FailProp: expr! — unwrap Result
        if isinstance(expr, FailPropExpr):
            inner_type = self._resolve_call_return(expr.expr, prefer_result=True)
            if inner_type is not None:
                return self._unwrap_result(inner_type)
            # Try general inference for non-call FailProp
            return self._infer_expr_type_str(expr.expr)

        # Function/constructor calls — existing logic
        if isinstance(expr, CallExpr):
            return self._resolve_call_return_str(expr)

        # List literal
        if isinstance(expr, ListLiteral):
            if expr.elements:
                elem = self._infer_expr_type_str(expr.elements[0])
                if elem is not None:
                    return f"List<{elem}>"
            return None

        return None

    def _resolve_call_return_str(self, expr: object) -> str | None:
        """If expr is a call, resolve and stringify its return type."""
        ty = self._resolve_call_return(expr)
        if ty is None:
            return None
        return self._type_to_str(ty)

    def _resolve_call_return(
        self,
        expr: object,
        *,
        prefer_result: bool = False,
    ) -> Type | None:
        """Resolve the return type of a call expression.

        When *prefer_result* is True (FailProp context), prefer overloads
        that return ``Result<Value, Error>`` over those that don't.
        """
        assert self._symbols is not None
        from prove.types import GenericInstance

        if not isinstance(expr, CallExpr):
            return None

        arg_count = len(expr.args)

        def _pick_sig(name: str) -> Type | None:
            sig = self._symbols.resolve_function(None, name, arg_count)
            if sig is None:
                sig = self._symbols.resolve_function_any(name, arity=arg_count)
            if sig is None:
                return None
            if not prefer_result:
                return sig.return_type
            # In FailProp context, prefer a Result-returning overload
            ret = sig.return_type
            if isinstance(ret, GenericInstance) and ret.base_name == "Result":
                return ret
            # Check all overloads for a Result-returning one
            all_fns = self._symbols.all_functions()
            for (_v, fname), sigs in all_fns.items():
                if fname != name:
                    continue
                for s in sigs:
                    if len(s.param_types) != arg_count:
                        continue
                    r = s.return_type
                    if isinstance(r, GenericInstance) and r.base_name == "Result":
                        return r
            return ret

        # Module-qualified call: Module.function(args)
        if isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            return _pick_sig(expr.func.field)

        # Unqualified call: function(args)
        if isinstance(expr.func, IdentifierExpr):
            return _pick_sig(expr.func.name)

        # Type constructor call: TypeName(args)
        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            result = _pick_sig(name)
            if result is not None:
                return result
            resolved = self._symbols.resolve_type(name)
            if resolved is not None:
                return resolved
            return None

        return None

    def _unwrap_result(self, ty: Type) -> str | None:
        """Unwrap Result<Value, Error> to Value as the annotation string.

        FailProp (!) propagates the error case, so the variable holds the
        success type Value.  For non-Result return types, stringify as-is.
        """
        from prove.types import ErrorType, GenericInstance, UnitType

        if isinstance(ty, (UnitType, ErrorType)):
            return None
        # Result<Value, Error> → Value (the success type)
        if isinstance(ty, GenericInstance) and ty.base_name == "Result" and ty.args:
            return self._type_to_str(ty.args[0])
        return self._type_to_str(ty)

    @staticmethod
    def _type_to_str(ty: Type) -> str | None:
        """Convert a resolved Type to source-level type syntax."""
        from prove.types import ErrorType, FunctionType, UnitType, type_name

        if isinstance(ty, (UnitType, ErrorType, FunctionType)):
            return None
        return type_name(ty)

    # ── Diagnostic-driven fixes ─────────────────────────────────

    def _is_unused_var(self, span: object) -> bool:
        """Check if a variable declaration span was flagged as W300."""
        return (span.file, span.start_line, span.start_col) in self._unused_var_spans

    def _is_unused_type(self, span: object) -> bool:
        """Check if a type definition span was flagged as W303."""
        return (span.file, span.start_line, span.start_col) in self._unused_type_spans

    def _is_unused_constant(self, span: object) -> bool:
        """Check if a constant definition span was flagged as I304."""
        return (span.file, span.start_line, span.start_col) in self._unused_constant_spans

    def _is_unused_import(self, span: object) -> bool:
        """Check if an import item span was flagged as I302."""
        return (span.file, span.start_line, span.start_col) in self._unused_import_spans

    def _is_unknown_module(self, span: object) -> bool:
        """Check if an import declaration span was flagged as I314."""
        return (span.file, span.start_line, span.start_col) in self._unknown_module_spans

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _indent(text: str, levels: int) -> str:
        prefix = "    " * levels
        return "\n".join(prefix + line if line else line for line in text.splitlines())

    @staticmethod
    def _indent_spaces(text: str, spaces: int) -> str:
        prefix = " " * spaces
        return "\n".join(prefix + line if line else line for line in text.splitlines())
