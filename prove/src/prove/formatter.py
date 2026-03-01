"""AST-walking pretty-printer for Prove source code.

Produces canonical formatting for .prv files. Walks the parsed AST and
emits source text using the same isinstance-dispatch pattern as c_emitter.py.

Limitation (v0.1): Regular ``//`` comments are not preserved in the AST
(discarded by the lexer). Doc comments (``///``) are preserved and emitted.
"""

from __future__ import annotations

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
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
    MainDef,
    MatchArm,
    MatchExpr,
    ModifiedType,
    Module,
    ModuleDecl,
    PathLit,
    PipeExpr,
    ProofBlock,
    RawStringLit,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    VariantPattern,
    WildcardPattern,
)

# Operator precedence table (higher binds tighter)
_PRECEDENCE: dict[str, int] = {
    "||": 1,
    "&&": 2,
    "==": 3, "!=": 3,
    "<": 4, ">": 4, "<=": 4, ">=": 4,
    "..": 5,
    "+": 6, "-": 6,
    "*": 7, "/": 7, "%": 7,
}


class ProveFormatter:
    """Format a parsed Prove Module back to canonical source text."""

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
        return ""

    # ── Function definitions ───────────────────────────────────

    def _format_function_def(self, fd: FunctionDef) -> str:
        lines: list[str] = []

        # Doc comment
        if fd.doc_comment:
            for doc_line in fd.doc_comment.splitlines():
                lines.append(f"/// {doc_line}" if doc_line else "///")

        # Signature: verb name(params) ReturnType[!]
        params = ", ".join(
            f"{p.name} {self._format_type_expr(p.type_expr)}"
            + (f" where {self._format_expr(p.constraint)}" if p.constraint else "")
            for p in fd.params
        )
        sig = f"{fd.verb} {fd.name}({params})"
        if fd.return_type:
            sig += f" {self._format_type_expr(fd.return_type)}"
        if fd.can_fail:
            sig += "!"
        lines.append(sig)

        # Annotations (2-space indent relative to signature)
        lines.extend(self._format_annotations(fd))

        # from + body (4-space indent)
        lines.append("from")
        for stmt in fd.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))

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
        for stmt in md.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))

        return "\n".join(lines)

    def _format_annotations(self, fd: FunctionDef) -> list[str]:
        """Format contract annotations with 2-space indent."""
        lines: list[str] = []
        for expr in fd.ensures:
            lines.append(f"  ensures {self._format_expr(expr)}")
        for expr in fd.requires:
            lines.append(f"  requires {self._format_expr(expr)}")
        if fd.proof:
            lines.extend(self._format_proof_block(fd.proof, 2))
        for text in fd.why_not:
            lines.append(f'  why_not: "{text}"')
        if fd.chosen:
            lines.append(f'  chosen: "{fd.chosen}"')
        for nm in fd.near_misses:
            lines.append(
                f"  near_miss: {self._format_expr(nm.input)}"
                f"  => {self._format_expr(nm.expected)}"
            )
        for expr in fd.know:
            lines.append(f"  know: {self._format_expr(expr)}")
        for expr in fd.assume:
            lines.append(f"  assume: {self._format_expr(expr)}")
        for expr in fd.believe:
            lines.append(f"  believe: {self._format_expr(expr)}")
        if fd.intent:
            lines.append(f'  intent: "{fd.intent}"')
        for name in fd.satisfies:
            lines.append(f"  satisfies {name}")
        return lines

    def _format_proof_block(self, proof: ProofBlock, indent: int) -> list[str]:
        prefix = " " * indent
        lines = [f"{prefix}proof"]
        for obl in proof.obligations:
            lines.append(f"{prefix}  {obl.name}: {obl.text}")
        return lines

    # ── Type definitions ───────────────────────────────────────

    def _format_type_def(self, td: TypeDef) -> str:
        params = ""
        if td.type_params:
            params = "<" + ", ".join(td.type_params) + ">"

        body = td.body
        if isinstance(body, RecordTypeDef):
            lines = [f"type {td.name}{params} is"]
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
                return f"type {td.name}{params} is {parts[0]}"
            # Multi-variant: first on same line, rest with | prefix
            variant_str = parts[0]
            for p in parts[1:]:
                variant_str += f"\n  | {p}"
            return f"type {td.name}{params} is {variant_str}"

        if isinstance(body, RefinementTypeDef):
            base = self._format_type_expr(body.base_type)
            constraint = self._format_expr(body.constraint)
            return f"type {td.name}{params} is {base} where {constraint}"

        from prove.ast_nodes import BinaryDef
        if isinstance(body, BinaryDef):
            return f"type {td.name}{params} is binary"

        return f"type {td.name}{params} is ..."

    # ── Constant definitions ───────────────────────────────────

    def _format_constant_def(self, cd: ConstantDef) -> str:
        type_ann = ""
        if cd.type_expr:
            type_ann = f" {self._format_type_expr(cd.type_expr)}"

        if isinstance(cd.value, ComptimeExpr):
            lines = [f"{cd.name} as{type_ann} = comptime"]
            for stmt in cd.value.body:
                lines.append(self._indent(self._format_stmt(stmt), 1))
            return "\n".join(lines)

        return f"{cd.name} as{type_ann} = {self._format_expr(cd.value)}"

    # ── Import declarations ────────────────────────────────────

    def _format_import_decl(self, imp: ImportDecl) -> str:
        # Group items by verb, preserving order of first appearance.
        groups: list[tuple[str | None, list[str]]] = []
        seen: dict[str | None, int] = {}
        for item in imp.items:
            if item.verb in seen:
                groups[seen[item.verb]][1].append(item.name)
            else:
                seen[item.verb] = len(groups)
                groups.append((item.verb, [item.name]))
        parts = []
        for verb, names in groups:
            if verb:
                parts.append(f"{verb} {' '.join(names)}")
            else:
                parts.append(" ".join(names))
        return f"{imp.module} {', '.join(parts)}"

    # ── Module declarations ────────────────────────────────────

    def _format_module_decl(self, mod: ModuleDecl) -> str:
        lines = [f"module {mod.name}"]

        if mod.narrative:
            lines.append(f'  narrative: """{mod.narrative}"""')

        if mod.temporal:
            lines.append(f"  temporal: {' -> '.join(mod.temporal)}")

        for imp in mod.imports:
            lines.append(f"  {self._format_import_decl(imp)}")

        for td in mod.types:
            lines.append("")
            formatted = self._format_type_def(td)
            # Indent type definition by 2 spaces inside module
            lines.append(self._indent_spaces(formatted, 2))

        for cd in mod.constants:
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
            lines.append(self._indent(formatted, 1))

        return "\n".join(lines)

    # ── Invariant network ──────────────────────────────────────

    def _format_invariant_network(self, inv: InvariantNetwork) -> str:
        lines = [f"invariant_network {inv.name}"]
        for constraint in inv.constraints:
            lines.append(f"  {self._format_expr(constraint)}")
        return "\n".join(lines)

    # ── Statement formatting ───────────────────────────────────

    def _format_stmt(self, stmt: object) -> str:
        if isinstance(stmt, VarDecl):
            return self._format_var_decl(stmt)
        if isinstance(stmt, Assignment):
            return f"{stmt.target} = {self._format_expr(stmt.value)}"
        if isinstance(stmt, ExprStmt):
            return self._format_expr(stmt.expr)
        if isinstance(stmt, MatchExpr):
            return self._format_match_expr(stmt)
        return ""

    def _format_var_decl(self, vd: VarDecl) -> str:
        type_ann = ""
        if vd.type_expr:
            type_ann = f" {self._format_type_expr(vd.type_expr)}"
        return f"{vd.name} as{type_ann} = {self._format_expr(vd.value)}"

    # ── Expression formatting ──────────────────────────────────

    def _format_expr(self, expr: object, parent_prec: int = 0) -> str:
        if isinstance(expr, IntegerLit):
            return expr.value
        if isinstance(expr, DecimalLit):
            return expr.value
        if isinstance(expr, StringLit):
            return f'"{expr.value}"'
        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"
        if isinstance(expr, CharLit):
            return f"'{expr.value}'"
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
        if isinstance(expr, LambdaExpr):
            return self._format_lambda(expr)
        if isinstance(expr, ValidExpr):
            if expr.args is not None:
                args = ", ".join(self._format_expr(a) for a in expr.args)
                return f"valid {expr.name}({args})"
            return f"valid {expr.name}"
        if isinstance(expr, MatchExpr):
            return self._format_match_expr(expr)
        if isinstance(expr, ComptimeExpr):
            return self._format_comptime(expr)
        if isinstance(expr, IndexExpr):
            return f"{self._format_expr(expr.obj, 99)}[{self._format_expr(expr.index)}]"
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
        args = ", ".join(self._format_expr(a) for a in expr.args)
        return f"{func}({args})"

    def _format_lambda(self, expr: LambdaExpr) -> str:
        params = ", ".join(expr.params)
        body = self._format_expr(expr.body)
        return f"|{params}| {body}"

    def _format_string_interp(self, expr: StringInterp) -> str:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, StringLit):
                parts.append(part.value)
            else:
                parts.append("{" + self._format_expr(part) + "}")
        return 'f"' + "".join(parts) + '"'

    def _format_match_expr(self, expr: MatchExpr) -> str:
        lines: list[str] = []
        if expr.subject is not None:
            lines.append(f"match {self._format_expr(expr.subject)}")
        else:
            # Implicit match (arms at current level)
            pass

        for arm in expr.arms:
            lines.append(self._indent(self._format_arm(arm), 1))
        return "\n".join(lines)

    def _format_arm(self, arm: MatchArm) -> str:
        pat = self._format_pattern(arm.pattern)
        if len(arm.body) == 1:
            body = self._format_stmt(arm.body[0])
            return f"{pat} => {body}"
        # Multi-statement arm
        lines = [f"{pat} =>"]
        for stmt in arm.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))
        return "\n".join(lines)

    def _format_comptime(self, expr: ComptimeExpr) -> str:
        lines = ["comptime"]
        for stmt in expr.body:
            lines.append(self._indent(self._format_stmt(stmt), 1))
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
            return pat.value
        if isinstance(pat, BindingPattern):
            return pat.name
        return "???"

    # ── Type expression formatting ─────────────────────────────

    def _format_type_expr(self, te: object) -> str:
        if isinstance(te, SimpleType):
            return te.name
        if isinstance(te, GenericType):
            args = ", ".join(self._format_type_expr(a) for a in te.args)
            return f"{te.name}<{args}>"
        if isinstance(te, ModifiedType):
            mods = " ".join(
                (f"{m.name}:{m.value}" if m.name else m.value)
                for m in te.modifiers
            )
            return f"{te.name}:[{mods}]"
        return "???"

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _indent(text: str, levels: int) -> str:
        prefix = "    " * levels
        return "\n".join(prefix + line if line else line for line in text.splitlines())

    @staticmethod
    def _indent_spaces(text: str, spaces: int) -> str:
        prefix = " " * spaces
        return "\n".join(prefix + line if line else line for line in text.splitlines())
