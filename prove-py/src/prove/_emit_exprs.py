"""Expression emission mixin for CEmitter."""

from __future__ import annotations

from prove.ast_nodes import (
    AsyncCallExpr,
    BinaryExpr,
    BinaryLookupExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    ComptimeExpr,
    DecimalLit,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
    FloatLit,
    IdentifierExpr,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    MatchExpr,
    PathLit,
    PipeExpr,
    RawStringLit,
    RegexLit,
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VariantPattern,
    WildcardPattern,
)
from prove.c_types import mangle_name, mangle_type_name, map_type
from prove.type_inference import BUILTIN_MAP
from prove.types import (
    ERROR_TY,
    INTEGER,
    UNIT,
    AlgebraicType,
    ErrorType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    Type,
    UnitType,
)


class ExprEmitterMixin:
    def _emit_expr(self, expr: Expr) -> str:
        if isinstance(expr, IntegerLit):
            return f"{expr.value}L"

        if isinstance(expr, DecimalLit):
            return expr.value

        if isinstance(expr, FloatLit):
            return expr.value

        if isinstance(expr, BooleanLit):
            return "true" if expr.value else "false"

        if isinstance(expr, CharLit):
            return f"'{expr.value}'"

        if isinstance(expr, PathLit):
            escaped = self._escape_c_string(expr.value)
            if self._in_hof_inline and escaped in self._string_literal_cache:
                return self._string_literal_cache[escaped]
            if self._use_region_allocation():
                return f'prove_string_from_cstr_region({self._get_region_ptr()}, "{escaped}")'
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, StringLit):
            escaped = self._escape_c_string(expr.value)
            if self._in_hof_inline and escaped in self._string_literal_cache:
                return self._string_literal_cache[escaped]
            if self._use_region_allocation():
                return f'prove_string_from_cstr_region({self._get_region_ptr()}, "{escaped}")'
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, TripleStringLit):
            escaped = self._escape_c_string(expr.value)
            if self._in_hof_inline and escaped in self._string_literal_cache:
                return self._string_literal_cache[escaped]
            if self._use_region_allocation():
                return f'prove_string_from_cstr_region({self._get_region_ptr()}, "{escaped}")'
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, RawStringLit):
            escaped = self._escape_c_string(expr.value)
            if self._in_hof_inline and escaped in self._string_literal_cache:
                return self._string_literal_cache[escaped]
            if self._use_region_allocation():
                return f'prove_string_from_cstr_region({self._get_region_ptr()}, "{escaped}")'
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, RegexLit):
            escaped = self._escape_c_string(expr.value)
            if self._use_region_allocation():
                return f'prove_string_from_cstr_region({self._get_region_ptr()}, "{escaped}")'
            return f'prove_string_from_cstr("{escaped}")'

        if isinstance(expr, StringInterp):
            return self._emit_string_interp(expr)

        if isinstance(expr, ListLiteral):
            return self._emit_list_literal(expr)

        if isinstance(expr, IdentifierExpr):
            # Check if this identifier is an outputs function with no args (zero-arg call)
            sig = self._symbols.resolve_function("outputs", expr.name, 0)
            if sig is None:
                sig = self._symbols.resolve_function_any(expr.name, arity=0)
            if sig and sig.verb == "outputs" and sig.module:
                c_name = self._resolve_stdlib_c_name(sig)
                if c_name:
                    return f"{c_name}()"
            return expr.name

        if isinstance(expr, TypeIdentifierExpr):
            if expr.name == "Unit":
                return "(void)0"
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

        if isinstance(expr, AsyncCallExpr):
            return self._emit_async_call(expr)

        if isinstance(expr, MatchExpr):
            return self._emit_match_expr(expr)

        if isinstance(expr, LambdaExpr):
            return self._emit_lambda(expr)

        if isinstance(expr, IndexExpr):
            return self._emit_index(expr)

        if isinstance(expr, LookupAccessExpr):
            return self._emit_lookup_access(expr)

        if isinstance(expr, BinaryLookupExpr):
            return self._emit_binary_lookup_expr(expr)

        if isinstance(expr, StoreLookupExpr):
            return self._emit_store_lookup_expr(expr)

        if isinstance(expr, ValidExpr):
            # Prefer validates verb since valid X(...) means validates
            n = len(expr.args) if expr.args is not None else 0
            sig = self._symbols.resolve_function("validates", expr.name, n)
            if sig is None:
                sig = self._symbols.resolve_function_any(expr.name, arity=n)
            if expr.args is not None:
                # valid error(x) -> call the validates function
                args_c = ", ".join(self._emit_expr(a) for a in expr.args)
                # Check stdlib C name first
                if sig and sig.module:
                    c_name = self._resolve_stdlib_c_name(sig, expr.args, verb_override="validates")
                    if c_name:
                        return f"{c_name}({args_c})"
                pt = list(sig.param_types) if sig else None
                fn = mangle_name("validates", expr.name, pt)
                return f"{fn}({args_c})"
            # valid error -> function reference (used as HOF predicate)
            if sig and sig.module:
                c_name = self._resolve_stdlib_c_name(sig, verb_override="validates")
                if c_name:
                    return c_name
            pt = list(sig.param_types) if sig else None
            return mangle_name("validates", expr.name, pt)

        if isinstance(expr, ComptimeExpr):
            result = self._eval_comptime(type("const", (), {"span": expr.span})(), expr)
            if result is not None:
                return self._comptime_result_to_c(result)
            return "/* comptime failed */ 0"

        return "/* unsupported expr */ 0"

    # -- Binary expressions -----------------------------------------

    def _emit_binary(self, expr: BinaryExpr) -> str:
        left = self._emit_expr(expr.left)
        right = self._emit_expr(expr.right)

        # Unwrap Option operands when the other side is the inner type
        lt = self._infer_expr_type(expr.left)
        rt = self._infer_expr_type(expr.right)
        left = self._maybe_unwrap_option_value(left, lt, rt)
        right = self._maybe_unwrap_option_value(right, rt, lt)
        # Re-infer after unwrap for downstream checks
        if isinstance(lt, GenericInstance) and lt.base_name == "Option" and lt.args:
            lt_eff = lt.args[0]
        else:
            lt_eff = lt

        # String concatenation
        if expr.op == "+":
            if isinstance(lt_eff, PrimitiveType) and lt_eff.name == "String":
                if self._c_returns_value_ptr(expr.left):
                    left = f"prove_value_as_text({left})"
                if self._c_returns_value_ptr(expr.right):
                    right = f"prove_value_as_text({right})"
                return f"prove_string_concat({left}, {right})"

        # String equality
        if expr.op == "==" or expr.op == "!=":
            if isinstance(lt_eff, PrimitiveType) and lt_eff.name == "String":
                if self._c_returns_value_ptr(expr.left):
                    left = f"prove_value_as_text({left})"
                if self._c_returns_value_ptr(expr.right):
                    right = f"prove_value_as_text({right})"
                eq = f"prove_string_eq({left}, {right})"
                return eq if expr.op == "==" else f"(!{eq})"
            # Algebraic type tag comparison: severity == Error -> .tag == TAG
            if isinstance(lt_eff, AlgebraicType) and isinstance(expr.right, TypeIdentifierExpr):
                cname = mangle_type_name(lt_eff.name)
                tag = f"{cname}_TAG_{expr.right.name.upper()}"
                cmp = "==" if expr.op == "==" else "!="
                return f"({left}.tag {cmp} {tag})"

        # Map Prove operators to C
        from prove.type_inference import BINARY_OP_TO_C

        c_op = BINARY_OP_TO_C.get(expr.op, expr.op)

        # Runtime division-by-zero guard for integer / and %
        if expr.op in ("/", "%") and not isinstance(expr.right, IntegerLit):
            if isinstance(lt_eff, PrimitiveType) and lt_eff.name == "Integer":
                if not self._divisor_covered_by_requires(expr.right):
                    tmp = self._tmp()
                    self._line(f"int64_t {tmp} = {right};")
                    self._line("#ifndef PROVE_RELEASE")
                    self._line(f'if ({tmp} == 0) prove_panic("division by zero");')
                    self._line("#endif")
                    return f"({left} {c_op} {tmp})"

        return f"({left} {c_op} {right})"

    def _divisor_covered_by_requires(self, divisor_expr: Expr) -> bool:
        """Check if a divisor is covered by a requires clause (e.g. requires b != 0)."""
        if not self._current_requires:
            return False
        if not isinstance(divisor_expr, IdentifierExpr):
            return False
        name = divisor_expr.name
        for req in self._current_requires:
            if not isinstance(req, BinaryExpr):
                continue
            # Match patterns: param != 0, param > 0, 0 != param, 0 < param
            left_is_name = (
                isinstance(req.left, IdentifierExpr) and req.left.name == name
            )
            right_is_name = (
                isinstance(req.right, IdentifierExpr) and req.right.name == name
            )
            if req.op in ("!=", ">") and left_is_name:
                if isinstance(req.right, IntegerLit) and req.right.value == "0":
                    return True
            if req.op in ("!=", "<") and right_is_name:
                if isinstance(req.left, IntegerLit) and req.left.value == "0":
                    return True
        return False

    # -- Unary expressions ------------------------------------------

    def _emit_unary(self, expr: UnaryExpr) -> str:
        operand = self._emit_expr(expr.operand)
        if expr.op == "!":
            return f"(!{operand})"
        if expr.op == "-":
            return f"(-{operand})"
        return operand

    # -- String conversion helper -----------------------------------

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
                return ""  # identity -- shouldn't happen
        return "prove_string_from_int"  # fallback

    # -- Loop body retains ------------------------------------------

    def _emit_loop_body_retains(self, body: Expr, loop_param: str) -> None:
        """Emit prove_retain for captured pointer vars passed to calls in a loop.

        The callee releases its parameters, but loop-invariant captured
        variables are reused on every iteration, so we must retain them
        before each call to keep the refcount balanced.
        """
        if not isinstance(body, CallExpr):
            return
        for arg in body.args:
            if isinstance(arg, IdentifierExpr) and arg.name != loop_param:
                ty = self._locals.get(arg.name)
                if ty and map_type(ty).is_pointer:
                    # Skip retain for non-escaping vars in release mode
                    if self._release_mode and self._escape_info is not None:
                        func_name = self._get_current_function_name()
                        if func_name and not self._escape_info.escapes(func_name, arg.name):
                            continue
                    self._line(f"prove_retain({arg.name});")

    # -- Field expressions ------------------------------------------

    def _emit_field(self, expr: FieldExpr) -> str:
        # Named column access on binary lookup: Prediction:Cat.probability
        from prove.ast_nodes import LookupAccessExpr, LookupTypeDef
        from prove.c_types import mangle_type_name

        if isinstance(expr.obj, LookupAccessExpr):
            lookup = self._lookup_tables.get(expr.obj.type_name)
            if (
                lookup is not None
                and isinstance(lookup, LookupTypeDef)
                and lookup.is_binary
                and lookup.column_names
            ):
                field = expr.field
                for i, cn in enumerate(lookup.column_names):
                    if cn == field and i < len(lookup.value_types):
                        lcname = mangle_type_name(expr.obj.type_name)
                        array_name = f"{lcname}_col_{cn}"
                        # Get the variant index from the operand
                        inner = self._emit_expr(expr.obj)
                        col_type = (
                            lookup.value_types[i].name
                            if hasattr(lookup.value_types[i], "name")
                            else "String"
                        )
                        if col_type == "String":
                            return f"prove_string_from_cstr({array_name}[{inner}])"
                        return f"{array_name}[{inner}]"

        obj = self._emit_expr(expr.obj)
        obj_type = self._infer_expr_type(expr.obj)
        if isinstance(obj_type, (RecordType, AlgebraicType)):
            return f"{obj}.{expr.field}"
        # Table field access: prove_table_get
        if isinstance(obj_type, GenericInstance) and obj_type.base_name == "Table":
            val_type = obj_type.args[0] if obj_type.args else INTEGER
            val_ct = map_type(val_type)
            get_expr = f'prove_table_get(prove_string_from_cstr("{expr.field}"), {obj})'
            unwrap = f"prove_option_unwrap({get_expr})"
            if val_ct.is_pointer:
                return f"({val_ct.decl}){unwrap}"
            if val_ct.decl == "int64_t":
                return f"prove_value_to_number({unwrap})"
            if val_ct.decl == "double":
                return f"prove_value_to_decimal({unwrap})"
            if val_ct.decl == "bool":
                return f"prove_value_to_bool({unwrap})"
            return f"({val_ct.decl}){unwrap}"
        # Pointer types use ->
        ct = map_type(obj_type)
        if ct.is_pointer:
            return f"{obj}->{expr.field}"
        return f"{obj}.{expr.field}"

    # -- Pipe expressions -------------------------------------------

    def _emit_pipe(self, expr: PipeExpr) -> str:
        left = self._emit_expr(expr.left)

        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            if name in BUILTIN_MAP:
                return f"{BUILTIN_MAP[name]}({left})"
            sig = self._symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=1,
                )
            if sig:
                coerced = self._coerce_call_args([left], [expr.left], sig)
                left = coerced[0]
            if sig and sig.module:
                c_name = self._resolve_stdlib_c_name(sig)
                if c_name:
                    return f"{c_name}({left})"
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({left})"
            return f"{name}({left})"

        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            name = expr.right.func.name
            # Route HOF builtins through the dedicated HOF emitters
            if name in ("map", "filter", "reduce", "each"):
                synthetic = CallExpr(
                    func=expr.right.func,
                    args=[expr.left] + list(expr.right.args),
                    span=expr.span,
                )
                if name == "map":
                    return self._emit_hof_map(synthetic)
                if name == "filter":
                    return self._emit_hof_filter(synthetic)
                if name == "reduce":
                    return self._emit_hof_reduce(synthetic)
                return self._emit_hof_each(synthetic)
            extra_args = [self._emit_expr(a) for a in expr.right.args]
            all_args = [left] + extra_args
            if name in BUILTIN_MAP:
                return f"{BUILTIN_MAP[name]}({', '.join(all_args)})"
            total = 1 + len(expr.right.args)
            sig = self._symbols.resolve_function(None, name, total)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=total,
                )
            if sig:
                all_arg_exprs = [expr.left] + list(expr.right.args)
                all_args = self._coerce_call_args(all_args, all_arg_exprs, sig)
            if sig and sig.module:
                c_name = self._resolve_stdlib_c_name(sig)
                if c_name:
                    return f"{c_name}({', '.join(all_args)})"
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                return f"{mangled}({', '.join(all_args)})"
            return f"{name}({', '.join(all_args)})"

        right = self._emit_expr(expr.right)
        return f"{right}({left})"

    # -- Fail propagation -------------------------------------------

    def _emit_fail_prop(self, expr: FailPropExpr) -> str:
        self._line("")
        tmp = self._named_tmp("result")
        inner = self._emit_expr(expr.expr)
        self._line(f"Prove_Result {tmp} = {inner};")
        if self._in_main:
            self._line(f"if (prove_result_is_err({tmp})) {{")
            self._indent += 1
            err_str = self._named_tmp("error")
            self._line(f"Prove_String *{err_str} = (Prove_String*){tmp}.error;")
            self._line(
                f"fprintf(stderr,"
                f' "error: %.*s\\n",'
                f" (int){err_str}->length,"
                f" {err_str}->data);"
            )
            self._line("prove_runtime_cleanup();")
            self._line("return 1;")
            self._indent -= 1
            self._line("}")
        elif self._in_streams_loop:
            # streams functions are void — break out of the loop on error
            self._line(f"if (prove_result_is_err({tmp})) goto _streams_exit;")
        else:
            if self._in_region_scope:
                self._line(f"if (prove_result_is_err({tmp})) {{")
                self._indent += 1
                self._line("prove_region_exit(prove_global_region());")
                self._line(f"return {tmp};")
                self._indent -= 1
                self._line("}")
            else:
                self._line(f"if (prove_result_is_err({tmp})) return {tmp};")
        # Unwrap the success value
        inner_type = self._infer_expr_type(expr.expr)
        if isinstance(inner_type, GenericInstance) and inner_type.base_name == "Result":
            if inner_type.args:
                success_type = inner_type.args[0]
                return self._unwrap_result_value(tmp, success_type)
        # Failable function with non-Result return -- the C ABI still wraps
        # in Prove_Result, so we need to unwrap.
        if isinstance(inner_type, ErrorType):
            return f"{tmp}"
        # Result without args already handled above; bare Result has no value.
        if (
            isinstance(inner_type, GenericInstance)
            and inner_type.base_name == "Result"
            and not inner_type.args
        ):
            return f"{tmp}"
        return self._unwrap_result_value(tmp, inner_type)

    def _emit_async_call(self, expr: AsyncCallExpr) -> str:
        """Emit an async call (expr&).

        For attached calls: pass _coro as first arg so the caller can yield.
        For listens calls: build worker coro list and call entry directly.
        For detached calls: bare call, no _coro threading.
        """
        inner = expr.expr
        if isinstance(inner, CallExpr) and isinstance(inner.func, IdentifierExpr):
            fname = inner.func.name
            sig = self._symbols.resolve_function_any(fname)
            if sig and sig.verb == "attached":
                # Pass _coro as implicit first argument
                args = [self._emit_expr(a) for a in inner.args]
                args_str = ", ".join(["_coro"] + args)
                from prove.c_types import mangle_name
                if sig.param_types:
                    mangled = mangle_name(sig.verb, fname, sig.param_types)
                else:
                    mangled = fname
                return f"{mangled}({args_str})"
            if sig and sig.verb == "listens":
                return self._emit_listens_call(inner, sig)
        # Detached or bare: emit the inner expression directly
        return self._emit_expr(inner)

    def _emit_listens_call(self, call: CallExpr, sig) -> str:
        """Emit a listens call with worker coro creation for List<Attached> args."""
        from prove.ast_nodes import CallExpr as _CE, IdentifierExpr as _IE, ListLiteral
        from prove.c_types import mangle_name

        fname = call.func.name  # type: ignore[attr-defined]
        mangled = mangle_name(sig.verb, fname, sig.param_types)

        # Build worker list: each attached call becomes a pre-started coro
        if call.args and isinstance(call.args[0], ListLiteral):
            workers = call.args[0]
            list_tmp = self._tmp()
            self._line(
                f"Prove_List *{list_tmp} = prove_list_new({len(workers.elements)});"
            )
            for elem in workers.elements:
                if isinstance(elem, _CE) and isinstance(elem.func, _IE):
                    worker_sig = self._symbols.resolve_function_any(elem.func.name)
                    if worker_sig and worker_sig.verb == "attached":
                        w_mangled = mangle_name(
                            worker_sig.verb, elem.func.name, worker_sig.param_types
                        )
                        args_struct = f"_{w_mangled}_args"
                        body_fn = f"_{w_mangled}_body"
                        a_tmp = self._tmp()
                        c_tmp = self._tmp()
                        self._line(
                            f"{args_struct} *{a_tmp} = malloc(sizeof({args_struct}));"
                        )
                        for j, arg in enumerate(elem.args):
                            pname = worker_sig.param_names[j]
                            val = self._emit_expr(arg)
                            self._line(f"{a_tmp}->{pname} = {val};")
                        self._line(
                            f"Prove_Coro *{c_tmp} = prove_coro_new("
                            f"{body_fn}, PROVE_CORO_STACK_DEFAULT);"
                        )
                        self._line(f"prove_coro_start({c_tmp}, {a_tmp});")
                        self._line(f"prove_list_push({list_tmp}, (void*){c_tmp});")
                    else:
                        # Non-attached in worker list — emit as value
                        val = self._emit_expr(elem)
                        self._line(f"prove_list_push({list_tmp}, (void*)(intptr_t){val});")
                else:
                    val = self._emit_expr(elem)
                    self._line(f"prove_list_push({list_tmp}, (void*)(intptr_t){val});")
            return f"{mangled}({list_tmp})"

        # Fallback: emit args normally
        args = [self._emit_expr(a) for a in call.args]
        args_str = ", ".join(args) if args else ""
        return f"{mangled}({args_str})"

    def _unwrap_result_value(self, tmp: str, success_type: Type) -> str:
        """Emit the correct prove_result_unwrap_* call for a success type."""
        if isinstance(success_type, UnitType):
            return tmp  # No value to unwrap
        if isinstance(success_type, RecordType):
            ct = map_type(success_type)
            return f"*(({ct.decl}*)prove_result_unwrap_ptr({tmp}))"
        sname = getattr(success_type, "name", "")
        if sname == "Integer":
            return f"prove_result_unwrap_int({tmp})"
        ct = map_type(success_type)
        if ct.is_pointer:
            return f"({ct.decl})prove_result_unwrap_ptr({tmp})"
        if ct.decl == "double":
            return f"prove_result_unwrap_double({tmp})"
        # Struct-like GenericInstance (Option<Value>, etc.)
        if isinstance(success_type, GenericInstance) and not ct.is_pointer:
            return f"*(({ct.decl}*)prove_result_unwrap_ptr({tmp}))"
        return f"prove_result_unwrap_int({tmp})"

    # -- Match expressions ------------------------------------------

    def _emit_match_expr(self, m: MatchExpr) -> str:
        if m.subject is None:
            # Implicit subject: matches/streams use first parameter,
            # listens uses _ev (received event from queue)
            if (
                self._current_func is not None
                and self._current_func.verb in ("matches", "streams", "listens")
            ):
                if self._current_func.verb == "listens":
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
                    return self._emit_match_expr(implicit_subj)
            # No subject and not matches/streams/listens -- just emit arm bodies
            for arm in m.arms:
                for s in arm.body:
                    self._emit_stmt(s)
            return "/* match */"

        # Save locals so match arm bindings don't leak to function scope
        saved_locals = dict(self._locals)
        subj = self._emit_expr(m.subject)
        subj_type = self._resolve_prim_type(self._infer_expr_type(m.subject))

        # Detect Option<T> subject — literal/wildcard patterns need unwrapping
        is_option_subj = (
            isinstance(subj_type, GenericInstance)
            and subj_type.base_name == "Option"
            and subj_type.args
        )
        if is_option_subj:
            opt_tmp = self._tmp()
            self._line(f"Prove_Option {opt_tmp} = {subj};")
            subj = opt_tmp

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
                    if is_option_subj:
                        # Unwrap Option: check tag==1 (Some) and compare inner value
                        inner_ty = subj_type.args[0]
                        inner_ct = map_type(inner_ty)
                        cast = (
                            f"({inner_ct.decl})"
                            if inner_ct.is_pointer
                            else f"({inner_ct.decl})(intptr_t)"
                        )
                        unwrapped = f"{cast}{subj}.value"
                        inner_cond = self._emit_literal_cond(unwrapped, arm.pattern, inner_ty)
                        cond = f"{subj}.tag == 1 && {inner_cond}"
                    else:
                        cond = self._emit_literal_cond(subj, arm.pattern, subj_type, m.subject)
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
                elif isinstance(arm.pattern, VariantPattern):
                    vp = arm.pattern
                    if isinstance(subj_type, GenericInstance) and subj_type.base_name == "Option":
                        if vp.name == "Some":
                            keyword = "if" if first else "} else if"
                            self._line(f"{keyword} ({subj}.tag == 1) {{")
                            self._indent += 1
                            if vp.fields and isinstance(vp.fields[0], BindingPattern):
                                inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                                inner_ct = map_type(inner_ty)
                                bind_name = vp.fields[0].name
                                cast = (
                                    f"({inner_ct.decl})"
                                    if inner_ct.is_pointer
                                    else f"({inner_ct.decl})(intptr_t)"
                                )
                                if bind_name == subj:
                                    alias = self._tmp()
                                    self._line(f"{inner_ct.decl} {alias} = {cast}{subj}.value;")
                                    self._line(f"{inner_ct.decl} {bind_name} = {alias};")
                                else:
                                    self._line(f"{inner_ct.decl} {bind_name} = {cast}{subj}.value;")
                                self._locals[bind_name] = inner_ty
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
                        elif vp.name == "None":
                            # None variant -- treated as else
                            if first:
                                self._line("{")
                            else:
                                self._line("} else {")
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
                            self._line("}")
                    elif isinstance(subj_type, GenericInstance) and subj_type.base_name == "Result":
                        if vp.name == "Ok":
                            keyword = "if" if first else "} else if"
                            self._line(f"{keyword} ({subj}.tag == 0) {{")
                            self._indent += 1
                            if vp.fields and isinstance(vp.fields[0], BindingPattern):
                                inner_ty = subj_type.args[0] if subj_type.args else INTEGER
                                inner_ct = map_type(inner_ty)
                                bind_name = vp.fields[0].name
                                cast = (
                                    f"({inner_ct.decl})"
                                    if inner_ct.is_pointer
                                    else f"({inner_ct.decl})(intptr_t)"
                                )
                                if bind_name == subj:
                                    alias = self._tmp()
                                    self._line(f"{inner_ct.decl} {alias} = {cast}{subj}.value;")
                                    self._line(f"{inner_ct.decl} {bind_name} = {alias};")
                                else:
                                    self._line(f"{inner_ct.decl} {bind_name} = {cast}{subj}.value;")
                                self._locals[bind_name] = inner_ty
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
                        elif vp.name == "Err":
                            keyword = "if" if first else "} else if"
                            self._line(f"{keyword} ({subj}.tag == 1) {{")
                            self._indent += 1
                            if vp.fields and isinstance(vp.fields[0], BindingPattern):
                                bind_name = vp.fields[0].name
                                self._line(f"Prove_String* {bind_name} = {subj}.error;")
                                err_ty = subj_type.args[1] if len(subj_type.args) > 1 else ERROR_TY
                                self._locals[bind_name] = err_ty
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
                    elif map_type(subj_type).is_pointer:
                        if vp.name == "Some":
                            keyword = "if" if first else "} else if"
                            self._line(f"{keyword} ({subj} != NULL) {{")
                            self._indent += 1
                            if vp.fields and isinstance(vp.fields[0], BindingPattern):
                                bind_name = vp.fields[0].name
                                # Skip re-declaration when binding name
                                # matches the subject -- avoids C
                                # self-init UB (T x = x;)
                                if bind_name != subj:
                                    sct = map_type(subj_type)
                                    self._line(f"{sct.decl} {bind_name} = {subj};")
                                self._locals[bind_name] = subj_type
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
                        else:
                            # None or other -- else branch
                            if first:
                                self._line("{")
                            else:
                                self._line("} else {")
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
                            self._line("}")
                    elif isinstance(subj_type, RecordType) and vp.name == subj_type.name:
                        # Record type always matches its own name -- unconditional.
                        # Remaining arms are dead code, so break after emitting.
                        for i, s in enumerate(arm.body):
                            if not is_unit and i == len(arm.body) - 1:
                                e = self._stmt_expr(s)
                                if e is not None:
                                    self._line(f"{tmp} = {self._emit_expr(e)};")
                                else:
                                    self._emit_stmt(s)
                            else:
                                self._emit_stmt(s)
                        break
                first = False

            # Close trailing if without else
            if not isinstance(
                m.arms[-1].pattern,
                (WildcardPattern, BindingPattern),
            ):
                # Don't double-close if last was a None variant (already closed)
                last_pat = m.arms[-1].pattern
                needs_close = True
                if isinstance(last_pat, VariantPattern) and last_pat.name == "None":
                    needs_close = False
                if needs_close:
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
                # streams: Exit arm exits the blocking loop
                if (
                    self._in_streams_loop
                    and isinstance(arm.pattern, VariantPattern)
                    and arm.pattern.name == "Exit"
                ):
                    self._line("goto _streams_exit;")
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
                    ty = self._infer_expr_type(last.expr)
                    if not isinstance(ty, ErrorType):
                        return ty
        return UNIT

    # -- Lambda expressions -----------------------------------------

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

    # -- String interpolation ---------------------------------------

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
                    "Decimal",
                    "Float",
                ):
                    parts.append(f"prove_string_from_double({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Boolean":
                    parts.append(f"prove_string_from_bool({val})")
                elif isinstance(part_type, PrimitiveType) and part_type.name == "Character":
                    parts.append(f"prove_string_from_char({val})")
                elif (
                    isinstance(part_type, GenericInstance)
                    and part_type.base_name == "Option"
                    and part_type.args
                ):
                    inner = part_type.args[0]
                    inner_ct = map_type(inner)
                    cast = (
                        f"({inner_ct.decl})"
                        if inner_ct.is_pointer
                        else f"({inner_ct.decl})(intptr_t)"
                    )
                    unwrapped = f"{cast}{val}.value"
                    c_name = self._to_string_func(inner)
                    parts.append(f"{c_name}({unwrapped})")
                else:
                    parts.append(f"prove_string_from_int({val})")

        if not parts:
            return 'prove_string_from_cstr("")'
        result = parts[0]
        for p in parts[1:]:
            result = f"prove_string_concat({result}, {p})"
        return result

    # -- List literal -----------------------------------------------

    def _emit_list_literal(self, expr: ListLiteral) -> str:
        if not expr.elements:
            return "prove_list_new(4)"

        # Determine element type
        elem_type = self._infer_expr_type(expr.elements[0])
        ct = map_type(elem_type)

        tmp = self._tmp()
        # Use region allocation if inside a function with escape analysis
        if self._use_region_allocation():
            self._line(
                f"Prove_List *{tmp} = prove_list_new_region({self._get_region_ptr()}, {len(expr.elements)});"
            )
        else:
            self._line(f"Prove_List *{tmp} = prove_list_new({len(expr.elements)});")
        for elem in expr.elements:
            val = self._emit_expr(elem)
            if ct.is_pointer:
                self._line(f"prove_list_push({tmp}, (void*){val});")
            else:
                self._line(f"prove_list_push({tmp}, (void*)(intptr_t){val});")
        return tmp

    # -- Index expression -------------------------------------------

    def _emit_index(self, expr: IndexExpr) -> str:
        obj = self._emit_expr(expr.obj)
        idx = self._emit_expr(expr.index)
        obj_type = self._infer_expr_type(expr.obj)
        if isinstance(obj_type, ListType):
            elem_ct = map_type(obj_type.element)
            if elem_ct.is_pointer:
                return f"({elem_ct.decl})prove_list_get({obj}, {idx})"
            return f"({elem_ct.decl})(intptr_t)prove_list_get({obj}, {idx})"
        return f"{obj}[{idx}]"

    # -- Lookup access ----------------------------------------------

    def _emit_lookup_access(self, expr: LookupAccessExpr) -> str:
        """Emit a compile-time lookup: TypeName:"main" -> Main(), TypeName:Main -> string."""
        lookup = self._lookup_tables.get(expr.type_name)
        if lookup is None:
            return "/* no lookup table */ 0"
        operand = expr.operand

        # Binary lookup with variable operand: runtime lookup
        if isinstance(operand, IdentifierExpr) and lookup.is_binary:
            return self._emit_binary_lookup(expr, lookup)

        if isinstance(operand, (StringLit, IntegerLit, BooleanLit)):
            value = operand.value
            if isinstance(operand, BooleanLit):
                value = "true" if operand.value else "false"
            str_value = str(value)

            # Binary lookup: cross-column literal lookup
            if lookup.is_binary and lookup.value_types:
                for entry in lookup.entries:
                    if str_value in entry.values:
                        col_idx = self._binary_column_index(
                            lookup, self._expected_emit_type
                        )
                        val = entry.values[col_idx]
                        kind = entry.value_kinds[col_idx]
                        if kind == "string":
                            escaped = self._escape_c_string(val)
                            return f'prove_string_from_cstr("{escaped}")'
                        if kind == "integer":
                            return f"{val}L"
                        if kind == "decimal":
                            return val
                        if kind == "boolean":
                            return val
                        return f'prove_string_from_cstr("{val}")'
                return "/* lookup miss */ 0"

            # Single-column: literal -> variant constructor
            for entry in lookup.entries:
                if entry.value == str_value:
                    return f"{entry.variant}()"
            return "/* lookup miss */ 0"
        if isinstance(operand, TypeIdentifierExpr):
            # Reverse: variant -> value
            for entry in lookup.entries:
                if entry.variant == operand.name:
                    # Binary lookup: select column by expected type
                    if lookup.is_binary and entry.values:
                        col_idx = self._binary_column_index(lookup, self._expected_emit_type)
                        val = entry.values[col_idx]
                        kind = entry.value_kinds[col_idx]
                        if kind == "string":
                            escaped = self._escape_c_string(val)
                            return f'prove_string_from_cstr("{escaped}")'
                        if kind == "integer":
                            return f"{val}L"
                        if kind == "decimal":
                            return val
                        if kind == "boolean":
                            return val
                        return f'prove_string_from_cstr("{val}")'
                    # Single-column lookup
                    if entry.value_kind == "string":
                        escaped = self._escape_c_string(entry.value)
                        return f'prove_string_from_cstr("{escaped}")'
                    if entry.value_kind == "integer":
                        return f"{entry.value}L"
                    if entry.value_kind == "decimal":
                        return entry.value
                    if entry.value_kind == "boolean":
                        return entry.value
                    return f'prove_string_from_cstr("{entry.value}")'
            return "/* lookup miss */ 0"
        return "/* unsupported lookup */ 0"

    def _emit_binary_lookup(self, expr: LookupAccessExpr, lookup: object) -> str:
        """Emit runtime binary lookup for a variable operand."""
        from prove.ast_nodes import LookupTypeDef
        from prove.c_types import mangle_type_name

        assert isinstance(lookup, LookupTypeDef)
        operand = expr.operand
        assert isinstance(operand, IdentifierExpr)
        cname = mangle_type_name(expr.type_name)
        var_c = self._emit_expr(operand)

        # Determine direction from expected type (VarDecl annotation) or
        # function return type as fallback
        ret_type = self._expected_emit_type or self._current_return_type()
        ret_name = self._type_name_str(ret_type)

        # Check if return type matches any column type (forward lookup)
        col_name = self._find_binary_column_name(lookup, ret_name)
        if col_name:
            if ret_name == "String":
                return f"prove_string_from_cstr({cname}_col_{col_name}[{var_c}])"
            return f"{cname}_col_{col_name}[{var_c}]"

        # Check if return type matches the algebraic type (reverse lookup)
        alg_type = self._symbols.resolve_type(expr.type_name)
        if alg_type and self._types_match(ret_type, alg_type):
            # Reverse: column value → variant index
            var_type = self._infer_expr_type(operand)
            var_name = self._type_name_str(var_type)
            use_sorted = len(lookup.entries) > 16
            if var_name == "String":
                fn = "prove_lookup_find_sorted" if use_sorted else "prove_lookup_find"
                return f"{fn}(&{cname}_reverse, {var_c}.data)"
            if var_name == "Integer":
                fn = "prove_lookup_find_int_sorted" if use_sorted else "prove_lookup_find_int"
                return f"{fn}(&{cname}_int_reverse, {var_c})"

        return "/* unsupported binary lookup */ 0"

    def _binary_column_index(self, lookup: object, expected: Type | None) -> int:
        """Return the column index matching expected type, or 0."""
        from prove.ast_nodes import LookupTypeDef

        assert isinstance(lookup, LookupTypeDef)
        if expected is not None:
            name = self._type_name_str(expected)
            for i, vt in enumerate(lookup.value_types):
                col_name = vt.name if hasattr(vt, "name") else ""
                if col_name == name:
                    return i
        return 0

    def _find_binary_column_name(self, lookup: object, type_name: str) -> str | None:
        """Find the C array suffix for the column matching the given type name."""
        from prove.ast_nodes import LookupTypeDef

        assert isinstance(lookup, LookupTypeDef)
        type_names = [
            vt.name if hasattr(vt, "name") else "" for vt in lookup.value_types
        ]
        has_dups = type_names.count(type_name) > 1
        for col_idx, vt in enumerate(lookup.value_types):
            col_type = vt.name if hasattr(vt, "name") else ""
            if col_type == type_name:
                # Use named column if available
                named = (
                    lookup.column_names[col_idx]
                    if lookup.column_names and col_idx < len(lookup.column_names)
                       and lookup.column_names[col_idx] is not None
                    else None
                )
                if named:
                    return named
                if has_dups:
                    return f"{col_type}_{col_idx}"
                return col_type
        return None

    def _type_name_str(self, ty: Type) -> str:
        """Get the simple name of a type for binary lookup column matching."""
        if isinstance(ty, PrimitiveType):
            return ty.name
        if isinstance(ty, AlgebraicType):
            return ty.name
        return ""

    def _types_match(self, a: Type, b: Type) -> bool:
        """Check if two types match by name."""
        return self._type_name_str(a) == self._type_name_str(b)

    def _current_return_type(self) -> Type:
        """Get the return type of the current function being emitted."""
        if hasattr(self, "_current_func_return") and self._current_func_return is not None:
            return self._current_func_return
        return ERROR_TY

    def _emit_binary_lookup_expr(self, expr: BinaryLookupExpr) -> str:
        """Emit a BinaryLookupExpr node (runtime binary lookup)."""
        from prove.ast_nodes import LookupTypeDef
        from prove.c_types import mangle_type_name

        cname = mangle_type_name(expr.type_name)
        var_c = self._emit_expr(expr.operand)

        if expr.key_type == "variant":
            # Forward: variant index → column value
            # Resolve the C array name using named columns if available
            lookup = self._lookup_tables.get(expr.type_name)
            col_array = expr.column_type
            if lookup and isinstance(lookup, LookupTypeDef) and lookup.column_names:
                for i, vt in enumerate(lookup.value_types):
                    col_name = vt.name if hasattr(vt, "name") else ""
                    if col_name == expr.column_type:
                        named = (
                            lookup.column_names[i]
                            if i < len(lookup.column_names)
                               and lookup.column_names[i] is not None
                            else None
                        )
                        if named:
                            col_array = named
                        break
            if expr.column_type == "String":
                return f"prove_string_from_cstr({cname}_col_{col_array}[{var_c}])"
            return f"{cname}_col_{col_array}[{var_c}]"
        if expr.key_type == "String":
            # Reverse: string → variant index
            lookup = self._lookup_tables.get(expr.type_name)
            use_sorted = (
                lookup is not None
                and isinstance(lookup, LookupTypeDef)
                and len(lookup.entries) > 16
            )
            fn = "prove_lookup_find_sorted" if use_sorted else "prove_lookup_find"
            return f"{fn}(&{cname}_reverse, {var_c}.data)"
        return "/* unsupported binary lookup */ 0"

    def _emit_store_lookup_expr(self, expr: StoreLookupExpr) -> str:
        """Emit runtime store-backed lookup: colors:"red" → prove_store_table_find_int(...)."""
        from prove.ast_nodes import LookupTypeDef

        table_var = expr.table_var
        key_c = self._emit_expr(expr.operand)

        # Determine column indices from schema and expected return type
        type_name_str = self._store_var_types.get(table_var, "")

        lookup = self._lookup_tables.get(type_name_str)
        if lookup is None or not isinstance(lookup, LookupTypeDef):
            return f"/* unknown store lookup */ 0"

        # key_col: index of column matching the key type (String)
        # val_col: index of column matching the expected return type
        key_col = 0
        val_col = 0
        ret_type = self._expected_emit_type or self._current_return_type()
        ret_name = self._type_name_str(ret_type)

        for i, vt in enumerate(lookup.value_types):
            col_name = vt.name if hasattr(vt, "name") else ""
            if col_name == ret_name:
                val_col = i
            elif col_name == "String":
                key_col = i

        self._needed_headers.add("prove_store.h")

        # Wrap key in Prove_String if it's a C string literal
        if isinstance(expr.operand, StringLit):
            escaped = self._escape_c_string(expr.operand.value)
            key_c = f'prove_string_from_cstr("{escaped}")'

        if ret_name == "Integer":
            return f"prove_store_table_find_int({table_var}, {key_c}, {key_col}, {val_col})"
        return f"prove_store_table_find({table_var}, {key_c}, {key_col}, {val_col})"

    def _infer_lookup_type(self, expr: LookupAccessExpr) -> Type:
        """Infer the type of a lookup access expression."""
        lookup = self._lookup_tables.get(expr.type_name)
        if lookup is None:
            return ERROR_TY
        operand = expr.operand
        if isinstance(operand, (StringLit, IntegerLit, BooleanLit)):
            # Forward: literal -> algebraic type
            resolved = self._symbols.resolve_type(expr.type_name)
            return resolved if resolved else ERROR_TY
        if isinstance(operand, TypeIdentifierExpr):
            # Reverse: variant -> value type
            name = lookup.value_type.name if hasattr(lookup.value_type, "name") else ""
            resolved = self._symbols.resolve_type(name)
            return resolved if resolved else ERROR_TY
        if isinstance(operand, IdentifierExpr) and lookup.is_binary:
            # Binary runtime: use function return type
            return self._current_return_type()
        return ERROR_TY

    def _emit_literal_cond(
        self,
        subj: str,
        pat: LiteralPattern,
        subj_type: Type | None = None,
        subj_expr: Expr | None = None,
    ) -> str:
        """Generate a C condition comparing subj to a literal pattern."""
        val = pat.value
        # True Value type: data is a real Prove_Value struct → use prove_value_as_*
        is_true_value = subj_type and self._is_value_type(subj_type)
        # Resolved Value: C function returns Prove_Value* but the Prove type
        # resolved to a concrete type (e.g. String).  The pointer is actually
        # the concrete type (Prove_String*, int64_t, …) — cast, don't access
        # as Prove_Value struct.
        is_resolved_value = (
            not is_true_value
            and subj_expr is not None
            and self._c_returns_value_ptr(subj_expr)
        )
        if pat.kind == "boolean" or val in ("true", "false"):
            if is_true_value:
                subj = f"prove_value_as_bool({subj})"
            elif is_resolved_value:
                subj = f"(bool)(intptr_t){subj}"
            return subj if val == "true" else f"!({subj})"
        if pat.kind == "string":
            escaped = self._escape_c_string(val)
            if is_true_value:
                subj = f"prove_value_as_text({subj})"
            elif is_resolved_value:
                subj = f"(Prove_String*){subj}"
            return f'prove_string_eq({subj}, prove_string_from_cstr("{escaped}"))'
        if is_true_value:
            subj = f"prove_value_as_number({subj})"
        elif is_resolved_value:
            subj = f"(int64_t)(intptr_t){subj}"
        return f"{subj} == {val}L"
