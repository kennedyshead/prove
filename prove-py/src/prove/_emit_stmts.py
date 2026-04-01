"""Statement emission mixin for CEmitter."""

from __future__ import annotations

from typing import Any

from prove.ast_nodes import (
    Assignment,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    CommentStmt,
    DecimalLit,
    ExplainEntry,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FloatLit,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    LiteralPattern,
    LookupPattern,
    MatchExpr,
    RawStringLit,
    RegexLit,
    Stmt,
    StringLit,
    TailContinue,
    TailLoop,
    TodoStmt,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    VariantPattern,
    WhileLoop,
    WildcardPattern,
)
from prove.c_types import CType, mangle_type_name, map_type, safe_c_name
from prove.types import (
    ERROR_TY,
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    ArrayType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    TypeVariable,
    UnitType,
    get_scale,
)
from prove.verb_defs import ALL_IO_VERBS, NON_ALLOCATING_VERBS

_IO_VERBS = ALL_IO_VERBS

# Literal types whose value the checker can statically verify against
# refinement constraints (E355).  No runtime guard needed for these.
_LITERAL_TYPES = (IntegerLit, DecimalLit, FloatLit, StringLit, BooleanLit, CharLit)


def _is_compile_time_literal(expr: Expr | None) -> bool:
    """Return True if *expr* is a compile-time literal (including negated numerics)."""
    if expr is None:
        return False
    if isinstance(expr, _LITERAL_TYPES):
        return True
    # Negated numeric literal: -42, -3.14
    if isinstance(expr, UnaryExpr) and expr.op == "-":
        return isinstance(expr.operand, (IntegerLit, DecimalLit, FloatLit))
    return False


