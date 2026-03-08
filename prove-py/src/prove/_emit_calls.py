"""Call dispatch and HOF emission mixin for CEmitter."""

from __future__ import annotations

import itertools

from prove.ast_nodes import (
    CallExpr,
    Expr,
    FieldExpr,
    IdentifierExpr,
    LambdaExpr,
    TypeIdentifierExpr,
    ValidExpr,
)
from prove.c_types import mangle_name, map_type
from prove.symbols import FunctionSignature
from prove.type_inference import BUILTIN_MAP, get_type_key
from prove.types import (
    INTEGER,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    Type,
    resolve_type_vars,
    substitute_type_vars,
)


class CallEmitterMixin:

    def _resolve_stdlib_c_name(
        self,
        sig: FunctionSignature,
        call_args: list[Expr] | None = None,
        verb_override: str | None = None,
    ) -> str | None:
        """Resolve a stdlib function signature to its C runtime name."""
        if not sig.module:
            return None
        from prove.stdlib_loader import binary_c_name

        verb = verb_override or sig.verb
        fpt = None
        if call_args:
            actual_fpt = self._infer_expr_type(call_args[0])
            fpt = get_type_key(actual_fpt)
        if fpt is None:
            pts = sig.param_types
            fpt = get_type_key(pts[0]) if pts else None
        return binary_c_name(sig.module, verb, sig.name, fpt)

    def _is_option_narrowed(
        self,
        func_name: str,
        args: list[Expr],
        module_name: str,
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
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                # requires valid email(param) — resolve the validates function
                sig_v = self._symbols.resolve_function(
                    "validates", req_expr.name, len(req_expr.args)
                )
                if sig_v is None:
                    sig_v = self._symbols.resolve_function_any(
                        req_expr.name, arity=len(req_expr.args)
                    )
                if sig_v is None or sig_v.verb != "validates":
                    continue
                req_mod = sig_v.module or module_name
                if req_mod != module_name:
                    continue
                req_arg_names: list[str] = []
                all_idents = True
                for a in req_expr.args:
                    if isinstance(a, IdentifierExpr):
                        req_arg_names.append(a.name)
                    else:
                        all_idents = False
                        break
                if all_idents and frozenset(req_arg_names) == call_key:
                    return True
                continue
            if not isinstance(req_expr, CallExpr):
                continue
            func = req_expr.func
            # Qualified: Table.has(...)
            if isinstance(func, FieldExpr) and isinstance(func.obj, TypeIdentifierExpr):
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
            req_arg_names2: list[str] = []
            all_idents2 = True
            for a in req_expr.args:
                if isinstance(a, IdentifierExpr):
                    req_arg_names2.append(a.name)
                else:
                    all_idents2 = False
                    break
            if not all_idents2:
                continue
            if frozenset(req_arg_names2) == call_key:
                return True
        return False

    def _maybe_unwrap_option(
        self,
        call_str: str,
        sig: FunctionSignature,
        call_args: list[Expr],
        module_name: str,
    ) -> str:
        """If the call returns Option<Value> and is narrowed by requires, unwrap."""
        from prove.symbols import FunctionSignature

        if not isinstance(sig, FunctionSignature):
            return call_str
        ret = sig.return_type
        if not (isinstance(ret, GenericInstance) and ret.base_name == "Option" and ret.args):
            return call_str
        if not self._is_option_narrowed(sig.name, call_args, module_name):
            return call_str
        # Resolve type variables against actual arg types
        actual_types = [self._infer_expr_type(a) for a in call_args]
        bindings = resolve_type_vars(sig.param_types, actual_types)
        inner = substitute_type_vars(ret.args[0], bindings)
        inner_ct = map_type(inner)
        return f"({inner_ct.decl}){call_str}.value"

    def _resolve_call_sig(self, expr: Expr) -> FunctionSignature | None:
        """Resolve the FunctionSignature for a call expression, if any."""
        from prove.symbols import FunctionSignature

        if isinstance(expr, CallExpr):
            n_args = len(expr.args)
            if isinstance(expr.func, IdentifierExpr):
                sig = self._symbols.resolve_function(None, expr.func.name, n_args)
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        expr.func.name,
                        arity=n_args,
                    )
                return sig if isinstance(sig, FunctionSignature) else None
            if isinstance(expr.func, FieldExpr) and isinstance(
                expr.func.obj,
                TypeIdentifierExpr,
            ):
                sig = self._symbols.resolve_function(
                    None,
                    expr.func.field,
                    n_args,
                )
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        expr.func.field,
                        arity=n_args,
                    )
                return sig if isinstance(sig, FunctionSignature) else None
        return None

    def _maybe_unwrap_option_value(
        self,
        expr_str: str,
        expr_type: Type,
        target_type: Type,
    ) -> str:
        """If expr_type is Option<Value> and target_type is Value, unwrap .value with tag check."""
        if (
            isinstance(expr_type, GenericInstance)
            and expr_type.base_name == "Option"
            and expr_type.args
        ):
            inner = expr_type.args[0]
            inner_ct = map_type(inner)
            target_ct = map_type(target_type)
            # Check if target type matches the inner Option type
            if target_ct.decl == inner_ct.decl:
                # Only unwrap if Some (tag == 1), otherwise use a default/zero value
                # For numeric types, use 0 as default; for pointers, use NULL
                if inner_ct.is_pointer or inner_ct.decl == "Prove_String*":
                    default_val = "NULL"
                else:
                    default_val = "0"
                return f"({expr_str}.tag == 1 ? ({inner_ct.decl}){expr_str}.value : {default_val})"
        return expr_str

    def _coerce_call_args(
        self,
        args: list[str],
        arg_exprs: list[Expr],
        sig: FunctionSignature,
    ) -> list[str]:
        """Coerce call arguments to match parameter types.

        Handles:
        - Option<Value> arg → Value param: unwrap with .value
        - Result<Value, Error> arg → Value param: unwrap with prove_result_unwrap_*
        - Prove_Value* arg → int64_t/String* param: prove_value_as_*
        """
        if sig is None or not hasattr(sig, "param_types"):
            return args
        result = list(args)
        for i, (arg_str, arg_expr) in enumerate(zip(args, arg_exprs)):
            if i >= len(sig.param_types):
                break
            arg_ty = self._infer_expr_type(arg_expr)
            param_ty = sig.param_types[i]
            arg_ct = map_type(arg_ty)
            param_ct = map_type(param_ty)
            if arg_ct.decl == param_ct.decl:
                continue
            # Option<Value> → Value: unwrap .value with tag check
            if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Option" and arg_ty.args:
                inner_ct = map_type(arg_ty.args[0])
                if inner_ct.decl == param_ct.decl:
                    # Only unwrap if Some (tag == 1), otherwise use default value
                    if inner_ct.is_pointer or inner_ct.decl == "Prove_String*":
                        default_val = "NULL"
                    else:
                        default_val = "0"
                    result[i] = (
                        f"({arg_str}.tag == 1 ? ({param_ct.decl}){arg_str}.value : {default_val})"
                    )
                    continue
            # Result<Value, Error> → Value: unwrap
            if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Result" and arg_ty.args:
                inner_ty = arg_ty.args[0]
                inner_ct = map_type(inner_ty)
                if inner_ct.decl == param_ct.decl:
                    if inner_ct.is_pointer:
                        result[i] = f"({param_ct.decl})prove_result_unwrap_ptr({arg_str})"
                    elif inner_ct.decl == "double":
                        result[i] = f"prove_result_unwrap_double({arg_str})"
                    else:
                        result[i] = f"prove_result_unwrap_int({arg_str})"
                    continue
            # Prove_Value* → concrete type extraction
            if arg_ct.decl == "Prove_Value*" and not param_ct.is_pointer:
                if param_ct.decl in (
                    "int64_t",
                    "int32_t",
                    "int16_t",
                    "int8_t",
                    "uint64_t",
                    "uint32_t",
                    "uint16_t",
                    "uint8_t",
                ):
                    result[i] = f"prove_value_as_number({arg_str})"
                elif param_ct.decl in ("double", "float"):
                    result[i] = f"prove_value_as_decimal({arg_str})"
                elif param_ct.decl == "bool":
                    result[i] = f"prove_value_as_bool({arg_str})"
                continue
            if arg_ct.decl == "Prove_Value*" and param_ct.decl == "Prove_String*":
                result[i] = f"prove_value_as_text({arg_str})"
                continue
        return result

    def _emit_call(self, expr: CallExpr) -> str:
        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Higher-order functions handle their own arg emission
            # (must check before eagerly emitting args to avoid
            # hoisting lambdas that will be inlined)
            if name == "map" and len(expr.args) == 2:
                return self._emit_hof_map(expr)
            if name == "each" and len(expr.args) == 2:
                return self._emit_hof_each(expr)
            if name == "filter" and len(expr.args) == 2:
                return self._emit_hof_filter(expr)
            if name == "reduce" and len(expr.args) == 3:
                return self._emit_hof_reduce(expr)

        args = [self._emit_expr(a) for a in expr.args]

        # Wrap record args with record-to-Value converters when needed
        args = self._wrap_record_to_value_args(expr, args)

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Type-aware dispatch for to_string
            if name == "to_string" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                # Unwrap Option<Value> → use inner type for dispatch
                if (
                    isinstance(arg_type, GenericInstance)
                    and arg_type.base_name == "Option"
                    and arg_type.args
                ):
                    inner_ty = arg_type.args[0]
                    inner_ct = map_type(inner_ty)
                    c_name = self._to_string_func(inner_ty)
                    return f"{c_name}(({inner_ct.decl}){args[0]}.value)"
                c_name = self._to_string_func(arg_type)
                return f"{c_name}({', '.join(args)})"

            # Type-aware dispatch for len
            if name == "len" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                if isinstance(arg_type, PrimitiveType) and arg_type.name == "String":
                    return f"prove_string_len({', '.join(args)})"
                return f"prove_list_len({', '.join(args)})"

            # unwrap(Option<Value>) → monomorphized _unwrap call
            if name == "unwrap" and len(args) == 1 and expr.args:
                arg_ty = self._infer_expr_type(expr.args[0])
                if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Option":
                    opt_ct = map_type(arg_ty)
                    return f"{opt_ct.decl}_unwrap({args[0]})"
                # Result unwrap
                if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Result":
                    if arg_ty.args:
                        inner_ct = map_type(arg_ty.args[0])
                        if inner_ct.is_pointer:
                            return f"prove_result_unwrap_ptr({args[0]})"
                        if inner_ct.decl == "double":
                            return f"prove_result_unwrap_double({args[0]})"
                        return f"prove_result_unwrap_int({args[0]})"

            # Builtin mapping
            if name in BUILTIN_MAP:
                c_name = BUILTIN_MAP[name]
                return f"{c_name}({', '.join(args)})"

            # Foreign (C FFI) functions — emit direct C call, no mangling
            if name in self._foreign_names:
                return f"{name}({', '.join(args)})"

            # Binary bridge: stdlib binary functions → C runtime
            n_args = len(expr.args)
            sig = self._symbols.resolve_function(None, name, n_args)
            # Type-based disambiguation for overloaded stdlib functions
            if expr.args:
                from prove.types import TypeVariable, types_compatible

                actual_types = [self._infer_expr_type(a) for a in expr.args]
                if sig is None or (
                    sig.param_types
                    and not all(
                        isinstance(p, TypeVariable) or types_compatible(p, a)
                        for p, a in zip(sig.param_types, actual_types)
                    )
                ):
                    any_sig = self._symbols.resolve_function_any(
                        name,
                        actual_types,
                    )
                    if any_sig is not None:
                        sig = any_sig
            elif sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )
            if sig and sig.module:
                args = self._coerce_call_args(args, expr.args, sig)
                c_name = self._resolve_stdlib_c_name(sig, expr.args)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str,
                        sig,
                        expr.args,
                        sig.module,
                    )
                    return call_str

            # User function — resolve with type-aware dispatch for overloads
            if sig is None:
                if expr.args:
                    actual = [self._infer_expr_type(a) for a in expr.args]
                    sig = self._symbols.resolve_function_by_types(None, name, actual)
                if sig is None:
                    sig = self._symbols.resolve_function(None, name, n_args)
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        name,
                        arity=n_args,
                    )

            if sig and sig.verb is not None:
                args = self._coerce_call_args(args, expr.args, sig)
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                call = f"{mangled}({', '.join(args)})"

                # Only memoize functions returning Integer or Boolean
                ret_type = sig.return_type if sig else None
                is_simple = (
                    ret_type
                    and isinstance(ret_type, PrimitiveType)
                    and ret_type.name in ("Integer", "Boolean")
                )
                if (
                    is_simple
                    and self._memo_info
                    and self._memo_info.is_candidate(sig.verb, sig.name)
                ):
                    table_name = f"_memo_{sig.verb}_{sig.name}"
                    table_size = 32
                    cand = self._memo_info.get_candidate(sig.verb, sig.name)
                    if cand:
                        key = self._get_memo_key(cand, args)
                        idx = f"(({key}) % {table_size})"
                        hit = f"{table_name}[{idx}].valid && {table_name}[{idx}].key == {key}"
                        miss = f"({table_name}[{idx}].key = {key}, {table_name}[{idx}].value = {call}, {table_name}[{idx}].valid = 1, {table_name}[{idx}].value)"
                        result = f"({hit}) ? {table_name}[{idx}].value : ({miss})"
                        return result

                return call

            # Variant constructor or unknown — use name directly
            return f"{name}({', '.join(args)})"

        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            # ByteArray(String) constructor
            if name == "ByteArray" and len(args) == 1:
                return f"prove_bytes_from_string({args[0]})"
            # List(...) constructor — emit as list creation with pushes
            if name == "List" and args:
                elem_type = self._infer_expr_type(expr.args[0])
                ct = map_type(elem_type)
                tmp = self._tmp()
                self._line(f"Prove_List *{tmp} = prove_list_new(sizeof({ct.decl}), {len(args)});")
                for i, arg in enumerate(args):
                    etmp = self._tmp()
                    self._line(f"{ct.decl} {etmp} = {arg};")
                    self._line(f"prove_list_push(&{tmp}, &{etmp});")
                return tmp
            # Pad record constructors with missing fields using defaults
            resolved = self._symbols.resolve_type(name)
            if isinstance(resolved, RecordType):
                # Coerce args to match record field types

                field_types = list(resolved.fields.values())
                fake_sig = type("Sig", (), {"param_types": field_types})()
                args = self._coerce_call_args(args, expr.args, fake_sig)
                if len(args) < len(resolved.fields):
                    for fname, ftype in itertools.islice(resolved.fields.items(), len(args), None):
                        args.append(self._default_for_type(ftype))
            elif len(args) < len(getattr(resolved, "fields", {})):
                for fname, ftype in itertools.islice(resolved.fields.items(), len(args), None):
                    args.append(self._default_for_type(ftype))
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
            # Type-aware resolution for overloaded functions
            sig = None
            if expr.args:
                actual = [self._infer_expr_type(a) for a in expr.args]
                sig = self._symbols.resolve_function_by_types(None, name, actual)
            if sig is None:
                sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )
            if sig and sig.module:
                c_name = self._resolve_stdlib_c_name(sig)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str,
                        sig,
                        expr.args,
                        module_name,
                    )
                    return call_str
            if sig and sig.verb is not None:
                mangled = mangle_name(sig.verb, sig.name, sig.param_types)
                call_str = f"{mangled}({', '.join(args)})"
                call_str = self._maybe_unwrap_option(
                    call_str,
                    sig,
                    expr.args,
                    module_name,
                )
                return call_str
            return f"{name}({', '.join(args)})"

        # Complex callable expression
        func = self._emit_expr(expr.func)
        return f"{func}({', '.join(args)})"

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

        # Determine result element type (may differ from input, e.g. Integer → String)
        result_elem_type = elem_type
        fn_expr = expr.args[1]
        if isinstance(fn_expr, IdentifierExpr):
            fn_sig = self._symbols.resolve_function_any(fn_expr.name, arity=1)
            if fn_sig:
                result_elem_type = fn_sig.return_type
        elif isinstance(fn_expr, LambdaExpr):
            # Infer from lambda body
            saved = dict(self._locals)
            if fn_expr.params:
                self._locals[fn_expr.params[0]] = elem_type
            result_elem_type = self._infer_expr_type(fn_expr.body)
            self._locals = saved

        # Emit lambda with correct types
        fn_name = self._emit_hof_lambda(fn_expr, elem_type, "map")
        result_ct = map_type(result_elem_type)
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
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1
            self._line(
                f"{elem_ct.decl} {param} = *({elem_ct.decl}*)prove_list_get({list_arg}, {idx});"
            )
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            # Retain captured pointer vars before the call — the callee
            # releases its params, but we reuse captured vars each iteration.
            self._emit_loop_body_retains(lam.body, param)
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
            expr.args[2],
            elem_type,
            "reduce",
            accum_type=accum_type,
        )
        self._line(f"prove_list_reduce({list_arg}, &{accum_tmp}, {fn_name});")
        return accum_tmp

    def _emit_hof_lambda(
        self,
        expr: Expr,
        elem_type: Type,
        kind: str,
        *,
        accum_type: Type | None = None,
    ) -> str:
        """Emit a lambda for HOF use with correct C signature."""
        if isinstance(expr, ValidExpr) and expr.args is None and kind == "filter":
            # valid error → wrap validates function as filter predicate
            sig = self._symbols.resolve_function_any(expr.name)
            pt = list(sig.param_types) if sig else None
            fn = mangle_name("validates", expr.name, pt)
            wrapper = f"_lambda_{self._tmp_counter}"
            self._tmp_counter += 1
            elem_ct = map_type(elem_type)
            lam = (
                f"static bool {wrapper}(const void *_arg) {{\n"
                f"    {elem_ct.decl} _x = *({elem_ct.decl}*)_arg;\n"
                f"    return {fn}(_x);\n"
                f"}}\n"
            )
            self._lambdas.append(lam)
            return wrapper
        if not isinstance(expr, LambdaExpr):
            # Not a lambda — resolve function reference and generate wrapper
            if isinstance(expr, IdentifierExpr) and kind in ("map", "filter"):
                # Check for common type-to-string conversions
                c_fn = None
                fn_sig = self._symbols.resolve_function_any(expr.name, arity=1)

                # If the function parameter type doesn't match elem_type,
                # use a built-in conversion (e.g., Integer → String)
                elem_ct = map_type(elem_type)
                elem_name = getattr(elem_type, "name", "")
                ret_type = fn_sig.return_type if fn_sig else None
                ret_name = getattr(ret_type, "name", "")

                if ret_name == "String" and elem_name == "Integer":
                    c_fn = "prove_string_from_int"
                elif ret_name == "String" and elem_name in ("Float", "Decimal"):
                    c_fn = "prove_string_from_double"
                elif ret_name == "String" and elem_name == "Boolean":
                    c_fn = "prove_string_from_bool"
                elif fn_sig and fn_sig.module:
                    c_fn = self._resolve_stdlib_c_name(fn_sig, None)

                if c_fn:
                    wrapper = f"_lambda_{self._tmp_counter}"
                    self._tmp_counter += 1
                    ret_ct = map_type(ret_type) if ret_type else elem_ct
                    if kind == "map":
                        lam = (
                            f"static void *{wrapper}(const void *_arg) {{\n"
                            f"    {elem_ct.decl} _x = *({elem_ct.decl}*)_arg;\n"
                            f"    static {ret_ct.decl} _result;\n"
                            f"    _result = {c_fn}(_x);\n"
                            f"    return &_result;\n"
                            f"}}\n"
                        )
                    elif kind == "filter":
                        lam = (
                            f"static bool {wrapper}(const void *_arg) {{\n"
                            f"    {elem_ct.decl} _x = *({elem_ct.decl}*)_arg;\n"
                            f"    return {c_fn}(_x);\n"
                            f"}}\n"
                        )
                    else:
                        return self._emit_expr(expr)
                    self._lambdas.append(lam)
                    return wrapper
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
                f"    {accum_ct.decl} {accum_param} = *({accum_ct.decl}*)_accum;\n"
                f"    {elem_ct.decl} {elem_param} = *({elem_ct.decl}*)_elem;\n"
                f"    *({accum_ct.decl}*)_accum = {body_code};\n"
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
