"""Generate C source code from a checked Prove Module + SymbolTable."""

from __future__ import annotations

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    DecimalLit,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    IfExpr,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    MainDef,
    MatchExpr,
    Module,
    PipeExpr,
    RecordTypeDef,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    VarDecl,
    VariantPattern,
    WildcardPattern,
)
from prove.c_types import CType, mangle_name, mangle_type_name, map_type
from prove.symbols import SymbolTable
from prove.types import (
    BOOLEAN,
    DECIMAL,
    ERROR_TY,
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    Type,
    UnitType,
)

# Built-in functions that map directly to runtime calls
_BUILTIN_MAP: dict[str, str] = {
    "println": "prove_println",
    "print": "prove_print",
    "readln": "prove_readln",
    "clamp": "prove_clamp",
}


class CEmitter:
    """Emit C source from a type-checked Prove module."""

    def __init__(self, module: Module, symbols: SymbolTable) -> None:
        self._module = module
        self._symbols = symbols
        self._out: list[str] = []
        self._indent = 0
        self._tmp_counter = 0
        self._lambdas: list[str] = []  # hoisted lambda definitions
        self._locals: dict[str, Type] = {}  # local var -> type for inference
        self._needed_headers: set[str] = set()
        self._current_func_return: Type = UNIT

    # ── Public API ─────────────────────────────────────────────

    def emit(self) -> str:
        """Generate the complete C source for the module."""
        # Collect what we need first (dry run for headers)
        self._collect_needed_headers()

        # Emit includes
        self._emit_includes()
        self._line("")

        # Forward declarations for types
        self._emit_type_forwards()

        # Type definitions
        for decl in self._module.declarations:
            if isinstance(decl, TypeDef):
                self._emit_type_def(decl)

        # Hoisted lambdas will be inserted here (placeholder position)
        lambda_pos = len(self._out)

        # Function definitions
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                self._emit_function(decl)

        # Main
        for decl in self._module.declarations:
            if isinstance(decl, MainDef):
                self._emit_main(decl)
                break

        # Insert hoisted lambdas before functions
        if self._lambdas:
            for lam in reversed(self._lambdas):
                self._out.insert(lambda_pos, lam)

        return "\n".join(self._out) + "\n"

    # ── Header collection ──────────────────────────────────────

    def _collect_needed_headers(self) -> None:
        """Pre-scan to determine which runtime headers are needed."""
        # Always include the base runtime
        self._needed_headers.add("prove_runtime.h")
        # The hello world always needs strings
        self._needed_headers.add("prove_string.h")

        # Scan function signatures and types for what we need
        for (_verb, _name), sigs in self._symbols.all_functions().items():
            for sig in sigs:
                for pt in sig.param_types:
                    ct = map_type(pt)
                    if ct.header:
                        self._needed_headers.add(ct.header)
                ct = map_type(sig.return_type)
                if ct.header:
                    self._needed_headers.add(ct.header)

    # ── Output helpers ─────────────────────────────────────────

    def _line(self, text: str) -> None:
        if text:
            self._out.append("    " * self._indent + text)
        else:
            self._out.append("")

    def _tmp(self) -> str:
        self._tmp_counter += 1
        return f"_tmp{self._tmp_counter}"

    # ── Includes ───────────────────────────────────────────────

    def _emit_includes(self) -> None:
        self._line("#include <stdint.h>")
        self._line("#include <stdbool.h>")
        self._line("#include <stdlib.h>")
        for h in sorted(self._needed_headers):
            self._line(f'#include "{h}"')

    # ── Type forward declarations ──────────────────────────────

    def _emit_type_forwards(self) -> None:
        for decl in self._module.declarations:
            if isinstance(decl, TypeDef):
                cname = mangle_type_name(decl.name)
                self._line(f"typedef struct {cname} {cname};")
        self._line("")

    # ── Type definitions ───────────────────────────────────────

    def _emit_type_def(self, td: TypeDef) -> None:
        cname = mangle_type_name(td.name)
        body = td.body

        if isinstance(body, RecordTypeDef):
            self._line(f"struct {cname} {{")
            self._indent += 1
            for f in body.fields:
                te_name = f.type_expr.name if hasattr(f.type_expr, 'name') else "Integer"
                ft = self._symbols.resolve_type(te_name)
                ct = map_type(ft) if ft else CType("int64_t", False, None)
                self._line(f"{ct.decl} {f.name};")
            self._indent -= 1
            self._line("};")
            self._line("")

        elif isinstance(body, AlgebraicTypeDef):
            # Tag enum
            self._line("enum {")
            self._indent += 1
            for i, v in enumerate(body.variants):
                tag = f"{cname}_TAG_{v.name.upper()}"
                self._line(f"{tag} = {i},")
            self._indent -= 1
            self._line("};")
            self._line("")

            # Tagged union struct
            self._line(f"struct {cname} {{")
            self._indent += 1
            self._line("uint8_t tag;")
            self._line("union {")
            self._indent += 1
            for v in body.variants:
                if v.fields:
                    self._line("struct {")
                    self._indent += 1
                    for f in v.fields:
                        ft = self._symbols.resolve_type(
                            f.type_expr.name if hasattr(f.type_expr, 'name') else "Integer"
                        )
                        ct = map_type(ft) if ft else CType("int64_t", False, None)
                        self._line(f"{ct.decl} {f.name};")
                    self._indent -= 1
                    self._line(f"}} {v.name};")
                else:
                    self._line(f"uint8_t _{v.name};  /* unit variant */")
            self._indent -= 1
            self._line("};")
            self._indent -= 1
            self._line("};")
            self._line("")

            # Constructor functions for each variant
            for i, v in enumerate(body.variants):
                tag = f"{cname}_TAG_{v.name.upper()}"
                params: list[str] = []
                for f in v.fields:
                    ft = self._symbols.resolve_type(
                        f.type_expr.name if hasattr(f.type_expr, 'name') else "Integer"
                    )
                    ct = map_type(ft) if ft else CType("int64_t", False, None)
                    params.append(f"{ct.decl} {f.name}")
                param_str = ", ".join(params) if params else "void"
                self._line(f"static inline {cname} {v.name}({param_str}) {{")
                self._indent += 1
                self._line(f"{cname} _v;")
                self._line(f"_v.tag = {tag};")
                for f in v.fields:
                    self._line(f"_v.{v.name}.{f.name} = {f.name};")
                self._line("return _v;")
                self._indent -= 1
                self._line("}")
                self._line("")

    # ── Function emission ──────────────────────────────────────

    def _emit_function(self, fd: FunctionDef) -> None:
        # Resolve types
        param_types: list[Type] = []
        for p in fd.params:
            sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
            if sig:
                idx = next((i for i, n in enumerate(sig.param_names) if n == p.name), None)
                if idx is not None and idx < len(sig.param_types):
                    param_types.append(sig.param_types[idx])
                    continue
            param_types.append(INTEGER)

        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        ret_type = sig.return_type if sig else UNIT
        self._current_func_return = ret_type

        # Map to C types
        ret_ct = map_type(ret_type)
        ret_decl = ret_ct.decl

        # For failable functions returning Result, the C return is Prove_Result
        if fd.can_fail:
            if isinstance(ret_type, GenericInstance) and ret_type.base_name == "Result":
                ret_decl = "Prove_Result"
            elif ret_ct.decl == "void":
                ret_decl = "Prove_Result"

        mangled = mangle_name(fd.verb, fd.name, param_types)

        params: list[str] = []
        for p, pt in zip(fd.params, param_types):
            ct = map_type(pt)
            params.append(f"{ct.decl} {p.name}")
        param_str = ", ".join(params) if params else "void"

        self._line(f"{ret_decl} {mangled}({param_str}) {{")
        self._indent += 1

        # Reset locals
        self._locals.clear()
        for p, pt in zip(fd.params, param_types):
            self._locals[p.name] = pt

        # Emit body
        self._emit_body(fd.body, ret_type, is_failable=fd.can_fail)

        self._indent -= 1
        self._line("}")
        self._line("")

    def _emit_main(self, md: MainDef) -> None:
        self._current_func_return = UNIT
        self._locals.clear()

        self._line("int main(int argc, char **argv) {")
        self._indent += 1

        # Emit body statements
        for stmt in md.body:
            self._emit_stmt(stmt)

        self._line("return 0;")
        self._indent -= 1
        self._line("}")
        self._line("")

    # ── Body emission ──────────────────────────────────────────

    def _emit_body(self, body: list, ret_type: Type, *, is_failable: bool = False) -> None:
        """Emit a function body. Last expression is the return value."""
        for i, stmt in enumerate(body):
            is_last = i == len(body) - 1
            if is_last and not isinstance(stmt, VarDecl):
                # Last expression is the return value
                if isinstance(ret_type, UnitType) and not is_failable:
                    self._emit_stmt(stmt)
                elif is_failable:
                    # For failable functions, wrap last in result_ok
                    self._emit_stmt(stmt)
                    if isinstance(ret_type, GenericInstance) and ret_type.base_name == "Result":
                        self._line("return prove_result_ok();")
                else:
                    expr = self._stmt_expr(stmt)
                    if expr is not None:
                        self._line(f"return {self._emit_expr(expr)};")
                    else:
                        self._emit_stmt(stmt)
            else:
                self._emit_stmt(stmt)

    def _stmt_expr(self, stmt) -> Expr | None:
        """Extract the expression from a statement, if it is an ExprStmt."""
        if isinstance(stmt, ExprStmt):
            return stmt.expr
        if isinstance(stmt, MatchExpr):
            return stmt
        return None

    # ── Statement emission ─────────────────────────────────────

    def _emit_stmt(self, stmt) -> None:
        if isinstance(stmt, VarDecl):
            self._emit_var_decl(stmt)
        elif isinstance(stmt, Assignment):
            self._emit_assignment(stmt)
        elif isinstance(stmt, ExprStmt):
            self._emit_expr_stmt(stmt)
        elif isinstance(stmt, MatchExpr):
            self._emit_match_stmt(stmt)

    def _emit_var_decl(self, vd: VarDecl) -> None:
        ty = self._infer_expr_type(vd.value)
        self._locals[vd.name] = ty
        ct = map_type(ty)
        val = self._emit_expr(vd.value)
        self._line(f"{ct.decl} {vd.name} = {val};")

    def _emit_assignment(self, assign: Assignment) -> None:
        val = self._emit_expr(assign.value)
        self._line(f"{assign.target} = {val};")

    def _emit_expr_stmt(self, es: ExprStmt) -> None:
        val = self._emit_expr(es.expr)
        self._line(f"{val};")

    def _emit_match_stmt(self, m: MatchExpr) -> None:
        """Emit a match expression as a statement (switch)."""
        if m.subject is None:
            # Implicit match — emit as if-else chain
            for i, arm in enumerate(m.arms):
                for s in arm.body:
                    self._emit_stmt(s)
            return

        subj = self._emit_expr(m.subject)
        subj_type = self._infer_expr_type(m.subject)

        if isinstance(subj_type, AlgebraicType):
            tmp = self._tmp()
            ct = map_type(subj_type)
            self._line(f"{ct.decl} {tmp} = {subj};")
            self._line(f"switch ({tmp}.tag) {{")
            cname = mangle_type_name(subj_type.name)
            for arm in m.arms:
                if isinstance(arm.pattern, VariantPattern):
                    tag = f"{cname}_TAG_{arm.pattern.name.upper()}"
                    self._line(f"case {tag}: {{")
                    self._indent += 1
                    # Bind fields
                    variant_info = next(
                        (v for v in subj_type.variants if v.name == arm.pattern.name), None
                    )
                    if variant_info:
                        for i, sub_pat in enumerate(arm.pattern.fields):
                            if isinstance(sub_pat, BindingPattern):
                                field_names = list(variant_info.fields.keys())
                                if i < len(field_names):
                                    fname = field_names[i]
                                    ft = variant_info.fields[fname]
                                    fct = map_type(ft)
                                    self._locals[sub_pat.name] = ft
                                    self._line(
                                        f"{fct.decl} {sub_pat.name} = "
                                        f"{tmp}.{arm.pattern.name}.{fname};"
                                    )
                    for s in arm.body:
                        self._emit_stmt(s)
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
                elif isinstance(arm.pattern, WildcardPattern):
                    self._line("default: {")
                    self._indent += 1
                    for s in arm.body:
                        self._emit_stmt(s)
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
            self._line("}")
        else:
            # Non-algebraic match — emit as if-else
            for arm in m.arms:
                for s in arm.body:
                    self._emit_stmt(s)

    # ── Expression emission ────────────────────────────────────

    def _emit_expr(self, expr: Expr) -> str:
        if isinstance(expr, IntegerLit):
            return f"{expr.value}L"

        if isinstance(expr, DecimalLit):
            return expr.value

        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"

        if isinstance(expr, CharLit):
            return f"'{expr.value}'"

        if isinstance(expr, StringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, TripleStringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, StringInterp):
            return self._emit_string_interp(expr)

        if isinstance(expr, ListLiteral):
            return self._emit_list_literal(expr)

        if isinstance(expr, IdentifierExpr):
            return expr.name

        if isinstance(expr, TypeIdentifierExpr):
            return expr.name

        if isinstance(expr, BinaryExpr):
            return self._emit_binary(expr)

        if isinstance(expr, UnaryExpr):
            return self._emit_unary(expr)

        if isinstance(expr, CallExpr):
            return self._emit_call(expr)

        if isinstance(expr, FieldExpr):
            return self._emit_field(expr)

        if isinstance(expr, PipeExpr):
            return self._emit_pipe(expr)

        if isinstance(expr, FailPropExpr):
            return self._emit_fail_prop(expr)

        if isinstance(expr, IfExpr):
            return self._emit_if(expr)

        if isinstance(expr, MatchExpr):
            return self._emit_match_expr(expr)

        if isinstance(expr, LambdaExpr):
            return self._emit_lambda(expr)

        if isinstance(expr, IndexExpr):
            return self._emit_index(expr)

        return "/* unsupported expr */ 0"

    # ── Binary expressions ─────────────────────────────────────

    def _emit_binary(self, expr: BinaryExpr) -> str:
        left = self._emit_expr(expr.left)
        right = self._emit_expr(expr.right)

        # String concatenation
        if expr.op == "+":
            lt = self._infer_expr_type(expr.left)
            if isinstance(lt, PrimitiveType) and lt.name == "String":
                return f"prove_string_concat({left}, {right})"

        # String equality
        if expr.op == "==" or expr.op == "!=":
            lt = self._infer_expr_type(expr.left)
            if isinstance(lt, PrimitiveType) and lt.name == "String":
                eq = f"prove_string_eq({left}, {right})"
                return eq if expr.op == "==" else f"(!{eq})"

        # Map Prove operators to C
        op_map = {
            "&&": "&&", "||": "||",
            "==": "==", "!=": "!=",
            "<": "<", ">": ">", "<=": "<=", ">=": ">=",
            "+": "+", "-": "-", "*": "*", "/": "/", "%": "%",
        }
        c_op = op_map.get(expr.op, expr.op)
        return f"({left} {c_op} {right})"

    # ── Unary expressions ──────────────────────────────────────

    def _emit_unary(self, expr: UnaryExpr) -> str:
        operand = self._emit_expr(expr.operand)
        if expr.op == "!":
            return f"(!{operand})"
        if expr.op == "-":
            return f"(-{operand})"
        return operand

    # ── Call expressions ───────────────────────────────────────

    def _emit_call(self, expr: CallExpr) -> str:
        args = [self._emit_expr(a) for a in expr.args]

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Type-aware dispatch for to_string
            if name == "to_string" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                c_name = self._to_string_func(arg_type)
                return f"{c_name}({', '.join(args)})"

            # Type-aware dispatch for len
            if name == "len" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                if isinstance(arg_type, PrimitiveType) and arg_type.name == "String":
                    return f"prove_string_len({', '.join(args)})"
                return f"prove_list_len({', '.join(args)})"

            # Builtin mapping
            if name in _BUILTIN_MAP:
                c_name = _BUILTIN_MAP[name]
                return f"{c_name}({', '.join(args)})"

            # User function — resolve and mangle
            sig = self._symbols.resolve_function(None, name, len(expr.args))
            if sig is None:
                sig = self._symbols.resolve_function_any(name)

            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({', '.join(args)})"

            # Variant constructor or unknown — use name directly
            return f"{name}({', '.join(args)})"

        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            # Check if it's a variant constructor
            sig = self._symbols.resolve_function(None, name, len(expr.args))
            if sig:
                return f"{name}({', '.join(args)})"
            return f"{name}({', '.join(args)})"

        # Complex callable expression
        func = self._emit_expr(expr.func)
        return f"{func}({', '.join(args)})"

    def _to_string_func(self, ty: Type) -> str:
        """Pick the right prove_string_from_* function."""
        if isinstance(ty, PrimitiveType):
            if ty.name == "Integer":
                return "prove_string_from_int"
            if ty.name in ("Decimal", "Float"):
                return "prove_string_from_double"
            if ty.name == "Boolean":
                return "prove_string_from_bool"
            if ty.name == "Character":
                return "prove_string_from_char"
            if ty.name == "String":
                return ""  # identity — shouldn't happen
        return "prove_string_from_int"  # fallback

    # ── Field access ───────────────────────────────────────────

    def _emit_field(self, expr: FieldExpr) -> str:
        obj = self._emit_expr(expr.obj)
        obj_type = self._infer_expr_type(expr.obj)
        if isinstance(obj_type, (RecordType, AlgebraicType)):
            return f"{obj}.{expr.field}"
        # Pointer types use ->
        ct = map_type(obj_type)
        if ct.is_pointer:
            return f"{obj}->{expr.field}"
        return f"{obj}.{expr.field}"

    # ── Pipe expressions ───────────────────────────────────────

    def _emit_pipe(self, expr: PipeExpr) -> str:
        left = self._emit_expr(expr.left)

        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            if name in _BUILTIN_MAP:
                return f"{_BUILTIN_MAP[name]}({left})"
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(name)
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({left})"
            return f"{name}({left})"

        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            extra_args = [self._emit_expr(a) for a in expr.right.args]
            all_args = [left] + extra_args
            if name in _BUILTIN_MAP:
                return f"{_BUILTIN_MAP[name]}({', '.join(all_args)})"
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(name)
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({', '.join(all_args)})"
            return f"{name}({', '.join(all_args)})"

        right = self._emit_expr(expr.right)
        return f"{right}({left})"

    # ── Fail propagation ───────────────────────────────────────

    def _emit_fail_prop(self, expr: FailPropExpr) -> str:
        tmp = self._tmp()
        inner = self._emit_expr(expr.expr)
        self._line(f"Prove_Result {tmp} = {inner};")
        self._line(f"if (prove_result_is_err({tmp})) return {tmp};")
        # Use typed unwrap based on the inner result's success type
        inner_type = self._infer_expr_type(expr.expr)
        if isinstance(inner_type, GenericInstance) and inner_type.base_name == "Result":
            if inner_type.args:
                success_type = inner_type.args[0]
                if isinstance(success_type, PrimitiveType) and success_type.name == "Integer":
                    return f"prove_result_unwrap_int({tmp})"
                if isinstance(success_type, PrimitiveType) and success_type.name == "String":
                    return f"(Prove_String*)prove_result_unwrap_ptr({tmp})"
        return f"{tmp}"

    # ── If expressions ─────────────────────────────────────────

    def _emit_if(self, expr: IfExpr) -> str:
        cond = self._emit_expr(expr.condition)
        result_type = self._infer_if_type(expr)
        ct = map_type(result_type)

        if isinstance(result_type, UnitType):
            # Statement-level if
            self._line(f"if ({cond}) {{")
            self._indent += 1
            for s in expr.then_body:
                self._emit_stmt(s)
            self._indent -= 1
            if expr.else_body:
                self._line("} else {")
                self._indent += 1
                for s in expr.else_body:
                    self._emit_stmt(s)
                self._indent -= 1
            self._line("}")
            return "/* if */"

        # Expression-level if — use temp var
        tmp = self._tmp()
        self._line(f"{ct.decl} {tmp};")
        self._line(f"if ({cond}) {{")
        self._indent += 1
        for i, s in enumerate(expr.then_body):
            if i == len(expr.then_body) - 1:
                e = self._stmt_expr(s)
                if e is not None:
                    self._line(f"{tmp} = {self._emit_expr(e)};")
                else:
                    self._emit_stmt(s)
            else:
                self._emit_stmt(s)
        self._indent -= 1
        self._line("} else {")
        self._indent += 1
        for i, s in enumerate(expr.else_body):
            if i == len(expr.else_body) - 1:
                e = self._stmt_expr(s)
                if e is not None:
                    self._line(f"{tmp} = {self._emit_expr(e)};")
                else:
                    self._emit_stmt(s)
            else:
                self._emit_stmt(s)
        self._indent -= 1
        self._line("}")
        return tmp

    # ── Match expressions ──────────────────────────────────────

    def _emit_match_expr(self, m: MatchExpr) -> str:
        if m.subject is None:
            # No subject — just emit first arm body
            for arm in m.arms:
                for s in arm.body:
                    self._emit_stmt(s)
            return "/* match */"

        subj = self._emit_expr(m.subject)
        subj_type = self._infer_expr_type(m.subject)

        if not isinstance(subj_type, AlgebraicType):
            # Non-algebraic: emit as first arm
            for arm in m.arms:
                for s in arm.body:
                    self._emit_stmt(s)
            return "/* match */"

        # Tagged union switch
        result_type = self._infer_match_result_type(m)
        ct = map_type(result_type)
        result_tmp = self._tmp()
        subj_tmp = self._tmp()
        sct = map_type(subj_type)
        cname = mangle_type_name(subj_type.name)

        if not isinstance(result_type, UnitType):
            self._line(f"{ct.decl} {result_tmp};")
        self._line(f"{sct.decl} {subj_tmp} = {subj};")
        self._line(f"switch ({subj_tmp}.tag) {{")

        for arm in m.arms:
            if isinstance(arm.pattern, VariantPattern):
                tag = f"{cname}_TAG_{arm.pattern.name.upper()}"
                self._line(f"case {tag}: {{")
                self._indent += 1
                variant_info = next(
                    (v for v in subj_type.variants if v.name == arm.pattern.name), None
                )
                if variant_info:
                    for i, sub_pat in enumerate(arm.pattern.fields):
                        if isinstance(sub_pat, BindingPattern):
                            field_names = list(variant_info.fields.keys())
                            if i < len(field_names):
                                fname = field_names[i]
                                ft = variant_info.fields[fname]
                                fct = map_type(ft)
                                self._locals[sub_pat.name] = ft
                                self._line(
                                    f"{fct.decl} {sub_pat.name} = "
                                    f"{subj_tmp}.{arm.pattern.name}.{fname};"
                                )
                for j, s in enumerate(arm.body):
                    if j == len(arm.body) - 1 and not isinstance(result_type, UnitType):
                        e = self._stmt_expr(s)
                        if e is not None:
                            self._line(f"{result_tmp} = {self._emit_expr(e)};")
                        else:
                            self._emit_stmt(s)
                    else:
                        self._emit_stmt(s)
                self._line("break;")
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                self._line("default: {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    self._locals[arm.pattern.name] = subj_type
                    self._line(f"{sct.decl} {arm.pattern.name} = {subj_tmp};")
                for j, s in enumerate(arm.body):
                    if j == len(arm.body) - 1 and not isinstance(result_type, UnitType):
                        e = self._stmt_expr(s)
                        if e is not None:
                            self._line(f"{result_tmp} = {self._emit_expr(e)};")
                        else:
                            self._emit_stmt(s)
                    else:
                        self._emit_stmt(s)
                self._line("break;")
                self._indent -= 1
                self._line("}")
        self._line("}")

        return result_tmp if not isinstance(result_type, UnitType) else "/* match */"

    def _infer_match_result_type(self, m: MatchExpr) -> Type:
        """Infer the result type of a match expression."""
        for arm in m.arms:
            if arm.body:
                last = arm.body[-1]
                if isinstance(last, ExprStmt):
                    return self._infer_expr_type(last.expr)
        return UNIT

    # ── Lambda expressions ─────────────────────────────────────

    def _emit_lambda(self, expr: LambdaExpr) -> str:
        # Hoist as a static function
        name = f"_lambda_{self._tmp_counter}"
        self._tmp_counter += 1

        # We don't know param types precisely, so use generic approach
        params = ", ".join(f"int64_t {p}" for p in expr.params)
        if not params:
            params = "void"

        body_code = self._emit_expr(expr.body)

        lam = f"static int64_t {name}({params}) {{\n    return {body_code};\n}}\n"
        self._lambdas.append(lam)
        return name

    # ── String interpolation ───────────────────────────────────

    def _emit_string_interp(self, expr: StringInterp) -> str:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, StringLit):
                escaped = self._escape_c_string(part.value)
                parts.append(f'prove_string_from_cstr("{escaped}")')
            else:
                part_type = self._infer_expr_type(part)
                val = self._emit_expr(part)
                if isinstance(part_type, PrimitiveType) and part_type.name == "String":
                    parts.append(val)
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Integer":
                    parts.append(f"prove_string_from_int({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name in (
                    "Decimal", "Float",
                ):
                    parts.append(f"prove_string_from_double({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Boolean":
                    parts.append(f"prove_string_from_bool({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Character":
                    parts.append(f"prove_string_from_char({val})")
                else:
                    parts.append(f"prove_string_from_int({val})")

        if not parts:
            return 'prove_string_from_cstr("")'
        result = parts[0]
        for p in parts[1:]:
            result = f"prove_string_concat({result}, {p})"
        return result

    # ── List literal ───────────────────────────────────────────

    def _emit_list_literal(self, expr: ListLiteral) -> str:
        if not expr.elements:
            return "prove_list_new(sizeof(int64_t), 4)"
        # Determine element type
        elem_type = self._infer_expr_type(expr.elements[0])
        ct = map_type(elem_type)

        tmp = self._tmp()
        self._line(f"Prove_List *{tmp} = prove_list_new(sizeof({ct.decl}), {len(expr.elements)});")
        for elem in expr.elements:
            val = self._emit_expr(elem)
            etmp = self._tmp()
            self._line(f"{ct.decl} {etmp} = {val};")
            self._line(f"prove_list_push(&{tmp}, &{etmp});")
        return tmp

    # ── Index expression ───────────────────────────────────────

    def _emit_index(self, expr: IndexExpr) -> str:
        obj = self._emit_expr(expr.obj)
        idx = self._emit_expr(expr.index)
        obj_type = self._infer_expr_type(expr.obj)
        if isinstance(obj_type, ListType):
            elem_ct = map_type(obj_type.element)
            return f"(*({elem_ct.decl}*)prove_list_get({obj}, {idx}))"
        return f"{obj}[{idx}]"

    # ── Type inference (lightweight) ───────────────────────────

    def _infer_expr_type(self, expr: Expr) -> Type:
        """Lightweight type inference mirroring the checker."""
        if isinstance(expr, IntegerLit):
            return INTEGER
        if isinstance(expr, DecimalLit):
            return DECIMAL
        if isinstance(expr, (StringLit, TripleStringLit, StringInterp)):
            return STRING
        if isinstance(expr, BooleanLit):
            return BOOLEAN
        if isinstance(expr, CharLit):
            return PrimitiveType("Character")

        if isinstance(expr, IdentifierExpr):
            # Check locals first
            if expr.name in self._locals:
                return self._locals[expr.name]
            sym = self._symbols.lookup(expr.name)
            if sym:
                return sym.resolved_type
            return ERROR_TY

        if isinstance(expr, TypeIdentifierExpr):
            resolved = self._symbols.resolve_type(expr.name)
            if resolved:
                return resolved
            return ERROR_TY

        if isinstance(expr, BinaryExpr):
            if expr.op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||"):
                return BOOLEAN
            left_ty = self._infer_expr_type(expr.left)
            return left_ty

        if isinstance(expr, UnaryExpr):
            if expr.op == "!":
                return BOOLEAN
            return self._infer_expr_type(expr.operand)

        if isinstance(expr, CallExpr):
            return self._infer_call_type(expr)

        if isinstance(expr, FieldExpr):
            obj_type = self._infer_expr_type(expr.obj)
            if isinstance(obj_type, RecordType):
                ft = obj_type.fields.get(expr.field)
                if ft:
                    return ft
            return ERROR_TY

        if isinstance(expr, PipeExpr):
            return self._infer_pipe_type(expr)

        if isinstance(expr, FailPropExpr):
            inner = self._infer_expr_type(expr.expr)
            if isinstance(inner, GenericInstance) and inner.base_name == "Result":
                if inner.args:
                    return inner.args[0]
            return ERROR_TY

        if isinstance(expr, IfExpr):
            return self._infer_if_type(expr)

        if isinstance(expr, MatchExpr):
            return self._infer_match_result_type(expr)

        if isinstance(expr, ListLiteral):
            if expr.elements:
                return ListType(self._infer_expr_type(expr.elements[0]))
            return ListType(INTEGER)

        if isinstance(expr, LambdaExpr):
            return FunctionType([], UNIT)

        if isinstance(expr, IndexExpr):
            obj_type = self._infer_expr_type(expr.obj)
            if isinstance(obj_type, ListType):
                return obj_type.element
            return ERROR_TY

        return ERROR_TY

    def _infer_call_type(self, expr: CallExpr) -> Type:
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
            sig = self._symbols.resolve_function(None, name, len(expr.args))
            if sig is None:
                sig = self._symbols.resolve_function_any(name)
            if sig:
                return sig.return_type
        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            sig = self._symbols.resolve_function(None, name, len(expr.args))
            if sig is None:
                sig = self._symbols.resolve_function_any(name)
            if sig:
                return sig.return_type
            resolved = self._symbols.resolve_type(name)
            if resolved:
                return resolved
        return ERROR_TY

    def _infer_pipe_type(self, expr: PipeExpr) -> Type:
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(name)
            if sig:
                return sig.return_type
        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(name)
            if sig:
                return sig.return_type
        return ERROR_TY

    def _infer_if_type(self, expr: IfExpr) -> Type:
        if expr.then_body:
            last = expr.then_body[-1]
            if isinstance(last, ExprStmt):
                return self._infer_expr_type(last.expr)
        return UNIT

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _escape_c_string(s: str) -> str:
        """Escape a string for C source."""
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
