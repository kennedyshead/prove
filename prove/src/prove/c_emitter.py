"""Generate C source code from a checked Prove Module + SymbolTable."""

from __future__ import annotations

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryDef,
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
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    MainDef,
    MatchExpr,
    Module,
    ModuleDecl,
    PathLit,
    PipeExpr,
    ProofObligation,
    RawStringLit,
    RecordTypeDef,
    StringInterp,
    StringLit,
    TailContinue,
    TailLoop,
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
    resolve_type_vars,
    substitute_type_vars,
)

# Built-in functions that map directly to runtime calls
_BUILTIN_MAP: dict[str, str] = {
    "clamp": "prove_clamp",
}


class CEmitter:
    """Emit C source from a type-checked Prove module."""

    # Known foreign library → C header mapping
    _FOREIGN_HEADERS: dict[str, str] = {
        "libm": "math.h",
        "libpthread": "pthread.h",
        "libdl": "dlfcn.h",
        "librt": "time.h",
    }

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
        self._in_main = False
        self._in_tail_loop = False
        self._foreign_names: set[str] = set()
        self._foreign_libs: set[str] = set()
        self._current_requires: list[Expr] = []
        self._collect_foreign_info()

    def _collect_foreign_info(self) -> None:
        """Scan module for foreign blocks and collect function names + libraries."""
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                for fb in decl.foreign_blocks:
                    self._foreign_libs.add(fb.library)
                    for ff in fb.functions:
                        self._foreign_names.add(ff.name)

    def _all_type_defs(self) -> list[TypeDef]:
        """Collect all TypeDef nodes from ModuleDecl blocks."""
        result: list[TypeDef] = []
        for decl in self._module.declarations:
            if isinstance(decl, ModuleDecl):
                result.extend(decl.types)
        return result

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
        for td in self._all_type_defs():
            self._emit_type_def(td)

        # Forward declarations for user functions
        self._emit_function_forwards()

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
        # IO init_args is always called in main
        self._needed_headers.add("prove_input_output.h")

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

        # Check if HOF functions are used (map/filter/reduce)
        self._scan_for_hof(self._module)

    def _scan_for_hof(self, module: Module) -> None:
        """Pre-scan AST for map/filter/reduce calls to include prove_hof.h."""
        _hof_names = {"map", "filter", "reduce", "each"}

        def _scan_expr(expr: Expr) -> bool:
            if isinstance(expr, CallExpr):
                if isinstance(expr.func, IdentifierExpr) and expr.func.name in _hof_names:
                    return True
                for a in expr.args:
                    if _scan_expr(a):
                        return True
            elif isinstance(expr, BinaryExpr):
                return _scan_expr(expr.left) or _scan_expr(expr.right)
            elif isinstance(expr, PipeExpr):
                return _scan_expr(expr.left) or _scan_expr(expr.right)
            return False

        def _scan_stmts(stmts: list) -> bool:
            for s in stmts:
                if isinstance(s, ExprStmt) and _scan_expr(s.expr):
                    return True
                if isinstance(s, VarDecl) and _scan_expr(s.value):
                    return True
            return False

        for decl in module.declarations:
            if isinstance(decl, (FunctionDef, MainDef)):
                if _scan_stmts(decl.body):
                    self._needed_headers.add("prove_hof.h")
                    return

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
        self._line("#include <stdio.h>")
        # Foreign library headers
        for lib in sorted(self._foreign_libs):
            header = self._FOREIGN_HEADERS.get(lib)
            if header:
                self._line(f"#include <{header}>")
        for h in sorted(self._needed_headers):
            self._line(f'#include "{h}"')

    # ── Type forward declarations ──────────────────────────────

    def _emit_type_forwards(self) -> None:
        for td in self._all_type_defs():
            cname = mangle_type_name(td.name)
            self._line(f"typedef struct {cname} {cname};")
        self._line("")

    def _emit_function_forwards(self) -> None:
        """Emit forward declarations for all user-defined functions."""
        any_emitted = False
        for decl in self._module.declarations:
            if not isinstance(decl, FunctionDef) or decl.binary:
                continue
            sig = self._symbols.resolve_function(
                decl.verb, decl.name, len(decl.params),
            )
            if not sig:
                continue
            ret_ct = map_type(sig.return_type)
            ret_decl = ret_ct.decl
            if decl.can_fail:
                if (isinstance(sig.return_type, GenericInstance)
                        and sig.return_type.base_name == "Result"):
                    ret_decl = "Prove_Result"
                elif ret_ct.decl == "void":
                    ret_decl = "Prove_Result"
            mangled = mangle_name(
                decl.verb, decl.name, sig.param_types,
            )
            params: list[str] = []
            for p, pt in zip(decl.params, sig.param_types):
                ct = map_type(pt)
                params.append(f"{ct.decl} {p.name}")
            param_str = ", ".join(params) if params else "void"
            self._line(f"{ret_decl} {mangled}({param_str});")
            any_emitted = True
        if any_emitted:
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

        elif isinstance(body, BinaryDef):
            # Opaque pointer typedef for C-backed types
            self._line(f"typedef struct {cname}_impl* {cname};")
            self._line("")

    # ── Function emission ──────────────────────────────────────

    def _emit_function(self, fd: FunctionDef) -> None:
        # Binary functions are C-backed — no Prove body to emit
        if fd.binary:
            return

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
        self._current_requires = fd.requires

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

        # Emit assume assertions at function entry
        for assume_expr in fd.assume:
            cond = self._emit_expr(assume_expr)
            self._line(f'if (!({cond})) prove_panic("assumption violated");')

        # Check if proof block has structured conditions (when)
        has_proof_conditions = (
            fd.proof is not None
            and any(obl.condition is not None for obl in fd.proof.obligations)
        )

        if has_proof_conditions:
            self._emit_proof_branches(fd, ret_type)
        else:
            # Emit body
            self._emit_body(fd.body, ret_type, is_failable=fd.can_fail)

        self._indent -= 1
        self._line("}")
        self._line("")

    def _emit_proof_branches(self, fd: FunctionDef, ret_type: Type) -> None:
        """Emit if/else-if chains from proof obligations with `when` conditions.

        Obligations with conditions map to body expressions by order.
        An obligation without a condition becomes the else branch.
        """
        assert fd.proof is not None

        # Separate obligations with and without conditions
        cond_obls: list[tuple[ProofObligation, int]] = []
        default_idx: int | None = None
        for i, obl in enumerate(fd.proof.obligations):
            if obl.condition is not None:
                cond_obls.append((obl, i))
            else:
                default_idx = i

        is_unit = isinstance(ret_type, UnitType)

        # Each obligation maps to the body expression at the same index.
        # Body is a list of stmts — we use obligation index to pick the
        # corresponding body expression.
        body = fd.body

        first = True
        for obl, idx in cond_obls:
            assert obl.condition is not None
            cond = self._emit_expr(obl.condition)
            keyword = "if" if first else "else if"
            self._line(f"{keyword} (({cond})) {{")
            self._indent += 1
            if idx < len(body):
                stmt = body[idx]
                if is_unit:
                    self._emit_stmt(stmt)
                else:
                    expr = self._stmt_expr(stmt)
                    if expr is not None:
                        self._line(f"return {self._emit_expr(expr)};")
                    else:
                        self._emit_stmt(stmt)
            self._indent -= 1
            self._line("}")
            first = False

        # Default (else) branch — obligation without condition
        if default_idx is not None and default_idx < len(body):
            self._line("else {")
            self._indent += 1
            stmt = body[default_idx]
            if is_unit:
                self._emit_stmt(stmt)
            else:
                expr = self._stmt_expr(stmt)
                if expr is not None:
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(stmt)
            self._indent -= 1
            self._line("}")

    def _emit_main(self, md: MainDef) -> None:
        self._current_func_return = UNIT
        self._in_main = True
        self._locals.clear()
        self._current_requires = []

        self._line("int main(int argc, char **argv) {")
        self._indent += 1

        self._line("prove_runtime_init();")
        self._line("prove_io_init_args(argc, argv);")

        # Emit body statements
        for stmt in md.body:
            self._emit_stmt(stmt)

        self._line("prove_runtime_cleanup();")
        self._line("return 0;")
        self._indent -= 1
        self._line("}")
        self._line("")
        self._in_main = False

    # ── Requires-based option narrowing ─────────────────────────

    def _is_option_narrowed(
        self, func_name: str, args: list[Expr], module_name: str,
    ) -> bool:
        """Check if a call matches a requires validates precondition."""
        if not self._current_requires:
            return False
        # All call args must be identifiers
        call_arg_names: list[str] = []
        for a in args:
            if isinstance(a, IdentifierExpr):
                call_arg_names.append(a.name)
            else:
                return False
        call_key = frozenset(call_arg_names)
        for req_expr in self._current_requires:
            if not isinstance(req_expr, CallExpr):
                continue
            func = req_expr.func
            # Qualified: Table.has(...)
            if (isinstance(func, FieldExpr)
                    and isinstance(func.obj, TypeIdentifierExpr)):
                if func.obj.name != module_name:
                    continue
                req_name = func.field
            # Unqualified: has(...)
            elif isinstance(func, IdentifierExpr):
                req_name = func.name
            else:
                continue
            # Check the requires call resolves to a validates function
            n = len(req_expr.args)
            sig = self._symbols.resolve_function("validates", req_name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(req_name, arity=n)
            if sig is None or sig.verb != "validates":
                continue
            # For unqualified calls, verify the module matches
            if isinstance(func, IdentifierExpr):
                req_mod = sig.module
                if req_mod != module_name:
                    continue
            # All requires args must be identifiers matching our call args
            req_arg_names: list[str] = []
            all_idents = True
            for a in req_expr.args:
                if isinstance(a, IdentifierExpr):
                    req_arg_names.append(a.name)
                else:
                    all_idents = False
                    break
            if not all_idents:
                continue
            if frozenset(req_arg_names) == call_key:
                return True
        return False

    def _maybe_unwrap_option(
        self, call_str: str, sig, call_args: list[Expr],
        module_name: str,
    ) -> str:
        """If the call returns Option<V> and is narrowed by requires, unwrap."""
        from prove.symbols import FunctionSignature
        if not isinstance(sig, FunctionSignature):
            return call_str
        ret = sig.return_type
        if not (isinstance(ret, GenericInstance) and ret.base_name == "Option"
                and ret.args):
            return call_str
        if not self._is_option_narrowed(sig.name, call_args, module_name):
            return call_str
        # Resolve type variables against actual arg types
        actual_types = [self._infer_expr_type(a) for a in call_args]
        bindings = resolve_type_vars(sig.param_types, actual_types)
        inner = substitute_type_vars(ret.args[0], bindings)
        inner_ct = map_type(inner)
        return f"({inner_ct.decl}){call_str}.value"

    # ── Body emission ──────────────────────────────────────────

    def _emit_body(self, body: list, ret_type: Type, *, is_failable: bool = False) -> None:
        """Emit a function body. Last expression is the return value."""
        for i, stmt in enumerate(body):
            is_last = i == len(body) - 1
            # TailLoop handles its own returns internally
            if isinstance(stmt, TailLoop):
                self._emit_stmt(stmt)
                continue
            if is_last and not isinstance(stmt, VarDecl):
                # Last expression is the return value
                if isinstance(ret_type, UnitType) and not is_failable:
                    self._emit_stmt(stmt)
                    self._emit_releases(None)
                elif is_failable:
                    # For failable functions, wrap last in result_ok
                    self._emit_stmt(stmt)
                    self._emit_releases(None)
                    if isinstance(ret_type, GenericInstance) and ret_type.base_name == "Result":
                        self._line("return prove_result_ok();")
                else:
                    expr = self._stmt_expr(stmt)
                    if expr is not None:
                        ret_tmp = self._tmp()
                        ret_ct = map_type(ret_type)
                        self._line(f"{ret_ct.decl} {ret_tmp} = {self._emit_expr(expr)};")
                        self._emit_releases(ret_tmp)
                        self._line(f"return {ret_tmp};")
                    else:
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
            else:
                self._emit_stmt(stmt)

    def _emit_releases(self, skip_var: str | None) -> None:
        """Emit prove_release for all pointer locals except skip_var."""
        for name, ty in self._locals.items():
            if name == skip_var:
                continue
            ct = map_type(ty)
            if ct.is_pointer:
                self._line(f"prove_release({name});")

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
        elif isinstance(stmt, TailLoop):
            self._emit_tail_loop(stmt)
        elif isinstance(stmt, TailContinue):
            self._emit_tail_continue(stmt)
        elif isinstance(stmt, MatchExpr):
            self._emit_match_stmt(stmt)

    def _emit_var_decl(self, vd: VarDecl) -> None:
        ty = self._infer_expr_type(vd.value)
        self._locals[vd.name] = ty
        ct = map_type(ty)
        val = self._emit_expr(vd.value)
        self._line(f"{ct.decl} {vd.name} = {val};")
        # Retain pointer types
        if ct.is_pointer:
            self._line(f"prove_retain({vd.name});")

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

        # Save locals so match arm bindings don't leak to function scope
        saved_locals = dict(self._locals)
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
                    self._emit_match_arm_body(arm.body)
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
                elif isinstance(arm.pattern, WildcardPattern):
                    self._line("default: {")
                    self._indent += 1
                    self._emit_match_arm_body(arm.body)
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
            self._line("}")
        else:
            # Non-algebraic match — emit as if-else
            if self._in_tail_loop:
                self._emit_tail_match_as_if_else(m, subj)
            else:
                for arm in m.arms:
                    for s in arm.body:
                        self._emit_stmt(s)
        # Restore locals (match arm bindings are scoped to arms)
        self._locals = saved_locals

    def _emit_match_arm_body(self, body: list) -> None:  # type: ignore[type-arg]
        """Emit match arm body, handling TailContinue and returns in tail loop."""
        for i, s in enumerate(body):
            is_last = i == len(body) - 1
            if isinstance(s, TailContinue):
                self._emit_tail_continue(s)
            elif is_last and self._in_tail_loop and not isinstance(s, TailContinue):
                # Base case in tail loop — emit as return
                expr = self._stmt_expr(s)
                if expr is not None:
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(s)
            else:
                self._emit_stmt(s)

    def _emit_tail_match_as_if_else(self, m: MatchExpr, subj: str) -> None:
        """Emit a non-algebraic match as if/else inside a tail loop."""
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    subj_type = self._infer_expr_type(m.subject) if m.subject else UNIT
                    bct = map_type(subj_type)
                    self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, LiteralPattern):
                cond = self._emit_literal_cond(subj, arm.pattern)
                keyword = "if" if first else "} else if"
                self._line(f"{keyword} ({cond}) {{")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
            first = False
        # Close trailing if without else
        if m.arms and not isinstance(m.arms[-1].pattern, (WildcardPattern, BindingPattern)):
            self._line("}")

    # ── Tail call optimization emission ─────────────────────────

    def _emit_tail_loop(self, tl: TailLoop) -> None:
        """Emit a TCO-rewritten loop: while (1) { body }."""
        saved_in_tail = self._in_tail_loop
        self._in_tail_loop = True
        self._line("while (1) {")
        self._indent += 1
        for i, stmt in enumerate(tl.body):
            is_last = i == len(tl.body) - 1
            if is_last and not isinstance(stmt, (TailContinue, TailLoop, MatchExpr)):
                # Last statement is the return value (base case)
                expr = self._stmt_expr(stmt)
                if expr is not None:
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(stmt)
            else:
                self._emit_stmt(stmt)
        self._indent -= 1
        self._line("}")
        self._in_tail_loop = saved_in_tail

    def _emit_tail_continue(self, tc: TailContinue) -> None:
        """Emit temporaries for all new values, then assign + continue."""
        # First, evaluate all new values into temporaries
        # (avoids evaluation-order bugs when params depend on each other)
        tmps: list[tuple[str, str]] = []
        for param_name, new_val_expr in tc.assignments:
            tmp = self._tmp()
            ty = self._locals.get(param_name)
            ct = map_type(ty) if ty else CType("int64_t", False, None)
            val = self._emit_expr(new_val_expr)
            self._line(f"{ct.decl} {tmp} = {val};")
            tmps.append((param_name, tmp))
        # Then assign all at once
        for param_name, tmp in tmps:
            self._line(f"{param_name} = {tmp};")
        self._line("continue;")

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

        if isinstance(expr, PathLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, StringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, TripleStringLit):
            escaped = self._escape_c_string(expr.value)
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, RawStringLit):
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

            # Higher-order functions: map, filter, reduce
            if name == "map" and len(expr.args) == 2:
                return self._emit_hof_map(expr)
            if name == "each" and len(expr.args) == 2:
                return self._emit_hof_each(expr)
            if name == "filter" and len(expr.args) == 2:
                return self._emit_hof_filter(expr)
            if name == "reduce" and len(expr.args) == 3:
                return self._emit_hof_reduce(expr)

            # Builtin mapping
            if name in _BUILTIN_MAP:
                c_name = _BUILTIN_MAP[name]
                return f"{c_name}({', '.join(args)})"

            # Foreign (C FFI) functions — emit direct C call, no mangling
            if name in self._foreign_names:
                return f"{name}({', '.join(args)})"

            # Binary bridge: stdlib binary functions → C runtime
            n_args = len(expr.args)
            sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=n_args,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name
                pts = sig.param_types
                fpt = pts[0].name if pts and hasattr(pts[0], "name") else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str, sig, expr.args, sig.module,
                    )
                    return call_str

            # User function — resolve and mangle (re-resolve if needed)
            if sig is None:
                sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=n_args,
                )

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

        # Namespaced call: Module.function(args)
        if isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            module_name = expr.func.obj.name
            name = expr.func.field
            n_args = len(expr.args)
            sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=n_args,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name
                pts = sig.param_types
                fpt = pts[0].name if pts and hasattr(pts[0], "name") else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str, sig, expr.args, module_name,
                    )
                    return call_str
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                call_str = f"{mangled}({', '.join(args)})"
                call_str = self._maybe_unwrap_option(
                    call_str, sig, expr.args, module_name,
                )
                return call_str
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

    # ── Higher-order function emission ─────────────────────────

    def _emit_hof_map(self, expr: CallExpr) -> str:
        """Emit prove_list_map(list, fn, result_elem_size)."""
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        # Infer element type from the list
        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element

        # Emit lambda with correct types
        fn_name = self._emit_hof_lambda(expr.args[1], elem_type, "map")
        result_ct = map_type(elem_type)  # map result elem same type for now
        return f"prove_list_map({list_arg}, {fn_name}, sizeof({result_ct.decl}))"

    def _emit_hof_each(self, expr: CallExpr) -> str:
        """Emit each as inline loop (avoids closure issues)."""
        self._needed_headers.add("prove_list.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            idx = self._tmp()
            self._line(
                f"for (int64_t {idx} = 0;"
                f" {idx} < {list_arg}->length; {idx}++) {{"
            )
            self._indent += 1
            self._line(
                f"{elem_ct.decl} {param} ="
                f" *({elem_ct.decl}*)prove_list_get("
                f"{list_arg}, {idx});"
            )
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(lam.body)
            self._locals = saved_locals
            self._line(f"{body_code};")
            self._indent -= 1
            self._line("}")
            return "(void)0"
        # Non-lambda: fall back to prove_list_each
        self._needed_headers.add("prove_hof.h")
        fn_name = self._emit_hof_lambda(lam, elem_type, "each")
        return f"prove_list_each({list_arg}, {fn_name})"

    def _emit_hof_filter(self, expr: CallExpr) -> str:
        """Emit prove_list_filter(list, pred)."""
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element

        fn_name = self._emit_hof_lambda(expr.args[1], elem_type, "filter")
        return f"prove_list_filter({list_arg}, {fn_name})"

    def _emit_hof_reduce(self, expr: CallExpr) -> str:
        """Emit prove_list_reduce(list, &accum, fn)."""
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element

        accum_type = self._infer_expr_type(expr.args[1])
        accum_ct = map_type(accum_type)

        # Emit initial accumulator into a temp
        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[1])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        fn_name = self._emit_hof_lambda(
            expr.args[2], elem_type, "reduce", accum_type=accum_type,
        )
        self._line(f"prove_list_reduce({list_arg}, &{accum_tmp}, {fn_name});")
        return accum_tmp

    def _emit_hof_lambda(
        self, expr: Expr, elem_type: Type, kind: str,
        *, accum_type: Type | None = None,
    ) -> str:
        """Emit a lambda for HOF use with correct C signature."""
        if not isinstance(expr, LambdaExpr):
            # Not a lambda — assume it's an identifier referencing a function
            return self._emit_expr(expr)

        name = f"_lambda_{self._tmp_counter}"
        self._tmp_counter += 1
        elem_ct = map_type(elem_type)

        if kind == "map":
            # void *fn(const void *_arg)
            param = expr.params[0] if expr.params else "_x"
            # Save and set locals for lambda body
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static void *{name}(const void *_arg) {{\n"
                f"    {elem_ct.decl} {param} = *({elem_ct.decl}*)_arg;\n"
                f"    static {elem_ct.decl} _result;\n"
                f"    _result = {body_code};\n"
                f"    return &_result;\n"
                f"}}\n"
            )
        elif kind == "filter":
            # bool fn(const void *_arg)
            param = expr.params[0] if expr.params else "_x"
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static bool {name}(const void *_arg) {{\n"
                f"    {elem_ct.decl} {param} = *({elem_ct.decl}*)_arg;\n"
                f"    return {body_code};\n"
                f"}}\n"
            )
        elif kind == "reduce":
            # void fn(void *_accum, const void *_elem)
            accum_param = expr.params[0] if len(expr.params) > 0 else "_acc"
            elem_param = expr.params[1] if len(expr.params) > 1 else "_el"
            accum_ct = map_type(accum_type) if accum_type else elem_ct
            saved_locals = dict(self._locals)
            self._locals[accum_param] = accum_type if accum_type else elem_type
            self._locals[elem_param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static void {name}(void *_accum, const void *_elem) {{\n"
                f"    {accum_ct.decl} *{accum_param} = ({accum_ct.decl}*)_accum;\n"
                f"    {elem_ct.decl} {elem_param} = *({elem_ct.decl}*)_elem;\n"
                f"    *{accum_param} = {body_code};\n"
                f"}}\n"
            )
        elif kind == "each":
            # void fn(const void *_arg)
            param = expr.params[0] if expr.params else "_x"
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            lam = (
                f"static void {name}(const void *_arg) {{\n"
                f"    {elem_ct.decl} {param} = *({elem_ct.decl}*)_arg;\n"
                f"    {body_code};\n"
                f"}}\n"
            )
        else:
            return self._emit_expr(expr)

        self._lambdas.append(lam)
        return name

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
                sig = self._symbols.resolve_function_any(
                    name, arity=1,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name
                pts = sig.param_types
                fpt = pts[0].name if pts and hasattr(pts[0], "name") else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    return f"{c_name}({left})"
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
                sig = self._symbols.resolve_function_any(
                    name, arity=total,
                )
            if sig and sig.module:
                from prove.stdlib_loader import binary_c_name
                pts = sig.param_types
                fpt = pts[0].name if pts and hasattr(pts[0], "name") else None
                c_name = binary_c_name(sig.module, sig.verb, sig.name, fpt)
                if c_name:
                    return f"{c_name}({', '.join(all_args)})"
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
        if self._in_main:
            self._line(f"if (prove_result_is_err({tmp})) {{")
            self._indent += 1
            err_str = self._tmp()
            self._line(
                f"Prove_String *{err_str} ="
                f" (Prove_String*){tmp}.data;"
            )
            self._line(
                f"if ({err_str}) fprintf(stderr,"
                f" \"error: %.*s\\n\","
                f" (int){err_str}->length,"
                f" {err_str}->data);"
            )
            self._line("prove_runtime_cleanup();")
            self._line("return 1;")
            self._indent -= 1
            self._line("}")
        else:
            self._line(
                f"if (prove_result_is_err({tmp})) return {tmp};"
            )
        # Unwrap the success value
        inner_type = self._infer_expr_type(expr.expr)
        if isinstance(inner_type, GenericInstance) and inner_type.base_name == "Result":
            if inner_type.args:
                success_type = inner_type.args[0]
                sname = getattr(success_type, "name", "")
                if sname == "Integer":
                    return f"prove_result_unwrap_int({tmp})"
                # All pointer types: String, Value, etc.
                ct = map_type(success_type)
                if ct.is_pointer:
                    return f"({ct.decl})prove_result_unwrap_ptr({tmp})"
        return f"{tmp}"

    # ── Match expressions ──────────────────────────────────────

    def _emit_match_expr(self, m: MatchExpr) -> str:
        if m.subject is None:
            # No subject — just emit first arm body
            for arm in m.arms:
                for s in arm.body:
                    self._emit_stmt(s)
            return "/* match */"

        # Save locals so match arm bindings don't leak to function scope
        saved_locals = dict(self._locals)
        subj = self._emit_expr(m.subject)
        subj_type = self._infer_expr_type(m.subject)

        if not isinstance(subj_type, AlgebraicType):
            # Non-algebraic match: emit as if/else-if chain
            result_type = self._infer_match_result_type(m)
            ct = map_type(result_type)
            is_unit = isinstance(result_type, UnitType)
            tmp = "" if is_unit else self._tmp()
            if not is_unit:
                self._line(f"{ct.decl} {tmp};")

            first = True
            for arm in m.arms:
                if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                    # Default/else branch
                    if first:
                        self._line("{")
                    else:
                        self._line("} else {")
                    self._indent += 1
                    if isinstance(arm.pattern, BindingPattern):
                        bct = map_type(subj_type)
                        self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                        self._locals[arm.pattern.name] = subj_type
                    for i, s in enumerate(arm.body):
                        if not is_unit and i == len(arm.body) - 1:
                            e = self._stmt_expr(s)
                            if e is not None:
                                self._line(f"{tmp} = {self._emit_expr(e)};")
                            else:
                                self._emit_stmt(s)
                        else:
                            self._emit_stmt(s)
                    self._indent -= 1
                    self._line("}")
                elif isinstance(arm.pattern, LiteralPattern):
                    cond = self._emit_literal_cond(subj, arm.pattern)
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} ({cond}) {{")
                    self._indent += 1
                    for i, s in enumerate(arm.body):
                        if not is_unit and i == len(arm.body) - 1:
                            e = self._stmt_expr(s)
                            if e is not None:
                                self._line(f"{tmp} = {self._emit_expr(e)};")
                            else:
                                self._emit_stmt(s)
                        else:
                            self._emit_stmt(s)
                    self._indent -= 1
                first = False

            # Close trailing if without else
            if not isinstance(m.arms[-1].pattern, (WildcardPattern, BindingPattern)):
                self._line("}")

            self._locals = saved_locals
            return "/* match */" if is_unit else tmp

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
        # Restore locals (match arm bindings are scoped to arms)
        self._locals = saved_locals

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
        if isinstance(expr, (StringLit, TripleStringLit, StringInterp, PathLit)):
            return STRING
        if isinstance(expr, RawStringLit):
            return PrimitiveType("String", ("Reg",))
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
        n = len(expr.args)
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=n,
                )
            if sig:
                ret = sig.return_type
                if (sig.module and isinstance(ret, GenericInstance)
                        and ret.base_name == "Option" and ret.args
                        and self._is_option_narrowed(
                            name, expr.args, sig.module,
                        )):
                    actual_types = [
                        self._infer_expr_type(a) for a in expr.args
                    ]
                    bindings = resolve_type_vars(
                        sig.param_types, actual_types,
                    )
                    return substitute_type_vars(ret.args[0], bindings)
                return ret
        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=n,
                )
            if sig:
                return sig.return_type
            resolved = self._symbols.resolve_type(name)
            if resolved:
                return resolved
        if isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            module_name = expr.func.obj.name
            name = expr.func.field
            sig = self._symbols.resolve_function(None, name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=n,
                )
            if sig:
                ret = sig.return_type
                if (isinstance(ret, GenericInstance)
                        and ret.base_name == "Option" and ret.args
                        and self._is_option_narrowed(
                            name, expr.args, module_name,
                        )):
                    actual_types = [
                        self._infer_expr_type(a) for a in expr.args
                    ]
                    bindings = resolve_type_vars(
                        sig.param_types, actual_types,
                    )
                    return substitute_type_vars(ret.args[0], bindings)
                return ret
        return ERROR_TY

    def _infer_pipe_type(self, expr: PipeExpr) -> Type:
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=1,
                )
            if sig:
                return sig.return_type
        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name, arity=total,
                )
            if sig:
                return sig.return_type
        return ERROR_TY

    def _emit_literal_cond(self, subj: str, pat: LiteralPattern) -> str:
        """Generate a C condition comparing subj to a literal pattern."""
        val = pat.value
        if val in ("true", "false"):
            return subj if val == "true" else f"!({subj})"
        if val.startswith('"'):
            escaped = self._escape_c_string(val[1:-1])
            return f'prove_string_eq({subj}, "{escaped}")'
        return f"{subj} == {val}L"

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
