"""Generate x86-64 assembly from a checked Prove Module + SymbolTable.

Mirrors the CEmitter interface: emit() -> str.
"""

from __future__ import annotations

from collections.abc import Sequence

from prove.asm_x86_64 import X86_64Codegen
from prove.ast_nodes import (
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
    Stmt,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeIdentifierExpr,
    UnaryExpr,
    VarDecl,
    WildcardPattern,
)
from prove.c_types import mangle_name
from prove.symbols import SymbolTable
from prove.types import (
    INTEGER,
    UNIT,
    Type,
    UnitType,
)

# Builtin functions that map to C runtime symbols
_BUILTIN_MAP: dict[str, str] = {
    "println": "prove_println",
    "print": "prove_print",
    "readln": "prove_readln",
    "clamp": "prove_clamp",
    "to_string": "prove_string_from_int",
    "len": "prove_list_len",
}


class AsmEmitter:
    """Emit x86-64 assembly from a type-checked Prove module."""

    def __init__(self, module: Module, symbols: SymbolTable) -> None:
        self._module = module
        self._symbols = symbols
        self._cg = X86_64Codegen()
        self._str_counter = 0
        self._locals: dict[str, int] = {}  # name -> stack offset
        self._stack_offset = 0
        self._current_func_return: Type = UNIT

    def emit(self) -> str:
        """Generate the complete assembly source for the module."""
        self._cg.emit_text_section()
        self._cg._raw("")

        # Emit function definitions
        for decl in self._module.declarations:
            if isinstance(decl, FunctionDef):
                self._emit_function(decl)
            elif isinstance(decl, ModuleDecl):
                for fn in decl.body:
                    if isinstance(fn, FunctionDef):
                        self._emit_function(fn)

        # Emit main
        for decl in self._module.declarations:
            if isinstance(decl, MainDef):
                self._emit_main(decl)
                break
            if isinstance(decl, ModuleDecl):
                for fn in decl.body:
                    if isinstance(fn, MainDef):
                        self._emit_main(fn)
                        break

        # Emit data section
        self._cg.emit_data_section()

        return self._cg.output()

    # ── Function emission ─────────────────────────────────────

    def _emit_function(self, fd: FunctionDef) -> None:
        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        param_types = sig.param_types if sig else [INTEGER] * len(fd.params)
        ret_type = sig.return_type if sig else UNIT
        self._current_func_return = ret_type

        mangled = mangle_name(fd.verb, fd.name, param_types)

        # Calculate stack: each param + each local gets 8 bytes
        # Start conservatively: params + some room
        max_locals = len(fd.params) + len(fd.body) * 2 + 8
        stack_size = max_locals * 8

        self._cg.emit_global(mangled)
        self._cg.emit_prologue(mangled, stack_size)

        # Reset locals
        self._locals.clear()
        self._stack_offset = 0

        # Store incoming arguments to local stack slots
        for i, p in enumerate(fd.params):
            offset = self._alloc_local(p.name)
            self._cg.emit_store_arg_to_local(i, offset)

        # Check for proof conditions
        has_proof_conditions = (
            fd.proof is not None
            and any(obl.condition is not None for obl in fd.proof.obligations)
        )

        if has_proof_conditions:
            self._emit_proof_branches(fd, ret_type)
        else:
            self._emit_body(fd.body, ret_type)

        self._cg._raw("")

    def _emit_main(self, md: MainDef) -> None:
        self._current_func_return = UNIT
        self._locals.clear()
        self._stack_offset = 0

        stack_size = (len(md.body) * 2 + 8) * 8
        self._cg.emit_global("main")
        self._cg.emit_prologue("main", stack_size)

        for stmt in md.body:
            self._emit_stmt(stmt)

        # return 0
        self._cg.emit_load_imm(0)
        self._cg.emit_epilogue()
        self._cg._raw("")

    # ── Stack management ──────────────────────────────────────

    def _alloc_local(self, name: str) -> int:
        """Allocate an 8-byte stack slot for a local variable. Returns offset."""
        self._stack_offset -= 8
        self._locals[name] = self._stack_offset
        return self._stack_offset

    # ── Body emission ─────────────────────────────────────────

    def _emit_body(self, body: Sequence[Stmt | MatchExpr], ret_type: Type) -> None:
        """Emit function body. Last expression is return value."""
        for i, stmt in enumerate(body):
            is_last = i == len(body) - 1
            self._emit_stmt(stmt)
            if is_last and not isinstance(ret_type, UnitType):
                # rax has the last expression value
                self._cg.emit_epilogue()

        if isinstance(ret_type, UnitType):
            self._cg.emit_epilogue()

    def _emit_proof_branches(self, fd: FunctionDef, ret_type: Type) -> None:
        """Emit if/else-if chains from proof obligations with conditions."""
        assert fd.proof is not None

        cond_obls: list[tuple[ProofObligation, int]] = []
        default_idx: int | None = None
        for i, obl in enumerate(fd.proof.obligations):
            if obl.condition is not None:
                cond_obls.append((obl, i))
            else:
                default_idx = i

        body = fd.body

        for j, (obl, idx) in enumerate(cond_obls):
            assert obl.condition is not None
            next_label = self._cg.new_label(".Lnext")
            self._emit_expr(obl.condition)
            self._cg.emit_branch_if_zero(next_label)
            # Emit the body expression at this index
            if idx < len(body):
                self._emit_stmt(body[idx])
            self._cg.emit_epilogue()
            self._cg._label(next_label)

        # Default branch
        if default_idx is not None and default_idx < len(body):
            self._emit_stmt(body[default_idx])
            self._cg.emit_epilogue()
        else:
            # No default — just epilogue with whatever's in rax
            self._cg.emit_epilogue()

    # ── Statement emission ────────────────────────────────────

    def _emit_stmt(self, stmt: object) -> None:
        if isinstance(stmt, VarDecl):
            self._emit_var_decl(stmt)
        elif isinstance(stmt, Assignment):
            self._emit_assignment(stmt)
        elif isinstance(stmt, ExprStmt):
            self._emit_expr(stmt.expr)
        elif isinstance(stmt, MatchExpr):
            self._emit_expr(stmt)

    def _emit_var_decl(self, vd: VarDecl) -> None:
        self._emit_expr(vd.value)
        offset = self._alloc_local(vd.name)
        self._cg.emit_store_local(offset)

    def _emit_assignment(self, assign: Assignment) -> None:
        self._emit_expr(assign.value)
        offset = self._locals.get(assign.target)
        if offset is not None:
            self._cg.emit_store_local(offset)

    # ── Expression emission ───────────────────────────────────

    def _emit_expr(self, expr: Expr) -> None:
        """Emit code for an expression, leaving result in %rax."""
        if isinstance(expr, IntegerLit):
            self._cg.emit_load_imm(int(expr.value))

        elif isinstance(expr, BooleanLit):
            self._cg.emit_load_imm(1 if expr.value else 0)

        elif isinstance(expr, CharLit):
            self._cg.emit_load_imm(ord(expr.value[0]) if expr.value else 0)

        elif isinstance(expr, (StringLit, TripleStringLit, RawStringLit, PathLit)):
            value = expr.value
            label = self._add_string(value)
            self._cg.emit_load_string(label)
            self._cg.emit_call("prove_string_from_cstr", 1)

        elif isinstance(expr, DecimalLit):
            # Decimal literals need special handling (xmm registers)
            # For now, truncate to integer
            self._cg.emit_load_imm(int(float(expr.value)))

        elif isinstance(expr, IdentifierExpr):
            offset = self._locals.get(expr.name)
            if offset is not None:
                self._cg.emit_load_local(offset)
            else:
                # Try as a global or constant
                self._cg._comment(f"identifier: {expr.name}")
                self._cg.emit_load_imm(0)

        elif isinstance(expr, BinaryExpr):
            self._emit_binary(expr)

        elif isinstance(expr, UnaryExpr):
            self._emit_unary(expr)

        elif isinstance(expr, CallExpr):
            self._emit_call(expr)

        elif isinstance(expr, PipeExpr):
            self._emit_pipe(expr)

        elif isinstance(expr, MatchExpr):
            self._emit_match(expr)

        elif isinstance(expr, StringInterp):
            self._emit_string_interp(expr)

        elif isinstance(expr, ListLiteral):
            self._emit_list_literal(expr)

        elif isinstance(expr, IndexExpr):
            self._emit_index(expr)

        elif isinstance(expr, FieldExpr):
            self._emit_field(expr)

        elif isinstance(expr, LambdaExpr):
            self._cg._comment("lambda (not yet supported in ASM)")
            self._cg.emit_load_imm(0)

        elif isinstance(expr, FailPropExpr):
            self._emit_fail_prop(expr)

        else:
            self._cg._comment(f"unsupported expr: {type(expr).__name__}")
            self._cg.emit_load_imm(0)

    def _emit_binary(self, expr: BinaryExpr) -> None:
        # Comparisons and logical ops
        if expr.op in ("==", "!=", "<", ">", "<=", ">="):
            self._emit_expr(expr.left)
            self._cg.emit_push_result()
            self._emit_expr(expr.right)
            self._cg.emit_compare(expr.op)
        elif expr.op == "&&":
            end = self._cg.new_label(".Land_end")
            self._emit_expr(expr.left)
            self._cg.emit_branch_if_zero(end)
            self._emit_expr(expr.right)
            self._cg._label(end)
        elif expr.op == "||":
            end = self._cg.new_label(".Lor_end")
            self._emit_expr(expr.left)
            self._cg.emit_branch_if_nonzero(end)
            self._emit_expr(expr.right)
            self._cg._label(end)
        elif expr.op in ("+", "-", "*", "/", "%"):
            self._emit_expr(expr.left)
            self._cg.emit_push_result()
            self._emit_expr(expr.right)
            self._cg.emit_arith(expr.op)
        else:
            self._cg._comment(f"unsupported binary op: {expr.op}")
            self._cg.emit_load_imm(0)

    def _emit_unary(self, expr: UnaryExpr) -> None:
        self._emit_expr(expr.operand)
        if expr.op == "-":
            self._cg.emit_negate()
        elif expr.op == "!":
            self._cg.emit_not()

    def _emit_match(self, expr: MatchExpr) -> None:
        """Emit a match expression as conditional branches."""
        if expr.subject is None:
            # Implicit match — just emit all arm bodies
            for arm in expr.arms:
                for s in arm.body:
                    self._emit_stmt(s)
            return

        # Evaluate the subject once, store in a temp local
        self._emit_expr(expr.subject)
        subj_offset = self._alloc_local("__match_subj")
        self._cg.emit_store_local(subj_offset)

        end_label = self._cg.new_label(".Lmatch_end")

        for i, arm in enumerate(expr.arms):
            if isinstance(arm.pattern, LiteralPattern):
                next_label = self._cg.new_label(".Lmatch_next")
                # Load subject, compare with literal
                self._cg.emit_load_local(subj_offset)
                self._cg.emit_push_result()
                # Parse the literal value
                if arm.pattern.value == "true":
                    self._cg.emit_load_imm(1)
                elif arm.pattern.value == "false":
                    self._cg.emit_load_imm(0)
                else:
                    # Integer literal
                    try:
                        self._cg.emit_load_imm(int(arm.pattern.value))
                    except ValueError:
                        self._cg.emit_load_imm(0)
                self._cg.emit_compare("==")
                self._cg.emit_branch_if_zero(next_label)
                # Emit arm body
                for s in arm.body:
                    self._emit_stmt(s)
                self._cg.emit_branch(end_label)
                self._cg._label(next_label)

            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                # Default/else arm — always taken
                if isinstance(arm.pattern, BindingPattern):
                    # Bind the subject to the pattern name
                    self._cg.emit_load_local(subj_offset)
                    bind_offset = self._alloc_local(arm.pattern.name)
                    self._cg.emit_store_local(bind_offset)
                for s in arm.body:
                    self._emit_stmt(s)
                self._cg.emit_branch(end_label)

            else:
                self._cg._comment(f"unsupported match pattern: {type(arm.pattern).__name__}")

        self._cg._label(end_label)

    def _emit_call(self, expr: CallExpr) -> None:
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Dispatch to_string based on arg types (basic for now)
            if name == "to_string" and expr.args:
                self._emit_expr(expr.args[0])
                self._cg.emit_move_result_to_arg(0)
                self._cg.emit_call("prove_string_from_int", 1)
                return

            # Resolve builtin or user function
            c_name: str | None = _BUILTIN_MAP.get(name)
            if c_name is None:
                sig = self._symbols.resolve_function(
                    None, name, len(expr.args),
                )
                if sig is None:
                    sig = self._symbols.resolve_function_any(name)
                if sig and sig.verb is not None:
                    c_name = mangle_name(sig.verb, sig.name, sig.param_types)
                else:
                    c_name = name

            # Evaluate arguments and place in ABI registers
            if len(expr.args) <= 6:
                # Evaluate each arg, push to stack, then pop to arg regs
                for arg in expr.args:
                    self._emit_expr(arg)
                    self._cg.emit_push_result()
                for i in range(len(expr.args) - 1, -1, -1):
                    self._cg.emit_pop_arg(i)
            self._cg.emit_call(c_name, len(expr.args))

        elif isinstance(expr.func, TypeIdentifierExpr):
            # Constructor call
            name = expr.func.name
            for arg in expr.args:
                self._emit_expr(arg)
                self._cg.emit_push_result()
            for i in range(len(expr.args) - 1, -1, -1):
                self._cg.emit_pop_arg(i)
            self._cg.emit_call(name, len(expr.args))
        else:
            self._cg._comment("complex call target")
            self._cg.emit_load_imm(0)

    def _emit_pipe(self, expr: PipeExpr) -> None:
        """Emit a |> b as b(a)."""
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            c_name = _BUILTIN_MAP.get(name, name)
            self._emit_expr(expr.left)
            self._cg.emit_move_result_to_arg(0)
            self._cg.emit_call(c_name, 1)
        elif isinstance(expr.right, CallExpr) and isinstance(
            expr.right.func, IdentifierExpr,
        ):
            name = expr.right.func.name
            c_name = _BUILTIN_MAP.get(name, name)
            # Evaluate left (first arg)
            self._emit_expr(expr.left)
            self._cg.emit_push_result()
            # Evaluate extra args
            for arg in expr.right.args:
                self._emit_expr(arg)
                self._cg.emit_push_result()
            # Pop all to arg regs
            total = 1 + len(expr.right.args)
            for i in range(total - 1, -1, -1):
                self._cg.emit_pop_arg(i)
            self._cg.emit_call(c_name, total)
        else:
            self._emit_expr(expr.left)
            self._cg.emit_move_result_to_arg(0)
            self._emit_expr(expr.right)
            self._cg.emit_call("/* pipe */", 1)

    def _emit_string_interp(self, expr: StringInterp) -> None:
        """Emit string interpolation by concatenating parts."""
        first = True
        for part in expr.parts:
            if isinstance(part, StringLit):
                label = self._add_string(part.value)
                self._cg.emit_load_string(label)
                self._cg.emit_call("prove_string_from_cstr", 1)
            else:
                self._emit_expr(part)
                self._cg.emit_move_result_to_arg(0)
                self._cg.emit_call("prove_string_from_int", 1)
            if not first:
                # Concatenate: previous result on stack, current in %rax
                self._cg.emit_move_result_to_arg(1)
                self._cg.emit_pop_arg(0)
                self._cg.emit_call("prove_string_concat", 2)
            else:
                self._cg.emit_push_result()
                first = False
        if not first:
            # Final result is already in %rax from last concat
            pass
        else:
            # Empty interpolation
            label = self._add_string("")
            self._cg.emit_load_string(label)
            self._cg.emit_call("prove_string_from_cstr", 1)

    def _emit_list_literal(self, expr: ListLiteral) -> None:
        """Emit a list literal: call prove_list_new, then push each element."""
        self._cg.emit_call("prove_list_new", 0)
        # Save list pointer
        list_offset = self._alloc_local("__list_tmp")
        self._cg.emit_store_local(list_offset)
        for elem in expr.elements:
            self._emit_expr(elem)
            self._cg.emit_push_result()
            self._cg.emit_load_local(list_offset)
            self._cg.emit_move_result_to_arg(0)
            self._cg.emit_pop_arg(1)
            self._cg.emit_call("prove_list_push", 2)
        # Result = list pointer
        self._cg.emit_load_local(list_offset)

    def _emit_index(self, expr: IndexExpr) -> None:
        """Emit list[index] as prove_list_get(list, index)."""
        self._emit_expr(expr.obj)
        self._cg.emit_push_result()
        self._emit_expr(expr.index)
        self._cg.emit_push_result()
        self._cg.emit_pop_arg(1)
        self._cg.emit_pop_arg(0)
        self._cg.emit_call("prove_list_get", 2)

    def _emit_field(self, expr: FieldExpr) -> None:
        """Emit record field access (struct member)."""
        self._cg._comment(f"field access: .{expr.field}")
        self._emit_expr(expr.obj)
        # For structs this needs offset computation; stub for now
        self._cg._comment("(field offset not yet computed)")

    def _emit_fail_prop(self, expr: FailPropExpr) -> None:
        """Emit fail propagation: call inner, check for error, return early."""
        self._emit_expr(expr.expr)
        # Store result
        res_offset = self._alloc_local("__fail_tmp")
        self._cg.emit_store_local(res_offset)
        # Check if error
        self._cg.emit_load_local(res_offset)
        self._cg.emit_move_result_to_arg(0)
        self._cg.emit_call("prove_result_is_err", 1)
        ok_label = self._cg.new_label(".Lfail_ok")
        self._cg.emit_branch_if_zero(ok_label)
        # Error path: return the error result
        self._cg.emit_load_local(res_offset)
        self._cg.emit_epilogue()
        self._cg._label(ok_label)
        # Success path: unwrap
        self._cg.emit_load_local(res_offset)
        self._cg.emit_move_result_to_arg(0)
        self._cg.emit_call("prove_result_unwrap_int", 1)

    # ── Helpers ───────────────────────────────────────────────

    def _add_string(self, value: str) -> str:
        """Add a string to the data section and return its label."""
        self._str_counter += 1
        label = f".Lstr{self._str_counter}"
        self._cg.add_string_data(label, value)
        return label
