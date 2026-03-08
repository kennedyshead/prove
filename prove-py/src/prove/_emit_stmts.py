"""Statement emission mixin for CEmitter."""

from __future__ import annotations

from prove.ast_nodes import (
    Assignment,
    BindingPattern,
    CallExpr,
    CommentStmt,
    ExplainEntry,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FunctionDef,
    IdentifierExpr,
    LiteralPattern,
    MatchExpr,
    RawStringLit,
    RegexLit,
    Stmt,
    TailContinue,
    TailLoop,
    ValidExpr,
    VarDecl,
    VariantPattern,
    WildcardPattern,
)
from prove.c_types import CType, mangle_type_name, map_type
from prove.types import (
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    UnitType,
)


class StmtEmitterMixin:

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
                elif is_failable:
                    # For failable functions, wrap last expression in result_ok
                    if isinstance(ret_type, GenericInstance) and ret_type.base_name == "Result":
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
                            ret_tmp = self._tmp()
                            ret_ct = map_type(ret_type)
                            self._line(f"{ret_ct.decl} {ret_tmp} = {self._emit_expr(expr)};")
                            self._emit_releases(ret_tmp)
                            self._emit_region_exit()
                            if isinstance(ret_type, RecordType):
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
                            elif isinstance(ret_type, GenericInstance) and not ret_ct.is_pointer:
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
                        # For validates functions returning bool: if returning an Option,
                        # check if it's Some (tag == 1)
                        emit_val = self._emit_expr(expr)
                        if isinstance(ret_type, PrimitiveType) and ret_type.name == "Boolean":
                            expr_type = self._infer_expr_type(expr)
                            if (
                                isinstance(expr_type, GenericInstance)
                                and expr_type.base_name == "Option"
                            ):
                                if isinstance(expr, IdentifierExpr):
                                    emit_val = f"{expr.name}.tag == 1"
                        self._line(f"{ret_ct.decl} {ret_tmp} = {emit_val};")
                        self._emit_releases(ret_tmp)
                        self._emit_region_exit()
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
        elif isinstance(stmt, MatchExpr):
            self._emit_match_stmt(stmt)
        elif isinstance(stmt, CommentStmt):
            pass  # comments don't emit C code

    def _emit_var_decl(self, vd: VarDecl) -> None:
        # Determine target type: from annotation if present, else from value
        target_ty = self._infer_expr_type(vd.value)
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
                elif type_args and type_name in ("Table", "Option", "Result"):
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
        value_ty = self._infer_expr_type(vd.value)
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
                self._line(f"{tgt_ct.decl} {vd.name};")
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
                        f"{vd.name} = prove_option_some((Prove_Value*)(intptr_t)prove_result_unwrap_int({cv_tmp}));"
                    )
                    self._line(f"else {vd.name} = prove_option_none();")
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
                            target_inner_type,  # type: ignore[arg-type]
                            tgt_ct.decl,
                            vd.name,
                        )
                    else:
                        self._line(
                            f"{vd.name} = prove_option_some({raw_tmp}.value);"
                        )
                self._indent -= 1
                self._line("} else {")
                self._indent += 1
                self._line(f"{vd.name} = prove_option_none();")
                self._indent -= 1
                self._line("}")
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
        val = self._emit_expr(vd.value)
        self._expected_emit_type = None

        if needs_unwrap:
            # For failable function returning Result, unwrap before assignment
            tmp = self._tmp()
            self._line(f"Prove_Result {tmp} = {val};")
            # Check for error - panic if non-failable function, return error if failable
            is_failable = (
                getattr(self._current_func, "can_fail", False) if self._current_func else False
            )
            if self._in_main:
                err_str = self._tmp()
                self._line(f"if (prove_result_is_err({tmp})) {{")
                self._indent += 1
                self._line(f"Prove_String *{err_str} = (Prove_String*){tmp}.error;")
                self._line(
                    f"if ({err_str}) fprintf(stderr,"
                    f' "error: %.*s\\n",'
                    f" (int){err_str}->length,"
                    f" {err_str}->data);"
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
                self._line(f'if (prove_result_is_err({tmp})) prove_panic("IO error");')
            # Unwrap the success value
            if isinstance(target_ty, RecordType):
                self._line(f"{ct.decl} {vd.name} = *(({ct.decl}*)prove_result_unwrap_ptr({tmp}));")
            elif ct.is_pointer:
                self._line(f"{ct.decl} {vd.name} = ({ct.decl})prove_result_unwrap_ptr({tmp});")
            elif ct.decl == "double":
                self._line(f"{ct.decl} {vd.name} = prove_result_unwrap_double({tmp});")
            elif isinstance(target_ty, GenericInstance) and not ct.is_pointer:
                # Struct-like GenericInstance (Option<Value>, etc.)
                self._line(f"{ct.decl} {vd.name} = *(({ct.decl}*)prove_result_unwrap_ptr({tmp}));")
            else:
                # For integer types
                self._line(f"{ct.decl} {vd.name} = prove_result_unwrap_int({tmp});")
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
                        self._line(f"{ct.decl} {vd.name} = prove_option_some((Prove_Value*){val});")
                    else:
                        self._line(f"{ct.decl} {vd.name} = prove_option_some((Prove_Value*)(intptr_t){val});")
            else:
                self._line(f"{ct.decl} {vd.name} = {val};")

        # Validate refinement type constraints
        # Skip validation for GenericInstance (Option<Value>) because validation is already
        # done in the conversion code. Only validate direct RefinementType assignments.
        if not isinstance(target_ty, GenericInstance):
            check_ty = target_ty
            validation_var = vd.name
            if isinstance(check_ty, RefinementType) and check_ty.constraint:
                self._emit_refinement_validation(validation_var, check_ty)

        # Update locals with target type
        self._locals[vd.name] = target_ty
        # Retain pointer types
        if ct.is_pointer:
            self._line(f"prove_retain({vd.name});")

    def _emit_refinement_validation(self, var_name: str, target_ty: RefinementType) -> None:
        """Emit runtime validation for refinement type constraints."""
        constraint = target_ty.constraint
        if constraint is None:
            return

        if isinstance(constraint, RegexLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.pattern.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
            )
            self._indent += 1
            self._line('prove_panic("constraint failed: value does not match pattern");')
            self._indent -= 1
            self._line("}")
        elif isinstance(constraint, RawStringLit):
            self._needed_headers.add("prove_pattern.h")
            escaped_pattern = constraint.value.replace("\\", "\\\\")
            self._line(
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
            )
            self._indent += 1
            self._line('prove_panic("constraint failed: value does not match pattern");')
            self._indent -= 1
            self._line("}")

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
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
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
                f'if (!prove_pattern_match({var_name}, prove_string_from_cstr("{escaped_pattern}"))) {{'
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

    def _emit_assignment(self, assign: Assignment) -> None:
        val = self._emit_expr(assign.value)
        self._line(f"{assign.target} = {val};")

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
        val = self._emit_expr(es.expr)
        # Suppress bare tmp variable statements from FailPropExpr
        # (the error check is already emitted as a side effect)
        if isinstance(es.expr, FailPropExpr) and val.startswith("_tmp"):
            return
        # Transforms call as statement: capture return value back into
        # the first argument (mutation-by-return for value types).
        if isinstance(es.expr, CallExpr) and isinstance(es.expr.func, IdentifierExpr):
            sig = self._symbols.resolve_function_any(
                es.expr.func.name,
                arity=len(es.expr.args),
            )
            if (
                sig is not None
                and sig.verb == "transforms"
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
                has_variant = any(isinstance(a.pattern, VariantPattern) for a in m.arms)
                if (
                    has_variant
                    and isinstance(subj_type, GenericInstance)
                    and subj_type.base_name == "Result"
                ):
                    self._emit_result_match_stmt(m, subj, subj_type)
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
                    self._line(f"{keyword} ({subj}.tag == 1) {{")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(
                        arm.pattern.fields[0],
                        BindingPattern,
                    ):
                        inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                        inner_ct = map_type(inner_ty)
                        bind_name = arm.pattern.fields[0].name
                        cast = f"({inner_ct.decl})" if inner_ct.is_pointer else f"({inner_ct.decl})(intptr_t)"
                        if bind_name == subj:
                            # Avoid C self-init UB when binding
                            # shadows subject
                            alias = self._tmp()
                            self._line(f"{inner_ct.decl} {alias} = {cast}{subj}.value;")
                            self._line(f"{inner_ct.decl} {bind_name} = {alias};")
                        else:
                            self._line(
                                f"{inner_ct.decl} {bind_name} = {cast}{subj}.value;"
                            )
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
                            self._line(
                                f"{inner_ct.decl} {tmp} = ({inner_ct.decl}){subj}.value;"
                            )
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
                elif arm.pattern.name == "Err":
                    if first:
                        self._line(f"if (prove_result_is_err({subj})) {{")
                    else:
                        self._line("} else {")
                    self._indent += 1
                    if arm.pattern.fields and isinstance(
                        arm.pattern.fields[0],
                        BindingPattern,
                    ):
                        bind_name = arm.pattern.fields[0].name
                        # Use temp to avoid shadowing when bind_name == subj
                        tmp = self._tmp()
                        self._line(
                            f"Prove_String* {tmp} = {subj}.error;"
                        )
                        self._line(f"Prove_String* {bind_name} = {tmp};")
                        self._locals[bind_name] = STRING
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
        # Close if last arm wasn't wildcard/Err
        if m.arms and not isinstance(
            m.arms[-1].pattern,
            (WildcardPattern, BindingPattern),
        ):
            last_pat = m.arms[-1].pattern
            if not (isinstance(last_pat, VariantPattern) and last_pat.name == "Err"):
                self._line("}")

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
                    self._emit_region_exit()
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
                    # String or boolean literals can't use switch
                    try:
                        int(arm.pattern.value)
                    except (ValueError, TypeError):
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

    def _emit_literal_match_stmt(self, m: MatchExpr, subj: str) -> None:
        """Emit a match on non-integer literals as an if-else chain."""
        first = True
        for arm in m.arms:
            if isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                if first:
                    self._line("{")
                else:
                    self._line("} else {")
                self._indent += 1
                if isinstance(arm.pattern, BindingPattern):
                    subj_type = self._infer_expr_type(m.subject) if m.subject else None
                    if subj_type:
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