class StmtEmitterMixin:
    _locals: dict[str, Type]
    _in_tail_loop: bool
    _in_main: bool
    _current_func: FunctionDef | None
    _in_region_scope: bool
    # ── Value → concrete type coercion helpers ─────────────────────

    def _is_value_type(self, ty: Type) -> bool:
        """Check if ty represents the Value type (TypeVariable or PrimitiveType)."""
        return (isinstance(ty, TypeVariable) and ty.name == "Value") or (
            isinstance(ty, PrimitiveType) and ty.name == "Value"
        )

    def _is_io_context(self) -> bool:
        """Check if the current function is an IO context (always needs runtime guards)."""
        if self._in_main:
            return True
        if self._current_func is not None:
            return getattr(self._current_func, "verb", None) in _IO_VERBS
        return True  # conservative default

    def _value_coercion_expr(self, raw_expr: str, target_ty: Type) -> str | None:
        """Return a prove_value_as_*() call to coerce a Prove_Value* to target_ty.

        Returns None if no coercion is needed (target is also Value).
        """
        if self._is_value_type(target_ty):  # noqa: E501
            return None
        if isinstance(target_ty, GenericInstance) and target_ty.base_name == "Table":
            return f"prove_value_as_object({raw_expr})"
        if isinstance(target_ty, ListType):
            return f"prove_value_as_array({raw_expr})"
        if isinstance(target_ty, GenericInstance) and target_ty.base_name == "List":
            return f"prove_value_as_array({raw_expr})"
        if isinstance(target_ty, PrimitiveType):
            if target_ty.name == "String":
                return f"prove_value_as_text({raw_expr})"
            if target_ty.name == "Integer":
                return f"prove_value_as_number({raw_expr})"
            if target_ty.name in ("Decimal", "Float"):
                return f"prove_value_as_decimal({raw_expr})"
            if target_ty.name == "Boolean":
                return f"prove_value_as_bool({raw_expr})"
        return None

    def _emit_region_exit(self) -> None:
        """Emit prove_region_exit if inside a region scope."""
        if self._in_region_scope:
            self._line("prove_region_exit(prove_global_region());")

    def _emit_explain_branches(self, fd: FunctionDef, ret_type: Type) -> None:
        """Emit if/else-if chains from explain entries with `when` conditions.

        Entries with conditions map to body expressions by order.
        An entry without a condition becomes the else branch.
        """
        assert fd.explain is not None

        # Separate entries with and without conditions
        cond_entries: list[tuple[ExplainEntry, int]] = []
        default_idx: int | None = None
        for i, entry in enumerate(fd.explain.entries):
            if entry.condition is not None:
                cond_entries.append((entry, i))
            else:
                default_idx = i

        is_unit = isinstance(ret_type, UnitType)

        # Each obligation maps to the body expression at the same index.
        # Body is a list of stmts — we use obligation index to pick the
        # corresponding body expression.
        body = fd.body

        first = True
        for entry, idx in cond_entries:
            assert entry.condition is not None
            cond = self._emit_expr(entry.condition)
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
                        self._emit_region_exit()
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
                    self._emit_region_exit()
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(stmt)
            self._indent -= 1
            self._line("}")

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
                    self._emit_region_exit()
                elif is_failable:
                    # For failable functions, wrap last expression in result_ok
                    last_expr = self._stmt_expr(stmt)
                    last_is_failprop = isinstance(last_expr, FailPropExpr)
                    # Error("message") constructor → return prove_result_err
                    last_is_error_ctor = (
                        isinstance(last_expr, CallExpr)
                        and isinstance(last_expr.func, TypeIdentifierExpr)
                        and last_expr.func.name == "Error"
                        and len(last_expr.args) == 1
                    )
                    if last_is_error_ctor:
                        assert isinstance(last_expr, CallExpr)
                        arg = last_expr.args[0]
                        if isinstance(arg, StringLit):
                            ref = self._static_error_ref(self._escape_c_string(arg.value))
                            self._emit_releases(None)
                            self._emit_region_exit()
                            self._line(f"return prove_result_err({ref});")
                        else:
                            err_val = self._emit_expr(arg)
                            self._emit_releases(None)
                            self._emit_region_exit()
                            self._line(f"return prove_result_err({err_val});")
                    elif (
                        isinstance(ret_type, GenericInstance)
                        and ret_type.base_name == "Result"
                        and not last_is_failprop
                    ):
                        # Already returns Result — just emit and return ok
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
                        self._emit_region_exit()
                        self._line("return prove_result_ok();")
                    elif isinstance(ret_type, UnitType):
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
                        self._emit_region_exit()
                        self._line("return prove_result_ok();")
                    else:
                        # Non-Result return: capture and wrap
                        expr = self._stmt_expr(stmt)
                        if expr is not None:
                            # When a FailProp (!) unwraps a Result return,
                            # the captured value is the inner success type
                            wrap_type: Type = ret_type
                            if (
                                last_is_failprop
                                and isinstance(ret_type, GenericInstance)
                                and ret_type.base_name == "Result"
                                and ret_type.args
                            ):
                                wrap_type = ret_type.args[0]
                            ret_tmp = self._tmp()
                            ret_ct = map_type(wrap_type)
                            self._in_return_position = True
                            ret_val = self._emit_expr(expr)
                            self._in_return_position = False
                            self._line(f"{ret_ct.decl} {ret_tmp} = {ret_val};")
                            self._emit_releases(ret_tmp)
                            self._emit_region_exit()
                            if isinstance(wrap_type, RecordType):
                                heap_tmp = self._tmp()
                                self._line(
                                    f"{ret_ct.decl}* {heap_tmp} = malloc(sizeof({ret_ct.decl}));"
                                )
                                self._line(f"*{heap_tmp} = {ret_tmp};")
                                self._line(f"return prove_result_ok_ptr({heap_tmp});")
                            elif ret_ct.is_pointer:
                                self._line(f"return prove_result_ok_ptr({ret_tmp});")
                            elif ret_ct.decl == "double":
                                self._line(f"return prove_result_ok_double({ret_tmp});")
                            elif isinstance(wrap_type, GenericInstance) and not ret_ct.is_pointer:
                                # Struct-like generic (Option<Value>, etc.) — heap-allocate
                                heap_tmp = self._tmp()
                                self._line(
                                    f"{ret_ct.decl}* {heap_tmp} = malloc(sizeof({ret_ct.decl}));"
                                )
                                self._line(f"*{heap_tmp} = {ret_tmp};")
                                self._line(f"return prove_result_ok_ptr({heap_tmp});")
                            else:
                                self._line(f"return prove_result_ok_int({ret_tmp});")
                        else:
                            self._emit_stmt(stmt)
                            self._emit_releases(None)
                            self._emit_region_exit()
                            self._line("return prove_result_ok();")
                else:
                    expr = self._stmt_expr(stmt)
                    if expr is not None:
                        ret_tmp = self._tmp()
                        ret_ct = map_type(ret_type)
                        # Check if expression returns Result but function does not
                        expr_type = self._infer_expr_type(expr)
                        needs_ret_unwrap = False
                        is_result_expr = (
                            isinstance(expr_type, GenericInstance)
                            and expr_type.base_name == "Result"
                        )
                        is_result_ret = (
                            isinstance(ret_type, GenericInstance) and ret_type.base_name == "Result"
                        )
                        if is_result_expr and not is_result_ret:
                            needs_ret_unwrap = True
                        if not needs_ret_unwrap and not isinstance(expr, FailPropExpr):
                            call_sig = self._resolve_call_sig(expr)
                            if (
                                call_sig is not None
                                and call_sig.can_fail
                                and not (
                                    isinstance(call_sig.return_type, GenericInstance)
                                    and call_sig.return_type.base_name == "Result"
                                )
                            ):
                                needs_ret_unwrap = True

                        self._in_return_position = True
                        emit_val = self._emit_expr(expr)
                        self._in_return_position = False
                        if needs_ret_unwrap:
                            # Unwrap Result for non-failable return
                            res_tmp = self._tmp()
                            self._line(f"Prove_Result {res_tmp} = {emit_val};")
                            self._line("#ifndef PROVE_RELEASE")
                            _span = getattr(expr, "span", None)
                            _loc = f" ({_span.file}:{_span.start_line})" if _span else ""
                            self._line(
                                f"if (prove_result_is_err({res_tmp}))"
                                f' prove_panic("unexpected error{_loc}");'
                            )
                            self._line("#endif")
                            # Check for Value → concrete coercion
                            success_ty = (
                                expr_type.args[0]
                                if isinstance(expr_type, GenericInstance)
                                and expr_type.base_name == "Result"
                                and expr_type.args
                                else None
                            )
                            coercion = None
                            if (
                                success_ty is not None
                                and self._is_value_type(success_ty)
                                and not self._is_value_type(ret_type)
                            ):
                                coercion = self._value_coercion_expr("_val_tmp", ret_type)
                            unwrap = f"prove_result_unwrap_ptr({res_tmp})"
                            if coercion is not None:
                                val_tmp = self._tmp()
                                self._line(f"Prove_Value* {val_tmp} = (Prove_Value*){unwrap};")
                                cc = self._value_coercion_expr(val_tmp, ret_type)
                                self._line(f"{ret_ct.decl} {ret_tmp} = {cc};")
                            elif isinstance(ret_type, RecordType):
                                cast = f"*(({ret_ct.decl}*){unwrap})"
                                self._line(f"{ret_ct.decl} {ret_tmp} = {cast};")
                            elif ret_ct.is_pointer:
                                self._line(f"{ret_ct.decl} {ret_tmp} = ({ret_ct.decl}){unwrap};")
                            elif ret_ct.decl == "double":
                                self._line(
                                    f"{ret_ct.decl} {ret_tmp} ="
                                    f" prove_result_unwrap_double({res_tmp});"
                                )
                            elif isinstance(ret_type, GenericInstance) and not ret_ct.is_pointer:
                                cast = f"*(({ret_ct.decl}*){unwrap})"
                                self._line(f"{ret_ct.decl} {ret_tmp} = {cast};")
                            else:
                                self._line(
                                    f"{ret_ct.decl} {ret_tmp} = prove_result_unwrap_int({res_tmp});"
                                )
                        else:
                            # For validates functions returning bool: if returning an Option,
                            # check if it's Some (tag == 1)
                            if isinstance(ret_type, PrimitiveType) and ret_type.name == "Boolean":
                                if (
                                    isinstance(expr_type, GenericInstance)
                                    and expr_type.base_name == "Option"
                                ):
                                    opt_tmp = self._tmp()
                                    opt_ct = map_type(expr_type)
                                    self._line(f"{opt_ct.decl} {opt_tmp} = {emit_val};")
                                    emit_val = f"({opt_tmp}.tag == 1)"
                            # Implicit Option wrapping: bare T → Some(T), Unit → None
                            # Skip for MatchExpr — _emit_match_expr already
                            # handles promotion and wrapping internally.
                            _is_match = isinstance(expr, MatchExpr)
                            if (
                                not _is_match
                                and isinstance(ret_type, GenericInstance)
                                and ret_type.base_name == "Option"
                                and ret_type.args
                                and not (
                                    isinstance(expr_type, GenericInstance)
                                    and expr_type.base_name == "Option"
                                )
                            ):
                                if isinstance(expr_type, UnitType):
                                    self._line(f"{ret_ct.decl} {ret_tmp} = prove_option_none();")
                                else:
                                    inner_ct = map_type(expr_type)
                                    if inner_ct.is_pointer:
                                        self._line(
                                            f"{ret_ct.decl} {ret_tmp} ="
                                            f" prove_option_some((Prove_Value*){emit_val});"
                                        )
                                    elif isinstance(expr_type, RecordType):
                                        heap = self._tmp()
                                        self._line(
                                            f"{inner_ct.decl}* {heap} = ({inner_ct.decl}*)"
                                            f"prove_region_alloc(prove_global_region(),"
                                            f" sizeof({inner_ct.decl}));"
                                        )
                                        self._line(f"*{heap} = {emit_val};")
                                        self._line(
                                            f"{ret_ct.decl} {ret_tmp} ="
                                            f" prove_option_some((Prove_Value*){heap});"
                                        )
                                    else:
                                        cast = f"(Prove_Value*)(intptr_t){emit_val}"
                                        some_call = f"prove_option_some({cast})"
                                        self._line(f"{ret_ct.decl} {ret_tmp} = {some_call};")
                            else:
                                self._line(f"{ret_ct.decl} {ret_tmp} = {emit_val};")
                        self._emit_releases(ret_tmp)
                        self._emit_region_exit()
                        self._line(f"return {ret_tmp};")
                    else:
                        self._emit_stmt(stmt)
                        self._emit_releases(None)
                        self._emit_region_exit()
            else:
                self._emit_stmt(stmt)

    def _emit_releases(self, skip_var: str | None) -> None:
        """Emit prove_release for all pointer locals except skip_var.

        Non-allocating verbs (validates/derives/matches) skip all releases:
        they never create heap objects, so every pointer local is a borrowed
        alias of a caller-owned value — no ownership to relinquish.

        Pure allocating verbs (creates/transforms) skip releases for PARAMS
        (caller retains ownership) but still release local variables that
        were allocated inside the function body.
        """
        from prove.verb_defs import PURE_VERBS

        verb = getattr(self._current_func, "verb", None) if self._current_func else None
        if verb in NON_ALLOCATING_VERBS:
            return
        is_pure = verb in PURE_VERBS
        for name, ty in self._locals.items():
            if name == skip_var:
                continue
            # Pure verbs don't own their params — skip release
            if is_pure and name in self._param_names:
                continue
            # Skip Verb/FunctionType — function pointers, not heap objects
            if isinstance(ty, PrimitiveType) and ty.name == "Verb":
                continue
            if isinstance(ty, FunctionType):
                continue
            ct = map_type(ty)
            if ct.is_pointer and not self._can_elide_retain(name):
                self._line(f"prove_release({name});")

    def _stmt_expr(self, stmt: Stmt) -> Expr | None:
        """Extract the expression from a statement, if it is an ExprStmt."""
        if isinstance(stmt, ExprStmt):
            return stmt.expr
        if isinstance(stmt, MatchExpr):
            return stmt
        return None

    # ── Statement emission ─────────────────────────────────────

    def _emit_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, VarDecl):
            self._emit_var_decl(stmt)
        elif isinstance(stmt, Assignment):
            self._emit_assignment(stmt)
        elif isinstance(stmt, FieldAssignment):
            self._emit_field_assignment(stmt)
        elif isinstance(stmt, ExprStmt):
            self._emit_expr_stmt(stmt)
        elif isinstance(stmt, TailLoop):
            self._emit_tail_loop(stmt)
        elif isinstance(stmt, TailContinue):
            self._emit_tail_continue(stmt)
        elif isinstance(stmt, WhileLoop):
            self._emit_while_loop(stmt)
        elif isinstance(stmt, MatchExpr):
            self._emit_match_stmt(stmt)
        elif isinstance(stmt, CommentStmt):
            pass  # comments don't emit C code
        elif isinstance(stmt, TodoStmt):
            msg = stmt.message or self._get_current_function_name() or "not implemented"
            _loc = f"{stmt.span.file}:{stmt.span.start_line}"
            self._line(f'prove_panic("TODO: {msg} ({_loc})");')

    def _emit_var_decl(self, vd: VarDecl) -> None:
        # C-safe variable name (escapes C keywords like 'default')
        cn = safe_c_name(vd.name)

        # Dispatch lookup assignment: skip C var, record for lazy dispatch at call site
        from prove.ast_nodes import LookupAccessExpr
        from prove.types import PrimitiveType

        if isinstance(vd.value, LookupAccessExpr):
            lookup = self._lookup_tables.get(vd.value.type_name)
            if lookup is not None and lookup.is_dispatch:
                self._dispatch_vars[vd.name] = (vd.value.type_name, vd.value.operand)
                self._locals[vd.name] = PrimitiveType("Verb")
                return

        # Store-backed lookup type annotations: Color at C level is either
        # a StoreTable* (for table loads) or a row construction (variant+vals).
        if vd.type_expr:
            type_name_str = getattr(vd.type_expr, "name", "")
            if type_name_str in self._store_lookup_types:
                val = self._emit_expr(vd.value)
                # Check if this is a row construction (variant + vals arrays)
                if hasattr(self, "_store_rows") and val in self._store_rows:
                    variant_name, vals_name = self._store_rows[val]
                    self._store_rows[vd.name] = (variant_name, vals_name)
                    self._locals[vd.name] = self._symbols.resolve_type(type_name_str) or ERROR_TY
                    self._store_var_types[vd.name] = type_name_str
                    return
                # Otherwise it's a table load — emit as Prove_StoreTable*
                self._needed_headers.add("prove_store.h")
                self._line(f"Prove_StoreTable *{cn} = {val};")
                # Initialize column schema from lookup type if table is empty
                lookup = self._lookup_tables.get(type_name_str)
                if lookup and lookup.value_types:
                    col_count = len(lookup.value_types)
                    self._line(f"if ({cn}->column_count == 0) {{")
                    self._indent += 1
                    self._line(f"{cn}->column_count = {col_count};")
                    self._line(
                        f"{cn}->column_names = (Prove_String **)calloc("
                        f"{col_count}, sizeof(Prove_String *));"
                    )
                    for i, vt in enumerate(lookup.value_types):
                        col_name = vt.name if hasattr(vt, "name") else "unknown"
                        self._line(
                            f'{vd.name}->column_names[{i}] = prove_string_from_cstr("{col_name}");'
                        )
                    self._indent -= 1
                    self._line("}")
                self._locals[vd.name] = self._symbols.resolve_type("StoreTable") or ERROR_TY
                self._store_var_types[vd.name] = type_name_str
                return

        # Determine target type: from annotation if present, else from value
        inferred_ty = self._infer_expr_type(vd.value)
        target_ty = inferred_ty
        if vd.type_expr:
            # Resolve type from annotation
            # SimpleType has 'name', GenericType has 'name' and 'args', ModifiedType has 'base_type'
            type_name = getattr(vd.type_expr, "name", None)
            if type_name is None:
                # Could be ModifiedType with base_type
                base = getattr(vd.type_expr, "base_type", None)
                if base:
                    type_name = getattr(base, "name", None)
            if type_name:
                # Handle GenericType annotations (e.g. Table<Value>, Option<Integer>)
                type_args = getattr(vd.type_expr, "args", None)
                if type_args and type_name == "List":
                    # List<Value> → ListType(element=Value)
                    ta = type_args[0]
                    ta_name = getattr(ta, "name", None)
                    if ta_name:
                        resolved_arg = self._symbols.resolve_type(ta_name)
                        target_ty = ListType(resolved_arg if resolved_arg else INTEGER)
                elif type_args and type_name == "Array":
                    # Array<T> → ArrayType(element=T)
                    ta = type_args[0]
                    ta_name = getattr(ta, "name", None)
                    if ta_name:
                        resolved_arg = self._symbols.resolve_type(ta_name)
                        target_ty = ArrayType(resolved_arg if resolved_arg else INTEGER)
                elif type_args and type_name in ("Table", "Option", "Result", "Value"):
                    arg_types: list[Type] = []
                    for ta in type_args:
                        ta_name = getattr(ta, "name", None)
                        if ta_name:
                            resolved_arg = self._symbols.resolve_type(ta_name)
                            arg_types.append(resolved_arg if resolved_arg else INTEGER)
                    target_ty = GenericInstance(type_name, arg_types)
                else:
                    resolved = self._symbols.resolve_type(type_name)
                    if resolved:
                        target_ty = resolved

        # Set expected type for binary lookup column selection
        self._expected_emit_type = target_ty

        # When annotation and value are both Option but with different inner types,
        # emit conversion code (e.g. Option<String> → Option<Integer> via parse)
        value_ty = inferred_ty
        if (
            isinstance(target_ty, GenericInstance)
            and isinstance(value_ty, GenericInstance)
            and target_ty.base_name == value_ty.base_name == "Option"
            and target_ty.args
            and value_ty.args
        ):
            target_inner = map_type(target_ty.args[0])
            value_inner = map_type(value_ty.args[0])
            target_inner_type = target_ty.args[0]
            value_inner_type = value_ty.args[0]
            needs_refinement_check = (
                isinstance(target_inner_type, RefinementType)
                and target_inner_type.constraint
                and isinstance(value_inner_type, PrimitiveType)
                and value_inner_type.name == "String"
            )
            if target_inner.decl != value_inner.decl or needs_refinement_check:
                # Emit conversion: store raw, then convert
                raw_ct = map_type(value_ty)
                tgt_ct = map_type(target_ty)
                raw_tmp = self._tmp()
                self._line(f"{raw_ct.decl} {raw_tmp} = {self._emit_expr(vd.value)};")
                self._line(f"{tgt_ct.decl} {cn};")
                self._line(f"if ({raw_tmp}.tag == 1) {{")
                self._indent += 1
                if value_inner.decl == "Prove_String*" and target_inner.decl == "int64_t":
                    self._needed_headers.add("prove_convert.h")
                    cv_tmp = self._tmp()
                    self._line(
                        f"Prove_Result {cv_tmp} = prove_convert_integer_str("
                        f"(Prove_String*){raw_tmp}.value);"
                    )
                    self._line(
                        f"if (!prove_result_is_err({cv_tmp})) "
                        f"{cn} = prove_option_some((Prove_Value*)(intptr_t)prove_result_unwrap_int({cv_tmp}));"  # noqa: E501
                    )
                    self._line(f"else {cn} = prove_option_none();")
                else:
                    # Generic fallback: cast the value
                    # Check if inner type has refinement constraint
                    needs_refinement = (
                        isinstance(target_inner_type, RefinementType)
                        and target_inner_type.constraint
                    )
                    if needs_refinement:
                        # Validate before wrapping - on failure, return None
                        self._emit_refinement_validation_for_option(
                            f"({target_inner.decl}){raw_tmp}.value",
                            target_inner_type,
                            tgt_ct.decl,
                            vd.name,
                        )
                    else:
                        self._line(f"{cn} = prove_option_some({raw_tmp}.value);")
                self._indent -= 1
                self._line("} else {")
                self._indent += 1
                self._line(f"{cn} = prove_option_none();")
                self._indent -= 1
                self._line("}")
                self._locals[vd.name] = target_ty
                return

        # Auto-unwrap: Option<T> → T when annotation declares T and the
        # function has requires contracts (the contracts are the proof).
        has_requires = self._current_func is not None and getattr(
            self._current_func, "requires", None
        )
        if (
            has_requires
            and isinstance(value_ty, GenericInstance)
            and value_ty.base_name == "Option"
            and value_ty.args
            and not isinstance(target_ty, GenericInstance)
            and vd.type_expr is not None
        ):
            inner_ct = map_type(target_ty)
            if inner_ct.header:
                self._needed_headers.add(inner_ct.header)
            self._needed_headers.add("prove_option.h")
            val = self._emit_expr(vd.value)
            self._expected_emit_type = None
            if inner_ct.is_pointer:
                self._line(f"{inner_ct.decl} {cn} = ({inner_ct.decl})prove_option_unwrap({val});")
            else:
                tmp = self._named_tmp("opt")
                self._line(f"Prove_Option {tmp} = {val};")
                decl = inner_ct.decl
                self._line(f"{decl} {cn} = ({tmp}.tag == 1) ? ({decl}){tmp}.value : ({decl}){{0}};")
            self._locals[vd.name] = target_ty
            return

        # Check if value is a failable call returning Result and target is the success type
        needs_unwrap = False
        if isinstance(value_ty, GenericInstance) and value_ty.base_name == "Result":
            if isinstance(target_ty, GenericInstance) and target_ty.base_name == "Result":
                # Target is also Result, no unwrapping needed
                pass
            else:
                # Target is the success type, need to unwrap
                needs_unwrap = True
        # Also detect failable non-Result calls (without !)
        # The C function returns Prove_Result even though the Prove type is not Result
        if not needs_unwrap and not isinstance(vd.value, FailPropExpr):
            call_sig = self._resolve_call_sig(vd.value)
            if (
                call_sig is not None
                and call_sig.can_fail
                and not (
                    isinstance(call_sig.return_type, GenericInstance)
                    and call_sig.return_type.base_name == "Result"
                )
            ):
                needs_unwrap = True

        ct = map_type(target_ty)
        if ct.header:
            self._needed_headers.add(ct.header)
        val = self._emit_expr(vd.value)
        self._expected_emit_type = None

        if needs_unwrap:
            # For failable function returning Result, unwrap before assignment
            self._line("")
            tmp = self._named_tmp("result")
            self._line(f"Prove_Result {tmp} = {val};")
            # Check for error - panic if non-failable function, return error if failable
            is_failable = (
                getattr(self._current_func, "can_fail", False) if self._current_func else False
            )
            if self._in_main:
                err_str = self._named_tmp("error")
                self._line(f"if (prove_result_is_err({tmp})) {{")
                self._indent += 1
                self._line(f"Prove_String *{err_str} = (Prove_String*){tmp}.error;")
                self._line(
                    f'fprintf(stderr, "error: %.*s\\n", (int){err_str}->length, {err_str}->data);'
                )
                self._line("prove_runtime_cleanup();")
                self._line("return 1;")
                self._indent -= 1
                self._line("}")
            elif is_failable:
                if self._in_region_scope:
                    self._line(f"if (prove_result_is_err({tmp})) {{")
                    self._indent += 1
                    self._line("prove_region_exit(prove_global_region());")
                    self._line(f"return {tmp};")
                    self._indent -= 1
                    self._line("}")
                else:
                    self._line(f"if (prove_result_is_err({tmp})) return {tmp};")
            else:
                _loc = f"{vd.span.file}:{vd.span.start_line}"
                self._line(f'if (prove_result_is_err({tmp})) prove_panic("IO error ({_loc})");')
            # Unwrap the success value
            # Detect Value → concrete coercion: when the Result's success type
            # is Value but the target annotation is a concrete type, we must
            # extract the inner value via prove_value_as_*() instead of casting.
            success_ty = (
                value_ty.args[0]
                if isinstance(value_ty, GenericInstance)
                and value_ty.base_name == "Result"
                and value_ty.args
                else None
            )
            coercion = None
            if (
                success_ty is not None
                and self._is_value_type(success_ty)
                and not self._is_value_type(target_ty)
            ):
                coercion = self._value_coercion_expr("_val_tmp", target_ty)

            if coercion is not None:
                # Two-step unwrap: first get Prove_Value*, then coerce
                val_tmp = self._tmp()
                self._line(
                    f"Prove_Value* {val_tmp} = (Prove_Value*)prove_result_unwrap_ptr({tmp});"
                )
                coercion_call = self._value_coercion_expr(val_tmp, target_ty)
                self._line(f"{ct.decl} {cn} = {coercion_call};")
            elif isinstance(target_ty, RecordType):
                self._line(f"{ct.decl} {cn} = *(({ct.decl}*)prove_result_unwrap_ptr({tmp}));")
            elif ct.is_pointer:
                self._line(f"{ct.decl} {cn} = ({ct.decl})prove_result_unwrap_ptr({tmp});")
            elif ct.decl == "double":
                self._line(f"{ct.decl} {cn} = prove_result_unwrap_double({tmp});")
            elif isinstance(target_ty, GenericInstance) and not ct.is_pointer:
                # Struct-like GenericInstance (Option<Value>, etc.)
                self._line(f"{ct.decl} {cn} = *(({ct.decl}*)prove_result_unwrap_ptr({tmp}));")
            else:
                # For integer types
                self._line(f"{ct.decl} {cn} = prove_result_unwrap_int({tmp});")
        else:
            # Wrap bare value in Option if annotation is Option<Value> but value is Value
            if (
                isinstance(target_ty, GenericInstance)
                and target_ty.base_name == "Option"
                and not (isinstance(value_ty, GenericInstance) and value_ty.base_name == "Option")
            ):
                # Check if inner type has refinement constraint
                if (
                    target_ty.args
                    and isinstance(target_ty.args[0], RefinementType)
                    and target_ty.args[0].constraint
                ):
                    # Store value in temp first, then validate
                    # Get the inner type for the temp
                    inner_ct = map_type(target_ty.args[0])
                    tmp_val = self._tmp()
                    self._line(f"{inner_ct.decl} {tmp_val} = {val};")
                    self._emit_refinement_validation_for_option(
                        tmp_val, target_ty.args[0], ct.decl, vd.name
                    )
                else:
                    inner_ct = map_type(target_ty.args[0]) if target_ty.args else map_type(INTEGER)
                    if inner_ct.is_pointer:
                        self._line(f"{ct.decl} {cn} = prove_option_some((Prove_Value*){val});")
                    else:
                        self._line(
                            f"{ct.decl} {cn} = prove_option_some((Prove_Value*)(intptr_t){val});"  # noqa: E501
                        )
            else:
                # Value → concrete coercion (e.g. Prove_Value* → Prove_Table*)
                val_ct = map_type(value_ty)
                if (
                    self._is_value_type(value_ty)
                    and not self._is_value_type(target_ty)
                    and (coerce := self._value_coercion_expr(val, target_ty)) is not None
                ):
                    self._line(f"{ct.decl} {cn} = {coerce};")
                elif ct.is_pointer and val_ct.decl != ct.decl:
                    self._line(f"{ct.decl} {cn} = ({ct.decl}){val};")
                else:
                    # Scale:N rounding for non-literal Decimal assignments
                    scale = get_scale(target_ty)
                    if scale is not None and not _is_compile_time_literal(vd.value):
                        self._needed_headers.add("prove_math.h")
                        self._line(f"{ct.decl} {cn} = prove_decimal_round({val}, {scale});")
                    else:
                        self._line(f"{ct.decl} {cn} = {val};")

        # Validate refinement type constraints
        # Skip validation for GenericInstance (Option<Value>) because validation is already
        # done in the conversion code. Only validate direct RefinementType assignments.
        # Also skip when the source is a compile-time literal — the checker already
        # verified the constraint via _static_check_refinement (E355).
        if not isinstance(target_ty, GenericInstance):
            check_ty = target_ty
            validation_var = vd.name
            if isinstance(check_ty, RefinementType) and check_ty.constraint:
                if not _is_compile_time_literal(vd.value):
                    self._emit_refinement_validation(validation_var, check_ty)

        # Update locals with target type
        self._locals[vd.name] = target_ty
        # In a streams loop, guard nullable reads (e.g. prove_readln on EOF)
        if self._in_streams_loop and ct.is_pointer and isinstance(vd.value, CallExpr):
            if isinstance(vd.value.func, IdentifierExpr):
                call_sig = self._symbols.resolve_function_any(
                    vd.value.func.name, arity=len(vd.value.args)
                )
                if call_sig and call_sig.verb == "inputs":
                    self._line(f"if (!{cn}) goto _streams_exit;")
        # Retain pointer types (skip for non-escaping vars in release mode)
        if ct.is_pointer and not self._can_elide_retain(vd.name):
            self._line(f"prove_retain({cn});")

    def _emit_refinement_validation(self, var_name: str, target_ty: RefinementType) -> None:
        """Emit runtime validation for refinement type constraints.

        In pure (non-IO) functions the guard is wrapped in #ifndef PROVE_RELEASE
        so it is stripped in release builds.  IO contexts always keep the guard.
        """
        constraint = target_ty.constraint
        if constraint is None:
            return

        io_ctx = self._is_io_context()
        _func_span = getattr(self._current_func, "span", None) if self._current_func else None
        _loc = f" ({_func_span.file}:{_func_span.start_line})" if _func_span else ""

        if isinstance(constraint, RegexLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.pattern.replace("\\", "\\\\")
            if not io_ctx:
                self._line("#ifndef PROVE_RELEASE")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'  # noqa: E501
            )
            self._indent += 1
            self._line(f'prove_panic("constraint failed: value does not match pattern{_loc}");')
            self._indent -= 1
            self._line("}")
            if not io_ctx:
                self._line("#endif")
        elif isinstance(constraint, RawStringLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.value.replace("\\", "\\\\")
            if not io_ctx:
                self._line("#ifndef PROVE_RELEASE")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'  # noqa: E501
            )
            self._indent += 1
            self._line(f'prove_panic("constraint failed: value does not match pattern{_loc}");')
            self._indent -= 1
            self._line("}")
            if not io_ctx:
                self._line("#endif")
        elif isinstance(constraint, BinaryExpr):
            self._emit_numeric_refinement(var_name, constraint, io_ctx)

    def _emit_numeric_refinement(
        self,
        var_name: str,
        constraint: BinaryExpr,
        io_context: bool = True,
    ) -> None:
        """Emit runtime validation for numeric refinement constraints."""
        from prove.type_inference import BINARY_OP_TO_C

        _func_span = getattr(self._current_func, "span", None) if self._current_func else None
        _loc = f" ({_func_span.file}:{_func_span.start_line})" if _func_span else ""

        if constraint.op == "..":
            # Range: 1..65535 → if (val < 1 || val > 65535) { panic }
            lo = self._emit_constraint_operand(constraint.left, var_name)
            hi = self._emit_constraint_operand(constraint.right, var_name)
            if not io_context:
                self._line("#ifndef PROVE_RELEASE")
            self._line(f"if ({var_name} < {lo} || {var_name} > {hi}) {{")
            self._indent += 1
            self._line(  # noqa: E501
                f'prove_panic("refinement type constraint violated: value out of range{_loc}");'
            )
            self._indent -= 1
            self._line("}")
            if not io_context:
                self._line("#endif")
        elif constraint.op in BINARY_OP_TO_C:
            c_op = BINARY_OP_TO_C[constraint.op]
            if constraint.op in ("&&", "||"):
                # Compound constraint: emit both sides
                self._emit_compound_refinement(var_name, constraint, io_context)
            else:
                # Comparison: self != 0 → if (!(val != 0)) { panic }
                left = self._emit_constraint_operand(constraint.left, var_name)
                right = self._emit_constraint_operand(constraint.right, var_name)
                if not io_context:
                    self._line("#ifndef PROVE_RELEASE")
                self._line(f"if (!({left} {c_op} {right})) {{")
                self._indent += 1
                self._line(f'prove_panic("refinement type constraint violated{_loc}");')
                self._indent -= 1
                self._line("}")
                if not io_context:
                    self._line("#endif")

    def _emit_compound_refinement(
        self,
        var_name: str,
        constraint: BinaryExpr,
        io_context: bool = True,
    ) -> None:
        """Emit compound constraint (&&, ||)."""
        from prove.type_inference import BINARY_OP_TO_C

        _func_span = getattr(self._current_func, "span", None) if self._current_func else None
        _loc = f" ({_func_span.file}:{_func_span.start_line})" if _func_span else ""

        c_op = BINARY_OP_TO_C[constraint.op]
        left = self._emit_constraint_condition(constraint.left, var_name)
        right = self._emit_constraint_condition(constraint.right, var_name)
        if not io_context:
            self._line("#ifndef PROVE_RELEASE")
        self._line(f"if (!({left} {c_op} {right})) {{")
        self._indent += 1
        self._line(f'prove_panic("refinement type constraint violated{_loc}");')
        self._indent -= 1
        self._line("}")
        if not io_context:
            self._line("#endif")

    def _emit_constraint_condition(self, expr: Expr, var_name: str) -> str:
        """Emit a constraint sub-expression as a C condition string."""
        from prove.type_inference import BINARY_OP_TO_C

        if isinstance(expr, BinaryExpr):
            if expr.op == "..":
                lo = self._emit_constraint_operand(expr.left, var_name)
                hi = self._emit_constraint_operand(expr.right, var_name)
                return f"({var_name} >= {lo} && {var_name} <= {hi})"
            elif expr.op in BINARY_OP_TO_C:
                left = self._emit_constraint_operand(expr.left, var_name)
                right = self._emit_constraint_operand(expr.right, var_name)
                return f"({left} {BINARY_OP_TO_C[expr.op]} {right})"
        return "1"

    def _emit_constraint_operand(self, expr: Expr, var_name: str) -> str:
        """Emit a single operand of a constraint expression, replacing 'self' with var_name."""
        if isinstance(expr, IdentifierExpr):
            if expr.name == "self":
                return var_name
            return expr.name
        if isinstance(expr, IntegerLit):
            return expr.value
        if isinstance(expr, UnaryExpr) and expr.op == "-":
            inner = self._emit_constraint_operand(expr.operand, var_name)
            return f"(-{inner})"
        if isinstance(expr, BinaryExpr):
            return self._emit_constraint_condition(expr, var_name)
        return self._emit_expr(expr)

    def _emit_refinement_validation_for_option(
        self, var_name: str, target_ty: Type, option_ct: str | CType, result_var: str
    ) -> None:
        """Emit validation that returns None on failure instead of panicking."""
        if not isinstance(target_ty, RefinementType):
            return
        constraint = target_ty.constraint
        if constraint is None:
            return

        # Declare the result variable first
        self._line(f"{option_ct} {result_var};")

        # Now we know target_ty is RefinementType
        rt = target_ty
        constraint = rt.constraint

        # Determine the right cast for wrapping the value
        inner_ct = map_type(target_ty)
        if inner_ct.is_pointer:
            some_expr = f"prove_option_some((Prove_Value*){var_name})"
        else:
            some_expr = f"prove_option_some((Prove_Value*)(intptr_t){var_name})"

        if isinstance(constraint, RegexLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.pattern.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'  # noqa: E501
            )
            self._indent += 1
            # Return None for Option type - silent failure
            self._line(f"{result_var} = prove_option_none();")
            self._indent -= 1
            self._line("} else {")
            self._indent += 1
            self._line(f"{result_var} = {some_expr};")
            self._indent -= 1
            self._line("}")
        elif isinstance(constraint, RawStringLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.value.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'  # noqa: E501
            )
            self._indent += 1
            # Return None for Option type - silent failure
            self._line(f"{result_var} = prove_option_none();")
            self._indent -= 1
            self._line("} else {")
            self._indent += 1
            self._line(f"{result_var} = {some_expr};")
            self._indent -= 1
            self._line("}")
        elif isinstance(constraint, BinaryExpr):
            cond = self._emit_numeric_option_condition(var_name, constraint)
            if cond:
                self._line(f"if (!({cond})) {{")
                self._indent += 1
                self._line(f"{result_var} = prove_option_none();")
                self._indent -= 1
                self._line("} else {")
                self._indent += 1
                self._line(f"{result_var} = {some_expr};")
                self._indent -= 1
                self._line("}")
            else:
                self._line(f"{result_var} = {some_expr};")

    def _emit_numeric_option_condition(self, var_name: str, constraint: BinaryExpr) -> str | None:
        """Build a C condition string for a numeric constraint (used in Option context)."""
        if constraint.op == "..":
            lo = self._emit_constraint_operand(constraint.left, var_name)
            hi = self._emit_constraint_operand(constraint.right, var_name)
            return f"{var_name} >= {lo} && {var_name} <= {hi}"
        return self._emit_constraint_condition(constraint, var_name)

    def _emit_assignment(self, assign: Assignment) -> None:
        val = self._emit_expr(assign.value)
        # If the RHS is a void function call, emit just the call (no assignment)
        call_sig = self._resolve_call_sig(assign.value)
        if call_sig is not None and isinstance(call_sig.return_type, UnitType):
            self._line(f"{val};")
        else:
            self._line(f"{assign.target} = {val};")
        # Validate refinement constraints on reassignment
        # Skip when source is a compile-time literal (checker already verified via E355)
        target_ty = self._locals.get(assign.target)
        if isinstance(target_ty, RefinementType) and target_ty.constraint:
            if not _is_compile_time_literal(assign.value):
                self._emit_refinement_validation(assign.target, target_ty)

    def _emit_field_assignment(self, fa: FieldAssignment) -> None:
        target = self._emit_expr(fa.target)
        val = self._emit_expr(fa.value)
        # Infer target field type and unwrap Option if needed
        target_type = self._infer_expr_type(fa.target)
        if isinstance(target_type, RecordType):
            field_type = target_type.fields.get(fa.field)
            if field_type:
                val_type = self._infer_expr_type(fa.value)
                val = self._maybe_unwrap_option_value(val, val_type, field_type)
        self._line(f"{target}.{fa.field} = {val};")

    def _emit_expr_stmt(self, es: ExprStmt) -> None:
        # Match expressions wrapped in ExprStmt must go through
        # _emit_match_stmt, not _emit_expr (which returns "/* match */").
        if isinstance(es.expr, MatchExpr):
            self._emit_match_stmt(es.expr)
            return
        # Dispatch var call: verb(args...) where verb was assigned from a dispatch lookup
        if isinstance(es.expr, CallExpr) and isinstance(es.expr.func, IdentifierExpr):
            var_name = es.expr.func.name
            if var_name in self._dispatch_vars:
                self._emit_dispatch_call(var_name, es.expr.args)
                return
        val = self._emit_expr(es.expr)
        # Suppress bare tmp variable statements from FailPropExpr
        # (the error check is already emitted as a side effect)
        if isinstance(es.expr, FailPropExpr) and val.startswith("_tmp"):
            return
        # Pure-verb call as statement: capture return value back into
        # the first argument (mutation-by-return for value types).
        # Applies to reads/creates/transforms when the return type matches
        # the first argument type.
        if isinstance(es.expr, CallExpr) and isinstance(es.expr.func, IdentifierExpr):
            sig = self._symbols.resolve_function_any(
                es.expr.func.name,
                arity=len(es.expr.args),
            )
            if (
                sig is not None
                and sig.verb in ("transforms", "derives")
                and es.expr.args
                and isinstance(es.expr.args[0], IdentifierExpr)
            ):
                # Check if any Option args have requires clauses - need to guard the call
                needs_guard = False
                for i, arg in enumerate(es.expr.args[1:], start=1):
                    if i < len(sig.param_types):
                        param_ty = sig.param_types[i]
                        if isinstance(param_ty, GenericInstance) and param_ty.base_name == "Option":
                            # Check if there's a requires clause for this param
                            if sig.requires:
                                for req in sig.requires:
                                    if isinstance(req, CallExpr):
                                        for req_arg in req.args:
                                            if (
                                                isinstance(req_arg, IdentifierExpr)
                                                and isinstance(arg, IdentifierExpr)
                                                and req_arg.name == arg.name
                                            ):
                                                needs_guard = True
                                                break
                                    if isinstance(req, ValidExpr) and req.args is not None:
                                        for req_arg in req.args:
                                            if (
                                                isinstance(req_arg, IdentifierExpr)
                                                and isinstance(arg, IdentifierExpr)
                                                and req_arg.name == arg.name
                                            ):
                                                needs_guard = True
                                                break
                if needs_guard:
                    # Emit if-check for Option args
                    arg_names = []
                    for arg in es.expr.args:
                        if isinstance(arg, IdentifierExpr):
                            arg_names.append(arg.name)
                    first_arg = es.expr.args[0].name
                    self._line("// Guarded transforms call")
                    for i, arg_name in enumerate(arg_names[1:], start=1):
                        if i < len(sig.param_types):
                            param_ty = sig.param_types[i]
                            if (
                                isinstance(param_ty, GenericInstance)
                                and param_ty.base_name == "Option"
                            ):
                                self._line(f"if ({arg_name}.tag == 1) {{")
                                self._indent += 1
                    self._line(f"{first_arg} = {val};")
                    for i, arg_name in enumerate(arg_names[1:], start=1):
                        if i < len(sig.param_types):
                            param_ty = sig.param_types[i]
                            if (
                                isinstance(param_ty, GenericInstance)
                                and param_ty.base_name == "Option"
                            ):
                                self._indent -= 1
                                self._line("}")
                    return
                first_arg = es.expr.args[0].name
                self._line(f"{first_arg} = {val};")
                return
        self._line(f"{val};")

    def _emit_dispatch_call(self, var_name: str, call_args: list) -> None:
        """Emit if-else dispatch chain for a verb variable assigned from a dispatch lookup."""
        from prove.c_types import mangle_name

        table_name, key_expr = self._dispatch_vars[var_name]
        lookup = self._lookup_tables[table_name]
        key_c = self._emit_expr(key_expr)
        args_c = [self._emit_expr(a) for a in call_args]

        first = True
        for entry in lookup.entries:
            key_val = entry.value  # the string key, e.g. "build"
            func_id = entry.variant  # the function identifier, e.g. "build"
            n_args = len(call_args)
            sig = self._symbols.resolve_function_any(func_id, arity=n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(func_id)
            c_func = (
                mangle_name(sig.verb, sig.name, sig.param_types, module=self._sig_module(sig))
                if sig and sig.verb
                else func_id
            )
            escaped = key_val.replace("\\", "\\\\").replace('"', '\\"')
            kw = "if" if first else "} else if"
            self._line(f'{kw} (prove_string_eq({key_c}, prove_string_from_cstr("{escaped}"))) {{')
            self._indent += 1
            self._line(f"{c_func}({', '.join(args_c)});")
            self._indent -= 1
            first = False
        if not first:
            self._line("}")

    def _emit_match_stmt(self, m: MatchExpr) -> None:
        """Emit a match expression as a statement (switch)."""
        if m.subject is None:
            # Implicit subject: matches/streams use first parameter,
            # listens translator uses _key, listens coroutine uses _ev, renders uses _ev
            if self._current_func is not None and self._current_func.verb in (
                "matches",
                "dispatches",
                "streams",
                "listens",
                "renders",
            ):
                if (
                    self._current_func.verb == "listens"
                    and self._current_func.state_type is not None
                ):
                    # Listens translator: match on raw key code
                    subj_name = "_key"
                elif self._current_func.verb in ("listens", "renders"):
                    subj_name = "_ev"
                elif self._current_func.params:
                    subj_name = self._current_func.params[0].name
                else:
                    subj_name = None
                if subj_name is not None:
                    implicit_subj = MatchExpr(
                        subject=IdentifierExpr(subj_name, m.span),
                        arms=m.arms,
                        span=m.span,
                    )
                    self._emit_match_stmt(implicit_subj)
                    return
            # No subject and not matches/streams/listens — emit arm bodies
            for i, arm in enumerate(m.arms):
                for s in arm.body:
                    self._emit_stmt(s)
            return

        # Save locals so match arm bindings don't leak to function scope
        saved_locals = dict(self._locals)
        subj = self._emit_expr(m.subject)
        subj_type = self._resolve_prim_type(self._infer_expr_type(m.subject))

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
                                    # In renders/listens, don't rebind state —
                                    # the outer state variable is the mutable
                                    # render state managed by the event loop.
                                    if (
                                        self._in_renders_loop or self._in_listens_loop
                                    ) and sub_pat.name in self._locals:
                                        continue
                                    fct = map_type(ft)
                                    self._locals[sub_pat.name] = ft
                                    self._line(
                                        f"{fct.decl} {sub_pat.name} = "
                                        f"{tmp}.{arm.pattern.name}.{fname};"
                                    )
                    self._emit_match_arm_body(arm.body)
                    # streams/listens/renders Exit arm must break out of the while(1) loop
                    if self._in_streams_loop and arm.pattern.name == "Exit":
                        self._line("goto _streams_exit;")
                    if self._in_listens_loop and arm.pattern.name == "Exit":
                        self._line("goto _listens_exit;")
                    if self._in_renders_loop and arm.pattern.name == "Exit":
                        self._line("goto _renders_exit;")
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
                has_variant = any(isinstance(a.pattern, VariantPattern) for a in m.arms)
                if (
                    has_variant
                    and isinstance(subj_type, GenericInstance)
                    and subj_type.base_name == "Result"
                ):
                    # Capture subject in temp to avoid re-evaluating function calls
                    tmp = self._tmp()
                    self._line(f"Prove_Result {tmp} = {subj};")
                    self._emit_result_match_stmt(m, tmp, subj_type)
                elif (
                    has_variant
                    and isinstance(subj_type, GenericInstance)
                    and subj_type.base_name == "Option"
                ):
                    self._emit_option_match_stmt(m, subj, subj_type)
                elif has_variant and isinstance(subj_type, RecordType):
                    # Record type check: first matching VariantPattern whose
                    # name matches the record type is the "true" branch,
                    # wildcard is else.
                    first = True
                    for arm in m.arms:
                        if (
                            isinstance(arm.pattern, VariantPattern)
                            and arm.pattern.name == subj_type.name
                        ):
                            # Always matches — emit as unconditional block
                            if not first:
                                self._line("} else {")
                            self._line("{")
                            self._indent += 1
                            self._emit_match_arm_body(arm.body)
                            self._indent -= 1
                            self._line("}")
                        elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                            pass  # Dead code — record always matches its own type
                        first = False
                elif self._is_lookup_match(m):
                    self._emit_lookup_switch_stmt(m, subj)
                elif self._is_integer_literal_match(m):
                    self._emit_integer_switch_stmt(m, subj)
                else:
                    self._emit_literal_match_stmt(m, subj)
        # Restore locals (match arm bindings are scoped to arms)
        self._locals = saved_locals

    def _emit_option_match_stmt(
        self,
        m: MatchExpr,
        subj: str,
        subj_type: GenericInstance,
    ) -> None:
        """Emit match on Option<Value> as if/else statement."""
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, VariantPattern):
                if arm.pattern.name == "Some":
                    keyword = "if" if first else "} else if"
                    cond = f"{subj}.tag == 1"
                    if arm.pattern.fields and isinstance(arm.pattern.fields[0], LiteralPattern):
                        inner_ty = subj_type.args[0] if subj_type.args else STRING
                        inner_ct = map_type(inner_ty)
                        cast = (
                            f"({inner_ct.decl})"
                            if inner_ct.is_pointer
                            else f"({inner_ct.decl})(intptr_t)"
                        )
                        unwrapped = f"{cast}{subj}.value"
                        inner_cond = self._emit_literal_cond(
                            unwrapped, arm.pattern.fields[0], inner_ty
                        )
                        cond = f"{cond} && {inner_cond}"
                    self._line(f"{keyword} ({cond}) {{")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(
                        arm.pattern.fields[0],
                        BindingPattern,
                    ):
                        inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                        inner_ct = map_type(inner_ty)
                        bind_name = arm.pattern.fields[0].name
                        cast = (
                            f"({inner_ct.decl})"
                            if inner_ct.is_pointer
                            else f"({inner_ct.decl})(intptr_t)"
                        )
                        if bind_name == subj:
                            # Avoid C self-init UB when binding
                            # shadows subject
                            alias = self._tmp()
                            self._line(f"{inner_ct.decl} {alias} = {cast}{subj}.value;")
                            self._line(f"{inner_ct.decl} {bind_name} = {alias};")
                        else:
                            self._line(f"{inner_ct.decl} {bind_name} = {cast}{subj}.value;")
                        self._locals[bind_name] = inner_ty
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
                elif arm.pattern.name == "None":
                    if first:
                        self._line("{")
                    else:
                        self._line("} else {")
                    self._indent += 1
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
                    self._line("}")
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            first = False
        # Close if last arm wasn't wildcard/None
        if m.arms and not isinstance(
            m.arms[-1].pattern,
            (WildcardPattern, BindingPattern),
        ):
            last_pat = m.arms[-1].pattern
            if not (isinstance(last_pat, VariantPattern) and last_pat.name == "None"):
                self._line("}")

    def _emit_result_match_stmt(
        self,
        m: MatchExpr,
        subj: str,
        subj_type: GenericInstance,
    ) -> None:
        """Emit match on Result<Value, Error> as if/else on prove_result_is_err."""
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, VariantPattern):
                if arm.pattern.name == "Ok":
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} (!prove_result_is_err({subj})) {{")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(
                        arm.pattern.fields[0],
                        BindingPattern,
                    ):
                        inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                        inner_ct = map_type(inner_ty)
                        bind_name = arm.pattern.fields[0].name
                        # Use temp to avoid shadowing when bind_name == subj
                        tmp = self._tmp()
                        if inner_ct.is_pointer:
                            self._line(f"{inner_ct.decl} {tmp} = ({inner_ct.decl}){subj}.value;")
                        elif inner_ct.decl == "double":
                            self._line(
                                f"{inner_ct.decl} {tmp} = prove_result_unwrap_double({subj});"
                            )
                        else:
                            self._line(
                                f"{inner_ct.decl} {tmp} = ({inner_ct.decl})(intptr_t){subj}.value;"
                            )
                        self._line(f"{inner_ct.decl} {bind_name} = {tmp};")
                        self._locals[bind_name] = inner_ty
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
                elif arm.pattern.name in ("Err", "Error"):
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} (prove_result_is_err({subj})) {{")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(
                        arm.pattern.fields[0],
                        BindingPattern,
                    ):
                        bind_name = arm.pattern.fields[0].name
                        # Use temp to avoid shadowing when bind_name == subj
                        tmp = self._tmp()
                        self._line(f"Prove_String* {tmp} = {subj}.error;")
                        self._line(f"Prove_String* {bind_name} = {tmp};")
                        self._locals[bind_name] = STRING
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            first = False
        # Close the trailing if/else-if chain
        if m.arms and not isinstance(
            m.arms[-1].pattern,
            (WildcardPattern, BindingPattern),
        ):
            self._line("}")

    def _emit_match_arm_body(self, body: list) -> None:
        """Emit match arm body, handling TailContinue and returns in tail loop."""
        for i, s in enumerate(body):
            is_last = i == len(body) - 1
            # Error("msg") in failable function → early return with error
            if is_last and getattr(self._current_func, "can_fail", False):
                expr = self._stmt_expr(s)
                if (
                    isinstance(expr, CallExpr)
                    and isinstance(expr.func, TypeIdentifierExpr)
                    and expr.func.name == "Error"
                    and len(expr.args) == 1
                ):
                    arg = expr.args[0]
                    if isinstance(arg, StringLit):
                        ref = self._static_error_ref(self._escape_c_string(arg.value))
                        self._line(f"return prove_result_err({ref});")
                    else:
                        err_val = self._emit_expr(arg)
                        self._line(f"return prove_result_err({err_val});")
                    return
            if isinstance(s, TailContinue):
                self._emit_tail_continue(s)
            elif is_last and self._in_tail_loop and not isinstance(s, TailContinue):
                # Base case in tail loop — emit as return, unless it's a nested
                # match (which may itself contain TailContinue nodes and should
                # be emitted as a statement rather than a return expression).
                expr = self._stmt_expr(s)
                if expr is not None and not isinstance(expr, MatchExpr):
                    self._emit_region_exit()
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(s)
            else:
                self._emit_stmt(s)

    def _emit_tail_match_as_if_else(self, m: MatchExpr, subj: str) -> None:
        """Emit a non-algebraic match as if/else inside a tail loop."""
        subj_type = self._infer_expr_type(m.subject) if m.subject else UNIT
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    bct = map_type(subj_type)
                    self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, LiteralPattern):
                cond = self._emit_literal_cond(subj, arm.pattern, subj_type, m.subject)
                keyword = "if" if first else "} else if"
                self._line(f"{keyword} ({cond}) {{")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
            first = False
        # Close trailing if without else
        if m.arms and not isinstance(m.arms[-1].pattern, (WildcardPattern, BindingPattern)):
            self._line("}")

    # ── Integer switch and literal match emission ─────────────────

    def _is_integer_literal_match(self, m: MatchExpr) -> bool:
        """Check if a match can be emitted as a C switch statement.

        Requires: all arms are integer literal patterns, optionally with
        a single wildcard/binding pattern as default.
        """
        has_literal = False
        for arm in m.arms:
            if isinstance(arm.pattern, LiteralPattern):
                if arm.pattern.kind not in ("integer", None):
                    return False
                has_literal = True
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                continue  # Wildcard becomes default
            else:
                return False
        return has_literal

    def _emit_integer_switch_stmt(self, m: MatchExpr, subj: str) -> None:
        """Emit a match on integer literals as a C switch statement."""
        self._line(f"switch ({subj}) {{")
        for arm in m.arms:
            if isinstance(arm.pattern, LiteralPattern):
                self._line(f"case {arm.pattern.value}L: {{")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._line("break;")
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                self._line("default: {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    subj_type = self._infer_expr_type(m.subject) if m.subject else None
                    if subj_type:
                        bct = map_type(subj_type)
                        self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                self._emit_match_arm_body(arm.body)
                self._line("break;")
                self._indent -= 1
                self._line("}")
        self._line("}")

    # ── LookupPattern match emission ─────────────────────────────

    def _is_lookup_match(self, m: MatchExpr) -> bool:
        """Check if a match has LookupPattern arms (e.g. Key:Escape, Key:"k")."""
        return any(isinstance(a.pattern, LookupPattern) for a in m.arms)

    def _lookup_case_value(self, pat: LookupPattern) -> str | None:
        """Resolve a LookupPattern to an integer case value for switch emission.

        Key:Escape → "27" (from lookup table integer column)
        Key:"k"   → "(int64_t)'k'" (ASCII value)
        Key:Space  → "32" (from lookup table integer column)
        """
        lookup = self._lookup_tables.get(pat.type_name)
        if pat.value_kind == "string":
            # String literal — single char becomes ASCII case value
            if len(pat.lookup_value) == 1:
                return f"(int64_t)'{pat.lookup_value}'"
            return None
        # Identifier — look up variant name in lookup table
        if lookup is not None:
            for entry in lookup.entries:
                if entry.variant == pat.lookup_value:
                    # Multi-column lookup: integer value is in entry.values
                    if entry.values:
                        for val, kind in zip(entry.values, entry.value_kinds):
                            if kind == "integer":
                                return val
                    # Single-column: value itself may be integer
                    if entry.value_kind == "integer":
                        return entry.value
                    break
        return None

    def _emit_lookup_switch_stmt(self, m: MatchExpr, subj: str) -> None:
        """Emit a match with LookupPattern arms as a C switch statement."""
        self._line(f"switch ({subj}) {{")
        for arm in m.arms:
            if isinstance(arm.pattern, LookupPattern):
                case_val = self._lookup_case_value(arm.pattern)
                if case_val is not None:
                    self._line(f"case {case_val}: {{")
                    self._indent += 1
                    self._emit_match_arm_body(arm.body)
                    if self._in_listens_loop and arm.pattern.lookup_value == "Escape":
                        # Exit via Escape in listens — handled by return in arm body
                        pass
                    self._line("break;")
                    self._indent -= 1
                    self._line("}")
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                self._line("default: {")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._line("break;")
                self._indent -= 1
                self._line("}")
        self._line("}")

    def _emit_literal_match_stmt(self, m: MatchExpr, subj: str) -> None:
        """Emit a match on non-integer literals as an if-else chain."""
        subj_type = self._infer_expr_type(m.subject) if m.subject else None
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    if subj_type:
                        bct = map_type(subj_type)
                        self._line(f"{bct.decl} {arm.pattern.name} = {subj};")
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
                self._line("}")
            elif isinstance(arm.pattern, VariantPattern):
                # Some/None on pointer type — emit as null check
                if arm.pattern.name == "Some":
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} ({subj} != NULL) {{")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(arm.pattern.fields[0], BindingPattern):
                        if subj_type:
                            bct = map_type(subj_type)
                            self._line(f"{bct.decl} {arm.pattern.fields[0].name} = {subj};")
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
                elif arm.pattern.name == "None":
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} ({subj} == NULL) {{")
                    self._indent += 1
                    self._emit_match_arm_body(arm.body)
                    self._indent -= 1
            elif isinstance(arm.pattern, LiteralPattern):
                # For boolean matches (true/false), the second arm should use
                # plain `else` to avoid re-evaluating the subject expression
                # (important for side-effectful subjects like GUI widget calls).
                is_bool_complement = (
                    not first
                    and arm.pattern.value in ("true", "false")
                    and isinstance(subj_type, PrimitiveType)
                    and subj_type.name == "Boolean"
                )
                if is_bool_complement:
                    self._line("} else {")
                else:
                    cond = self._emit_literal_cond(subj, arm.pattern, subj_type, m.subject)
                    keyword = "if" if first else "} else if"
                    self._line(f"{keyword} ({cond}) {{")
                self._indent += 1
                self._emit_match_arm_body(arm.body)
                self._indent -= 1
            first = False
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
                    self._emit_region_exit()
                    self._line(f"return {self._emit_expr(expr)};")
                else:
                    self._emit_stmt(stmt)
            else:
                self._emit_stmt(stmt)
        self._indent -= 1
        self._line("}")
        self._in_tail_loop = saved_in_tail

    def _emit_tail_continue(self, tc: TailContinue) -> None:
        """Emit param reassignments for tail-call loop iteration.

        Skips temporaries when no cross-dependencies exist between params.
        Omits redundant 'continue' since TailContinue always appears at the
        end of a while(1) body branch.
        """
        if self._needs_temporaries(tc):
            # Cross-dependencies between params: use temps to avoid order bugs
            tmps: list[tuple[str, str]] = []
            for param_name, new_val_expr in tc.assignments:
                tmp = self._tmp()
                ty = self._locals.get(param_name)
                ct = map_type(ty) if ty else CType("int64_t", False, None)
                val = self._emit_expr(new_val_expr)
                self._line(f"{ct.decl} {tmp} = {val};")
                tmps.append((param_name, tmp))
            for param_name, tmp in tmps:
                self._line(f"{param_name} = {tmp};")
        else:
            # No cross-dependencies: assign directly without temporaries
            for param_name, new_val_expr in tc.assignments:
                val = self._emit_expr(new_val_expr)
                self._line(f"{param_name} = {val};")

    @staticmethod
    def _expr_refs_any(expr: Any, names: set[str]) -> bool:
        """Check if an expression references any of the given variable names."""
        from prove.ast_nodes import (
            BinaryExpr,
            CallExpr,
            IdentifierExpr,
            IndexExpr,
            UnaryExpr,
        )

        if isinstance(expr, IdentifierExpr):
            return expr.name in names
        if isinstance(expr, BinaryExpr):
            return StmtEmitterMixin._expr_refs_any(
                expr.left, names
            ) or StmtEmitterMixin._expr_refs_any(expr.right, names)
        if isinstance(expr, UnaryExpr):
            return StmtEmitterMixin._expr_refs_any(expr.operand, names)
        if isinstance(expr, CallExpr):
            return any(StmtEmitterMixin._expr_refs_any(a, names) for a in expr.args)
        if isinstance(expr, IndexExpr):
            return StmtEmitterMixin._expr_refs_any(
                expr.obj, names
            ) or StmtEmitterMixin._expr_refs_any(expr.index, names)
        return False

    def _needs_temporaries(self, tc: TailContinue) -> bool:
        """Check if TailContinue assignments have cross-dependencies.

        Temporaries are needed when param A's new value expression references
        param B, and param B is also being reassigned.
        """
        assigned_params = {name for name, _ in tc.assignments}
        for param_name, new_val_expr in tc.assignments:
            # Check if expr references any OTHER param being reassigned
            other_params = assigned_params - {param_name}
            if other_params and self._expr_refs_any(new_val_expr, other_params):
                return True
        return False

    def _emit_while_loop(self, wl: WhileLoop) -> None:
        """Emit a finite while loop inlined from a TCO'd function."""
        cond = self._emit_expr(wl.break_cond)
        self._line(f"while (!({cond})) {{")
        self._indent += 1
        for s in wl.body:
            self._emit_stmt(s)
        self._indent -= 1
        self._line("}")
