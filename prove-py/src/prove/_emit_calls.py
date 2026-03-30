"""Call dispatch and HOF emission mixin for CEmitter."""

from __future__ import annotations

import itertools

from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    CallExpr,
    Expr,
    FailPropExpr,
    FieldExpr,
    IdentifierExpr,
    IntegerLit,  # noqa: F841
    LambdaExpr,
    PathLit,
    RawStringLit,
    StringLit,
    TripleStringLit,
    TypeIdentifierExpr,
    ValidExpr,
)
from prove.c_types import CType, mangle_name, mangle_type_name, map_type, safe_c_name
from prove.symbols import FunctionSignature
from prove.type_inference import BUILTIN_MAP, get_type_key
from prove.types import (
    INTEGER,
    STRING,
    AlgebraicType,
    ArrayType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    StructType,
    Type,
    TypeVariable,
    resolve_type_vars,
    substitute_type_vars,
)


def _has_object_call(expr: Expr, param_name: str) -> bool:
    """Check if an expression tree contains a call to object(param_name)."""
    if isinstance(expr, CallExpr):
        if (
            isinstance(expr.func, IdentifierExpr)
            and expr.func.name == "object"
            and len(expr.args) == 1
            and isinstance(expr.args[0], IdentifierExpr)
            and expr.args[0].name == param_name
        ):
            return True
        # Check in function args and sub-expressions
        for arg in expr.args:
            if _has_object_call(arg, param_name):
                return True
        return _has_object_call(expr.func, param_name)
    if isinstance(expr, BinaryExpr):
        return _has_object_call(expr.left, param_name) or _has_object_call(expr.right, param_name)
    if isinstance(expr, FieldExpr):
        return _has_object_call(expr.obj, param_name)
    return False


class CallEmitterMixin:
    _locals: dict[str, Type]
    _in_hof_inline: bool

    @staticmethod
    def _is_option_none_filter(pred: Expr) -> bool:
        """Check if a filter predicate is |x| unit(x) == false."""
        if not isinstance(pred, LambdaExpr):
            return False
        body = pred.body
        if (
            isinstance(body, BinaryExpr)
            and body.op == "=="
            and isinstance(body.left, (CallExpr, ValidExpr))
            and isinstance(body.right, BooleanLit)
            and body.right.value is False
        ):
            call = body.left
            if isinstance(call, CallExpr) and isinstance(call.func, IdentifierExpr):
                return call.func.name == "unit"
            if isinstance(call, ValidExpr):
                return call.name == "unit"
        return False

    def _wrap_recursive_constructor_args(
        self, name: str, args: list[str], expr_args: list[Expr]
    ) -> list[str]:
        """Wrap value args with region allocation for recursive variant constructors."""
        cache = getattr(self, "_recursive_fields_cache", {})
        # Find which type this constructor belongs to
        sig = self._symbols.resolve_function(None, name, len(expr_args))
        if sig is None:
            return args
        ret_type = sig.return_type
        if not isinstance(ret_type, AlgebraicType):
            return args
        rec_direct = cache.get(ret_type.name)
        if not rec_direct:
            return args
        # Find the variant matching this constructor name
        variant = next((v for v in ret_type.variants if v.name == name), None)
        if not variant:
            return args
        rec_ptr_locals: set[str] = getattr(self, "_recursive_pointer_locals", set())
        field_names = list(variant.fields.keys())
        new_args = list(args)
        for i, fname in enumerate(field_names):
            if i >= len(new_args):
                break
            if (name, fname) in rec_direct:
                # If the arg is already a recursive pointer local, pass directly
                if (
                    i < len(expr_args)
                    and isinstance(expr_args[i], IdentifierExpr)
                    and expr_args[i].name in rec_ptr_locals
                ):
                    # Use the raw pointer name (not dereferenced)
                    new_args[i] = safe_c_name(expr_args[i].name)
                else:
                    ftype = variant.fields[fname]
                    ct = map_type(ftype)
                    tmp = self._tmp()
                    self._line(f"{ct.decl} *{tmp} = prove_region_alloc(sizeof({ct.decl}));")
                    self._line(f"*{tmp} = {new_args[i]};")
                    new_args[i] = tmp
        return new_args

    def _resolve_stdlib_c_name(
        self,
        sig: FunctionSignature,
        call_args: list[Expr] | None = None,
        verb_override: str | None = None,
    ) -> str | None:
        """Resolve a stdlib function signature to its C runtime name.

        Also ensures the corresponding header is added to _needed_headers.
        """
        if not sig.module:
            return None
        from prove.stdlib_loader import binary_c_name, binary_c_name_overload_only

        verb = verb_override or sig.verb

        # Check if signature has multiple params - use param count + types as key
        num_params = len(sig.param_types) if sig.param_types else 0
        if num_params >= 3 and call_args and len(call_args) >= 3:
            # For 3+ arg functions, build key from all param types.
            # Use overload-only lookup (no generic fallback) to avoid
            # returning the wrong generic function when the combined key
            # doesn't match any overload.
            if num_params >= 3:
                tpt = get_type_key(sig.param_types[2]) if sig.param_types[2] else None
            else:
                tpt = None
            spt = (
                get_type_key(sig.param_types[1]) if num_params >= 2 and sig.param_types[1] else None
            )
            fpt = (
                get_type_key(sig.param_types[0]) if num_params >= 1 and sig.param_types[0] else None
            )

            if fpt and spt and tpt:
                combined = f"{fpt}_{spt}_{tpt}"
                result = binary_c_name_overload_only(sig.module, verb, sig.name, combined)
                if result:
                    self._ensure_header_for_c_func(result)
                    return result

        fpt = None
        if call_args:
            actual_fpt = self._infer_expr_type(call_args[0])  # noqa: E501
            fpt = get_type_key(actual_fpt)
        if fpt is None:
            pts = sig.param_types
            fpt = get_type_key(pts[0]) if pts else None
        result = binary_c_name(sig.module, verb, sig.name, fpt)
        # Fallback: when actual arg type (e.g. "Tree") doesn't match an overload
        # but the sig's param type does (e.g. "Value<Tree>"), use the sig's key.
        if result is None and sig.param_types:
            sig_fpt = get_type_key(sig.param_types[0])
            if sig_fpt and sig_fpt != fpt:
                result = binary_c_name(sig.module, verb, sig.name, sig_fpt)
        # When first-param lookup is ambiguous (e.g. array(Integer, Boolean/Integer)),
        # fall back to a combined key using the second argument/param type.
        if result is None and (call_args or sig.param_types):
            spt = None
            if call_args and len(call_args) >= 2:
                actual_spt = self._infer_expr_type(call_args[1])
                spt = get_type_key(actual_spt)
            if spt is None and len(sig.param_types) >= 2:
                spt = get_type_key(sig.param_types[1])
            if spt is not None:
                combined = f"{fpt}_{spt}" if fpt else spt
                result = binary_c_name(sig.module, verb, sig.name, combined)
        if result:
            self._ensure_header_for_c_func(result)
        return result

    def _ensure_header_for_c_func(self, c_func: str) -> None:
        """Add the runtime header for a C function based on its name prefix."""
        # C runtime functions follow the pattern prove_<module>_<func>.
        # Extract the module part to determine the header.
        if not c_func.startswith("prove_"):
            return
        rest = c_func[6:]  # strip "prove_"
        # Known runtime module prefixes → headers
        _PREFIX_HEADERS = {
            "error": "prove_error.h",
            "convert": "prove_convert.h",
            "parse": "prove_parse.h",
            "table": "prove_table.h",
            "hash_crypto": "prove_hash_crypto.h",
            "hash": "prove_hash.h",
            "string": "prove_string.h",
            "list_ops": "prove_list_ops.h",
            "list": "prove_list.h",
            "array": "prove_array.h",
            "math": "prove_math.h",
            "option": "prove_option.h",
            "result": "prove_result.h",
            "format": "prove_format.h",
            "path": "prove_path.h",
            "pattern": "prove_pattern.h",
            "random": "prove_random.h",
            "time": "prove_time.h",
            "bytes": "prove_bytes.h",
            "character": "prove_character.h",
            "text": "prove_text.h",
            "network": "prove_network.h",
            "language": "prove_language.h",
            "ansi": "prove_ansi.h",
        }
        # Try longest prefix first (hash_crypto before hash)
        for prefix in sorted(_PREFIX_HEADERS, key=len, reverse=True):
            if rest.startswith(prefix + "_") or rest == prefix:
                self._needed_headers.add(_PREFIX_HEADERS[prefix])
                return

    @staticmethod
    def _flatten_requires(requires: list[Expr]) -> list[Expr]:
        """Flatten &&-conjunctions in requires expressions."""
        flat: list[Expr] = []
        stack = list(requires)
        while stack:
            e = stack.pop()
            if isinstance(e, BinaryExpr) and e.op == "&&":
                stack.append(e.left)
                stack.append(e.right)
            else:
                flat.append(e)
        return flat

    def _is_requires_narrowed(
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
        for req_expr in self._flatten_requires(self._current_requires):
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

    def _narrow_for_requires(self, expr: Expr, inferred: Type) -> Type:
        """Narrow Result<T,E>/Option<T> to T if expr is mentioned in requires valid."""
        if not self._current_requires:
            return inferred
        if not isinstance(expr, IdentifierExpr):
            return inferred
        if not (
            isinstance(inferred, GenericInstance)
            and inferred.base_name in ("Option", "Result")
            and inferred.args
        ):
            return inferred
        param_name = expr.name
        for req_expr in self._flatten_requires(self._current_requires):
            # requires valid func(param) form
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                for a in req_expr.args:
                    if isinstance(a, IdentifierExpr) and a.name == param_name:
                        return inferred.args[0]
            # requires func(param) form (CallExpr with validates function)
            if isinstance(req_expr, CallExpr):
                for a in req_expr.args:
                    if isinstance(a, IdentifierExpr) and a.name == param_name:
                        return inferred.args[0]
        return inferred

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
        if not self._is_requires_narrowed(sig.name, call_args, module_name):
            return call_str
        # Resolve type variables against actual arg types
        actual_types = [self._infer_expr_type(a) for a in call_args]
        bindings = resolve_type_vars(sig.param_types, actual_types)
        inner = substitute_type_vars(ret.args[0], bindings)
        inner_ct = map_type(inner)
        cast = f"({inner_ct.decl})" if inner_ct.is_pointer else f"({inner_ct.decl})(intptr_t)"
        return f"{cast}{call_str}.value"

    def _maybe_unwrap_result(
        self,
        call_str: str,
        sig: FunctionSignature,
        call_args: list[Expr],
        module_name: str,
    ) -> str:
        """If the call returns Result<T,E> and is narrowed by requires, unwrap."""
        from prove.symbols import FunctionSignature

        if not isinstance(sig, FunctionSignature):
            return call_str
        ret = sig.return_type
        if not (isinstance(ret, GenericInstance) and ret.base_name == "Result" and ret.args):
            return call_str
        if not self._is_requires_narrowed(sig.name, call_args, module_name):
            return call_str
        # Resolve type variables against actual arg types
        actual_types = [self._infer_expr_type(a) for a in call_args]
        bindings = resolve_type_vars(sig.param_types, actual_types)
        inner = substitute_type_vars(ret.args[0], bindings)
        tmp = self._tmp()
        self._line(f"Prove_Result {tmp} = {call_str};")
        return self._unwrap_result_value(tmp, inner)

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

    def _c_returns_value_ptr(self, expr: Expr) -> bool:
        """Check if a call expression returns Prove_Value* at the C level.

        This detects cases where type variable resolution specialized the
        Prove return type (e.g. Value → String) but the C function still
        returns Prove_Value*.
        """
        sig = self._resolve_call_sig(expr)
        if sig and sig.return_type:
            ct = map_type(sig.return_type)
            return ct.decl == "Prove_Value*"
        return False

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
                    cast = f"({inner_ct.decl})"
                else:
                    default_val = "0"
                    cast = f"({inner_ct.decl})(intptr_t)"
                return f"({expr_str}.tag == 1 ? {cast}{expr_str}.value : {default_val})"
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
                    # Use a temp to avoid double-evaluation of the expression
                    opt_tmp = self._tmp()
                    self._line(f"Prove_Option {opt_tmp} = {arg_str};")
                    # Only unwrap if Some (tag == 1), otherwise use default value
                    if inner_ct.is_pointer or inner_ct.decl == "Prove_String*":
                        default_val = "NULL"
                        cast = f"({param_ct.decl})"
                    else:
                        default_val = "0"
                        cast = f"({param_ct.decl})(intptr_t)"
                    result[i] = f"({opt_tmp}.tag == 1 ? {cast}{opt_tmp}.value : {default_val})"
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
                # Compound: Result<Value, E> → concrete: unwrap + extract
                if inner_ct.decl == "Prove_Value*":
                    unwrapped = f"(Prove_Value*)prove_result_unwrap_ptr({arg_str})"
                    if param_ct.decl == "Prove_String*":
                        result[i] = f"prove_value_as_text({unwrapped})"
                        continue
                    if not param_ct.is_pointer and param_ct.decl in (
                        "int64_t",
                        "int32_t",
                        "int16_t",
                        "int8_t",
                        "uint64_t",
                        "uint32_t",
                        "uint16_t",
                        "uint8_t",
                    ):
                        result[i] = f"prove_value_as_number({unwrapped})"
                        continue
                    if param_ct.decl in ("double", "float"):
                        result[i] = f"prove_value_as_decimal({unwrapped})"
                        continue
                    if param_ct.decl == "bool":
                        result[i] = f"prove_value_as_bool({unwrapped})"
                        continue
                # Result<T, E> → Value*: unwrap + wrap as Value
                if param_ct.decl == "Prove_Value*":
                    if inner_ct.decl == "Prove_Table*":
                        result[i] = (
                            f"prove_value_object(({inner_ct.decl})prove_result_unwrap_ptr({arg_str}))"
                        )
                    elif inner_ct.decl == "Prove_String*":
                        result[i] = (
                            f"prove_value_text(({inner_ct.decl})prove_result_unwrap_ptr({arg_str}))"
                        )
                    elif inner_ct.decl == "Prove_List*":
                        result[i] = (
                            f"prove_value_array(({inner_ct.decl})prove_result_unwrap_ptr({arg_str}))"
                        )
                    elif inner_ct.is_pointer:
                        result[i] = f"(Prove_Value*)prove_result_unwrap_ptr({arg_str})"
                    elif inner_ct.decl == "double":
                        result[i] = f"prove_value_decimal(prove_result_unwrap_double({arg_str}))"
                    else:
                        result[i] = f"prove_value_number(prove_result_unwrap_int({arg_str}))"
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
            # Value<T> → T (phantom-typed value): cast Prove_Value* to concrete pointer
            if arg_ct.decl == "Prove_Value*" and param_ct.is_pointer:
                result[i] = f"(({param_ct.decl}){arg_str})"
                continue
            # concrete → Prove_Value*: wrap as Value
            if param_ct.decl == "Prove_Value*" and arg_ct.decl != "Prove_Value*":
                if arg_ct.decl == "Prove_Table*":
                    result[i] = f"prove_value_object({arg_str})"
                elif arg_ct.decl == "Prove_String*":
                    result[i] = f"prove_value_text({arg_str})"
                elif arg_ct.decl == "Prove_List*":
                    result[i] = f"prove_value_array({arg_str})"
                elif arg_ct.decl == "double":
                    result[i] = f"prove_value_decimal({arg_str})"
                elif arg_ct.decl == "bool":
                    result[i] = f"prove_value_bool({arg_str})"
                elif not arg_ct.is_pointer and arg_ct.decl in (
                    "int64_t",
                    "int32_t",
                    "int16_t",
                    "int8_t",
                    "uint64_t",
                    "uint32_t",
                    "uint16_t",
                    "uint8_t",
                ):
                    result[i] = f"prove_value_number({arg_str})"
                continue
        return result

    def _emit_structured_to_record(
        self,
        arg_expr: str,
        arg_type: Type,
        record_type: RecordType,
    ) -> str:
        """Emit deserialization from structured data to a record.

        Handles Value, Value<T>, Table<Value>, and Result<..., ...>.
        For Result types, unwraps first.  For Value types, extracts the
        object table.  Then delegates to _emit_table_to_record.
        """
        # Result<X, E>: unwrap to inner type first
        if isinstance(arg_type, GenericInstance) and arg_type.base_name == "Result":
            unwrap_tmp = self._tmp()
            self._line(
                f"Prove_Value* {unwrap_tmp} = (Prove_Value*)prove_result_unwrap_ptr({arg_expr});"
            )
            arg_expr = unwrap_tmp

        # Table<Value>: extract table directly
        if isinstance(arg_type, GenericInstance) and arg_type.base_name == "Table":
            tbl_expr = arg_expr
        else:
            # Value / Value<T>: extract the object table
            tbl_tmp = self._tmp()
            self._line(f"Prove_Table* {tbl_tmp} = prove_value_as_object({arg_expr});")
            tbl_expr = tbl_tmp

        rec_tmp = self._emit_table_to_record(tbl_expr, record_type)
        # Wrap in Prove_Result so FailProp (!) can unwrap it
        ct = map_type(record_type)
        heap_tmp = self._tmp()
        self._line(f"{ct.decl}* {heap_tmp} = malloc(sizeof({ct.decl}));")
        self._line(f"*{heap_tmp} = {rec_tmp};")
        res_tmp = self._tmp()
        self._line(f"Prove_Result {res_tmp} = prove_result_ok_ptr({heap_tmp});")
        return res_tmp

    def _emit_table_to_record(
        self,
        table_expr: str,
        record_type: RecordType,
    ) -> str:
        """Emit code that maps a Prove_Table* to a record struct.

        For each record field, looks up the key in the table, panics if
        missing, and converts the Value to the field's C type.  Nested
        record fields are handled recursively.
        """
        field_args: list[str] = []
        for fname, ftype in record_type.fields.items():
            opt_tmp = self._tmp()
            self._line(
                f"Prove_Option {opt_tmp} = prove_table_get("
                f'prove_string_from_cstr("{fname}"), '
                f"{table_expr});"
            )
            # Option<T> fields: pass the Prove_Option directly (absent = None)
            if isinstance(ftype, GenericInstance) and ftype.base_name == "Option":
                field_args.append(opt_tmp)
                continue
            _func_span = getattr(self._current_func, "span", None) if self._current_func else None
            _loc = f" ({_func_span.file}:{_func_span.start_line})" if _func_span else ""
            self._line("#ifndef PROVE_RELEASE")
            self._line(
                f"if ({opt_tmp}.tag == 0) prove_panic("
                f'"Tried to map non existent value '
                f"'{fname}' to type '{record_type.name}'{_loc}\");"
            )
            self._line("#endif")
            val_tmp = self._tmp()
            self._line(f"Prove_Value* {val_tmp} = (Prove_Value*){opt_tmp}.value;")
            # Resolve field to concrete C value
            resolved = (
                self._symbols.resolve_type(ftype.name)
                if isinstance(ftype, PrimitiveType)
                else ftype
            )
            if isinstance(resolved, RecordType):
                # Nested record: extract inner table and recurse
                tbl_tmp = self._tmp()
                self._line(f"Prove_Table* {tbl_tmp} = prove_value_as_object({val_tmp});")
                inner = self._emit_table_to_record(
                    tbl_tmp,
                    resolved,
                )
                field_args.append(inner)
            else:
                coerced = self._value_coercion_expr(
                    val_tmp,
                    ftype,
                )
                field_args.append(
                    coerced if coerced else val_tmp,
                )
        result_tmp = self._tmp()
        ct = map_type(record_type)
        self._line(f"{ct.decl} {result_tmp} = {record_type.name}({', '.join(field_args)});")
        return result_tmp

    def _emit_call(self, expr: CallExpr) -> str:
        # CSE: fused multi-reduce object() cache substitution
        cache = getattr(self, "_fused_object_cache", None)
        if (
            cache
            and isinstance(expr.func, IdentifierExpr)
            and expr.func.name == "object"
            and len(expr.args) == 1
            and isinstance(expr.args[0], IdentifierExpr)
            and expr.args[0].name == cache[0]
        ):
            return cache[1]

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
            if name == "all" and len(expr.args) == 2:
                return self._emit_hof_all(expr)
            if name == "any" and len(expr.args) == 2:
                return self._emit_hof_any(expr)
            if name == "find" and len(expr.args) == 2:
                return self._emit_hof_find(expr)
            if name == "reduce" and len(expr.args) == 3:
                return self._emit_hof_reduce(expr)
            if name == "par_map" and len(expr.args) == 2:
                return self._emit_hof_par_map(expr)
            if name == "par_filter" and len(expr.args) == 2:
                return self._emit_hof_par_filter(expr)
            if name == "par_reduce" and len(expr.args) == 3:
                return self._emit_hof_par_reduce(expr)
            if name == "par_each" and len(expr.args) == 2:
                return self._emit_hof_par_each(expr)
            # Fused iterator patterns from optimizer
            if name == "__fused_map_filter" and len(expr.args) == 3:
                return self._emit_fused_map_filter(expr)
            if name == "__fused_filter_map" and len(expr.args) == 3:
                return self._emit_fused_filter_map(expr)
            if name == "__fused_map_map" and len(expr.args) == 3:
                return self._emit_fused_map_map(expr)
            if name == "__fused_filter_filter" and len(expr.args) == 3:
                return self._emit_fused_filter_filter(expr)
            if name == "__fused_reduce_map" and len(expr.args) == 4:
                return self._emit_fused_reduce_map(expr)
            if name == "__fused_reduce_filter" and len(expr.args) == 4:
                return self._emit_fused_reduce_filter(expr)
            if name == "__fused_each_map" and len(expr.args) == 3:
                return self._emit_fused_each_map(expr)
            if name == "__fused_each_filter" and len(expr.args) == 3:
                return self._emit_fused_each_filter(expr)
            if name == "__fused_multi_reduce":
                return self._emit_fused_multi_reduce(expr)
            if name == "__fused_multi_reduce_ref":
                return self._emit_fused_multi_reduce_ref(expr)

        args = [self._emit_expr(a) for a in expr.args]

        # Wrap record args with record-to-Value converters when needed
        args = self._wrap_record_to_value_args(expr, args)

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name

            # Optimization: detect console(string(float_expr)) pattern and replace with printf
            # The Prove code "console(string(x))" becomes prove_println(...)
            if name == "console" and len(expr.args) == 1:
                arg_expr = expr.args[0]
                # Check if the argument is a call to string(float)
                if isinstance(arg_expr, CallExpr):
                    inner_func = arg_expr.func
                    if isinstance(inner_func, IdentifierExpr) and inner_func.name == "string":
                        # Check if string's argument is a Float type
                        if len(arg_expr.args) == 1:
                            inner_arg = arg_expr.args[0]
                            arg_type = self._infer_expr_type(inner_arg)
                            if (
                                arg_type
                                and isinstance(arg_type, PrimitiveType)
                                and arg_type.name in ("Float", "Decimal")
                            ):
                                # Emit the inner float expression directly
                                inner_c = self._emit_expr(inner_arg)
                                return f'printf("%f\\n", {inner_c})'

            # Type-aware dispatch for len
            if name == "len" and expr.args:
                arg_type = self._infer_expr_type(expr.args[0])
                if isinstance(arg_type, PrimitiveType) and arg_type.name == "String":
                    return f"prove_string_len({', '.join(args)})"
                return f"prove_list_len({', '.join(args)})"

            # unwrap(Option<Value>) → prove_option_unwrap with typed cast
            # Only use runtime unwrap if there's no user-defined unwrap function
            if name == "unwrap" and len(args) == 1 and expr.args:
                arg_ty = self._infer_expr_type(expr.args[0])
                if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Option":
                    from prove.stdlib_loader import is_stdlib_module

                    user_sig = self._symbols.resolve_function_any("unwrap", arity=1)
                    has_user_unwrap = (
                        user_sig is not None
                        and user_sig.module is not None
                        and not is_stdlib_module(user_sig.module)
                        and not is_stdlib_module(user_sig.module.capitalize())
                    )
                    if not has_user_unwrap:
                        inner_ty = arg_ty.args[0] if arg_ty.args else INTEGER
                        inner_ct = map_type(inner_ty)
                        if inner_ct.is_pointer:
                            return f"({inner_ct.decl})prove_option_unwrap({args[0]})"
                        return f"({inner_ct.decl})(intptr_t)prove_option_unwrap({args[0]})"
                # Result unwrap
                if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Result":
                    if arg_ty.args:
                        inner_ct = map_type(arg_ty.args[0])
                        if inner_ct.is_pointer:
                            return f"prove_result_unwrap_ptr({args[0]})"
                        if inner_ct.decl == "double":
                            return f"prove_result_unwrap_double({args[0]})"
                        return f"prove_result_unwrap_int({args[0]})"

            # unwrap(Option<Value>, default) → prove_error_unwrap_or with wrapped default
            if name == "unwrap" and len(args) == 2 and expr.args:
                arg_ty = self._infer_expr_type(expr.args[0])
                if (
                    isinstance(arg_ty, GenericInstance)
                    and arg_ty.base_name == "Option"
                    and arg_ty.args
                    and getattr(arg_ty.args[0], "name", None) == "Value"
                ):
                    default_ty = self._infer_expr_type(expr.args[1])
                    default_ct = map_type(default_ty)
                    default_c = args[1]
                    if default_ct.decl == "Prove_String*":
                        default_c = f"prove_value_text({default_c})"
                    elif default_ct.decl in (
                        "int64_t",
                        "int32_t",
                        "int16_t",
                        "int8_t",
                        "uint64_t",
                        "uint32_t",
                        "uint16_t",
                        "uint8_t",
                    ):
                        default_c = f"prove_value_number({default_c})"
                    elif default_ct.decl in ("double", "float"):
                        default_c = f"prove_value_decimal({default_c})"
                    elif default_ct.decl == "bool":
                        default_c = f"prove_value_boolean({default_c})"
                    self._needed_headers.add("prove_error.h")
                    return f"prove_error_unwrap_or({args[0]}, {default_c})"

            # Builtin mapping
            if name in BUILTIN_MAP:
                c_name = BUILTIN_MAP[name]
                return f"{c_name}({', '.join(args)})"

            # Foreign (C FFI) functions — emit direct C call, no mangling
            if name in self._foreign_names:
                sig = self._symbols.resolve_function(None, name, len(expr.args))
                if sig:
                    args = self._coerce_call_args(args, expr.args, sig)
                return f"{name}({', '.join(args)})"

            # Binary bridge: stdlib binary functions → C runtime
            n_args = len(expr.args)
            sig = self._symbols.resolve_function(None, name, n_args)
            # When verb=None lookup is ambiguous, prefer the overload whose verb
            # matches the current enclosing function (e.g. 'outputs dir' vs 'inputs dir').
            if sig is None:
                current_verb = getattr(self._current_func, "verb", None)
                if current_verb:
                    sig = self._symbols.resolve_function(current_verb, name, n_args)
            # Type-based disambiguation for overloaded stdlib functions
            if expr.args:
                from prove.types import types_compatible

                actual_types = [self._infer_expr_type(a) for a in expr.args]
                narrowed_types = [
                    self._narrow_for_requires(a, t) for a, t in zip(expr.args, actual_types)
                ]
                if sig is None or (
                    sig.param_types
                    and not all(
                        isinstance(p, TypeVariable) or types_compatible(p, a)
                        for p, a in zip(sig.param_types, narrowed_types)
                    )
                ):
                    any_sig = self._symbols.resolve_function_any(
                        name,
                        narrowed_types,
                    )
                    if any_sig is not None:
                        sig = any_sig
            elif sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )
            args_coerced = False
            if sig and sig.module:
                # Emit Verb lambda args before coercion
                for i, pt in enumerate(sig.param_types):
                    if isinstance(pt, FunctionType) and i < len(expr.args):
                        if isinstance(expr.args[i], LambdaExpr):
                            args[i] = self._emit_verb_lambda(expr.args[i], pt)
                args = self._coerce_call_args(args, expr.args, sig)
                args_coerced = True
                c_name: str | None = self._resolve_stdlib_c_name(sig, expr.args)
                if c_name:
                    # Option<T> → tag check for Value-type validators
                    if c_name == "prove_value_is_unit" and len(expr.args) == 1:
                        arg_ty = self._infer_expr_type(expr.args[0])
                        if isinstance(arg_ty, GenericInstance) and arg_ty.base_name == "Option":
                            return f"({args[0]}.tag == 0)"
                    # prove_store_merge takes a 4th resolver arg (NULL = no resolver)
                    if c_name == "prove_store_merge" and len(args) == 3:
                        args.append("NULL")
                    # prove_store_table_add: unpack store row components
                    if c_name == "prove_store_table_add" and len(args) == 2:
                        row_var = args[1]
                        if hasattr(self, "_store_rows") and row_var in self._store_rows:
                            variant_name, vals_name = self._store_rows[row_var]
                            return f"prove_store_table_add_variant({args[0]}, {variant_name}, {vals_name})"  # noqa: E501
                        # Row arg is the raw variable name — look up by expr
                        if isinstance(expr.args[1], IdentifierExpr):
                            rn = expr.args[1].name
                            if hasattr(self, "_store_rows") and rn in self._store_rows:
                                variant_name, vals_name = self._store_rows[rn]
                                return f"prove_store_table_add_variant({args[0]}, {variant_name}, {vals_name})"  # noqa: E501
                    # Heap-allocate struct args for list ops that take void*
                    if c_name == "prove_list_ops_set" and len(args) >= 3:
                        val_type = (
                            self._infer_expr_type(expr.args[2]) if len(expr.args) > 2 else None
                        )
                        if val_type and isinstance(val_type, (RecordType, AlgebraicType)):
                            vct = map_type(val_type)
                            heap_tmp = self._tmp()
                            self._line(f"{vct.decl} *{heap_tmp} = malloc(sizeof({vct.decl}));")
                            self._line(f"*{heap_tmp} = {args[2]};")
                            args[2] = f"(void*){heap_tmp}"
                    # Release mode: rewrite Array<Boolean> ops to BitArray
                    is_bitarray_set = False
                    if self._release_mode:
                        c_name = self._bitarray_rewrite(c_name)
                        if c_name == "prove_bitarray_set":
                            is_bitarray_set = True
                    call_str = f"{c_name}({', '.join(args)})"
                    # Optimization: replace conversion functions with direct C operations
                    # float(Integer) -> direct cast to double
                    if c_name == "prove_convert_float_int" and len(args) == 1:
                        call_str = f"(double){args[0]}"
                    # In-place mutating functions return void; wrap as comma
                    # expression so the array pointer stays as the result value.
                    if ("set_mut" in c_name or is_bitarray_set) and args:
                        call_str = f"({call_str}, {args[0]})"
                        return call_str
                    call_str = self._maybe_unwrap_option(
                        call_str,
                        sig,
                        expr.args,
                        sig.module,
                    )
                    call_str = self._maybe_unwrap_result(
                        call_str,
                        sig,
                        expr.args,
                        sig.module,
                    )
                    return call_str

            # User function — resolve with type-aware dispatch for overloads
            if sig is None:
                if expr.args:
                    actual = [
                        self._narrow_for_requires(a, self._infer_expr_type(a)) for a in expr.args
                    ]
                    sig = self._symbols.resolve_function_by_types(None, name, actual)
                if sig is None:
                    sig = self._symbols.resolve_function(None, name, n_args)
                if sig is None:
                    sig = self._symbols.resolve_function_any(
                        name,
                        arity=n_args,
                    )

            if sig and sig.verb is not None:
                # Struct-polymorphic call — monomorphise
                if any(isinstance(pt, StructType) for pt in sig.param_types):
                    concrete_types = list(sig.param_types)
                    for i, pt in enumerate(sig.param_types):
                        if isinstance(pt, StructType) and i < len(expr.args):
                            concrete_types[i] = self._infer_expr_type(expr.args[i])
                    template_key = (sig.verb, sig.name, len(sig.param_types))
                    template_fd = self._struct_templates.get(template_key)
                    if template_fd:
                        mangled = self._request_struct_specialisation(template_fd, concrete_types)
                        return f"{mangled}({', '.join(args)})"

                # Resolve function reference args for Verb parameters.
                # When the target function's return type is non-void, emit a
                # void-returning thunk so the call-through cast is ABI-safe.
                from prove.types import UnitType

                for i, pt in enumerate(sig.param_types):
                    if i < len(expr.args) and isinstance(expr.args[i], IdentifierExpr):
                        is_verb_param = (
                            isinstance(pt, PrimitiveType) and pt.name == "Verb"
                        ) or isinstance(pt, FunctionType)
                        if is_verb_param:
                            ref_name = expr.args[i].name
                            if ref_name not in self._locals:
                                ref_sig = self._symbols.resolve_function_any(ref_name)
                                if ref_sig is not None:
                                    ref_mangled = mangle_name(
                                        ref_sig.verb,
                                        ref_sig.name,
                                        ref_sig.param_types,
                                        module=self._sig_module(ref_sig),
                                    )
                                    # Non-void C return (including failable
                                    # functions that return Prove_Result):
                                    # emit a void thunk wrapper to avoid ABI
                                    # mismatch at the void-cast call-through.
                                    needs_thunk = (
                                        not isinstance(ref_sig.return_type, UnitType)
                                        or ref_sig.can_fail
                                    )
                                    if needs_thunk:
                                        thunk = self._emit_verb_thunk(ref_mangled, ref_sig)
                                        args[i] = f"(void*){thunk}"
                                    else:
                                        args[i] = f"(void*){ref_mangled}"

                if not args_coerced:
                    args = self._coerce_call_args(args, expr.args, sig)
                mangled = mangle_name(
                    sig.verb, sig.name, sig.param_types, module=self._sig_module(sig)
                )
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
                    mod_prefix = f"{self._module_name}_" if self._module_name else ""
                    table_name = f"_memo_{mod_prefix}{sig.verb}_{sig.name}"
                    table_size = 32
                    cand = self._memo_info.get_candidate(sig.verb, sig.name)
                    if cand:
                        key = self._get_memo_key(cand, args)
                        idx = f"(({key}) % {table_size})"
                        hit = f"{table_name}[{idx}].valid && {table_name}[{idx}].key == {key}"
                        miss = f"({table_name}[{idx}].key = {key}, {table_name}[{idx}].value = {call}, {table_name}[{idx}].valid = 1, {table_name}[{idx}].value)"  # noqa: E501
                        result = f"({hit}) ? {table_name}[{idx}].value : ({miss})"
                        return result

                return call

            # Call through Verb-typed parameter: cast void* to function pointer.
            # All Verb thunks are normalised to void return (see _emit_verb_thunk),
            # so the cast here is always void-returning.
            local_ty = self._locals.get(name)
            if local_ty is not None and (
                (isinstance(local_ty, PrimitiveType) and local_ty.name == "Verb")
                or isinstance(local_ty, FunctionType)
            ):
                arg_c_types = [map_type(self._infer_expr_type(a)).decl for a in expr.args]
                cast = f"void (*)({', '.join(arg_c_types)})" if arg_c_types else "void (*)(void)"
                return f"(({cast}){name})({', '.join(args)})"

            # Variant constructor or unknown — namespace variant constructors
            parent = self._get_variant_parent(name)
            if parent is not None:
                cname = mangle_type_name(parent.name)
                args = self._wrap_recursive_constructor_args(name, args, expr.args)
                return f"{cname}_{name}({', '.join(args)})"
            args = self._wrap_recursive_constructor_args(name, args, expr.args)
            return f"{name}({', '.join(args)})"

        if isinstance(expr.func, TypeIdentifierExpr):
            name = expr.func.name
            # Store-backed lookup row construction: Color(Red, "red", 0xFF0000)
            if name in self._store_lookup_types:
                return self._emit_store_row_construction(name, expr, args)
            # Error(String) constructor — produces a Prove_String* error value
            if name == "Error" and len(args) == 1:
                return args[0]
            # ByteArray(String) constructor
            if name == "ByteArray" and len(args) == 1:
                return f"prove_bytes_from_string({args[0]})"
            # List(...) constructor — emit as list creation with pushes
            if name == "List" and args:
                elem_type = self._infer_expr_type(expr.args[0])
                ct = map_type(elem_type)
                tmp = self._tmp()
                self._line(f"Prove_List *{tmp} = prove_list_new({len(args)});")
                for i, arg in enumerate(args):
                    if ct.is_pointer:
                        self._line(f"prove_list_push({tmp}, (void*){arg});")
                    else:
                        self._line(f"prove_list_push({tmp}, (void*)(intptr_t){arg});")
                return tmp
            # Pad record constructors with missing fields using defaults
            resolved = self._symbols.resolve_type(name)
            if isinstance(resolved, RecordType):
                # Single-arg deserialization: Record(structured_data)
                # Convert Value/Value<T>/Table<Value>/Result<...> to record
                if len(expr.args) == 1:
                    arg_ty = self._infer_expr_type(expr.args[0])
                    is_structured = (
                        isinstance(arg_ty, PrimitiveType) and arg_ty.name == "Value"
                    ) or (
                        isinstance(arg_ty, GenericInstance)
                        and arg_ty.base_name in ("Value", "Table", "Result")
                    )
                    if is_structured:
                        return self._emit_structured_to_record(
                            args[0],
                            arg_ty,
                            resolved,
                        )
                # Coerce args to match record field types
                field_types = list(resolved.fields.values())
                fake_sig = type(
                    "Sig",
                    (),
                    {"param_types": field_types},
                )()
                args = self._coerce_call_args(
                    args,
                    expr.args,
                    fake_sig,
                )
                if len(args) < len(resolved.fields):
                    for fname, ftype in itertools.islice(
                        resolved.fields.items(),
                        len(args),
                        None,
                    ):
                        args.append(self._default_for_type(ftype))
            elif len(args) < len(getattr(resolved, "fields", {})):
                for fname, ftype in itertools.islice(resolved.fields.items(), len(args), None):
                    args.append(self._default_for_type(ftype))
            # In renders/listens loop, variant calls are event self-dispatches
            # (e.g. Draw(state) enqueues a Draw event on the event queue)
            if self._in_renders_loop or self._in_listens_loop:
                # Resolve the concrete event type:
                # - renders: use the function's event_type (TodoEvent)
                # - listens: use the function's return type (TodoEvent)
                func_sig = (
                    self._symbols.resolve_function(
                        self._current_func.verb,
                        self._current_func.name,
                        len(self._current_func.params),
                    )
                    if self._current_func
                    else None
                )
                if self._in_renders_loop:
                    event_type = func_sig.event_type if func_sig else None
                else:
                    event_type = func_sig.return_type if func_sig else None
                # Verify this is actually a variant of the event type
                if (
                    event_type
                    and isinstance(event_type, AlgebraicType)
                    and any(v.name == name for v in event_type.variants)
                ):
                    evt_cname = map_type(event_type).decl
                    tag = f"{evt_cname}_TAG_{name.upper()}"
                    if self._in_renders_loop:
                        self._line(f"prove_event_queue_send(_eq, {tag}, NULL);")
                    else:
                        # In listens translator — set result tag.
                        # Do NOT return here: the switch break + function
                        # epilogue handles *_state_ptr = state and return.
                        self._line(f"_result.tag = {tag};")
                    return "(void)0"
            # Check if it's a variant constructor — namespace to avoid collisions
            parent = self._get_variant_parent(name)
            if parent is not None:
                cname = mangle_type_name(parent.name)
                args = self._wrap_recursive_constructor_args(name, args, expr.args)
                return f"{cname}_{name}({', '.join(args)})"
            sig = self._symbols.resolve_function(None, name, len(expr.args))
            if sig:
                args = self._wrap_recursive_constructor_args(name, args, expr.args)
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
                actual = [self._narrow_for_requires(a, self._infer_expr_type(a)) for a in expr.args]
                sig = self._symbols.resolve_function_by_types(None, name, actual)
            if sig is None:
                sig = self._symbols.resolve_function(None, name, n_args)
            if sig is None:
                sig = self._symbols.resolve_function_any(
                    name,
                    arity=n_args,
                )
            if sig and sig.module:
                # Emit Verb lambda args before coercion
                for i, pt in enumerate(sig.param_types):
                    if isinstance(pt, FunctionType) and i < len(expr.args):
                        if isinstance(expr.args[i], LambdaExpr):
                            args[i] = self._emit_verb_lambda(expr.args[i], pt)
                args = self._coerce_call_args(args, expr.args, sig)
                c_name: str | None = self._resolve_stdlib_c_name(sig)
                if c_name:
                    call_str = f"{c_name}({', '.join(args)})"
                    call_str = self._maybe_unwrap_option(
                        call_str,
                        sig,
                        expr.args,
                        module_name,
                    )
                    call_str = self._maybe_unwrap_result(
                        call_str,
                        sig,
                        expr.args,
                        module_name,
                    )
                    return call_str
            if sig and sig.verb is not None:
                # Struct-polymorphic call — monomorphise
                if any(isinstance(pt, StructType) for pt in sig.param_types):
                    concrete_types = list(sig.param_types)
                    for i, pt in enumerate(sig.param_types):
                        if isinstance(pt, StructType) and i < len(expr.args):
                            concrete_types[i] = self._infer_expr_type(expr.args[i])
                    template_key = (sig.verb, sig.name, len(sig.param_types))
                    template_fd = self._struct_templates.get(template_key)
                    if template_fd:
                        mangled = self._request_struct_specialisation(template_fd, concrete_types)
                        call_str = f"{mangled}({', '.join(args)})"
                        call_str = self._maybe_unwrap_option(
                            call_str,
                            sig,
                            expr.args,
                            module_name,
                        )
                        call_str = self._maybe_unwrap_result(
                            call_str,
                            sig,
                            expr.args,
                            module_name,
                        )
                        return call_str

                # Emit Verb lambda args before coercion
                for i, pt in enumerate(sig.param_types):
                    if isinstance(pt, FunctionType) and i < len(expr.args):
                        if isinstance(expr.args[i], LambdaExpr):
                            args[i] = self._emit_verb_lambda(expr.args[i], pt)
                args = self._coerce_call_args(args, expr.args, sig)
                mangled = mangle_name(
                    sig.verb, sig.name, sig.param_types, module=self._sig_module(sig)
                )
                call_str = f"{mangled}({', '.join(args)})"
                call_str = self._maybe_unwrap_option(
                    call_str,
                    sig,
                    expr.args,
                    module_name,
                )
                call_str = self._maybe_unwrap_result(
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

    @staticmethod
    def _hof_box(expr: str, ct: CType) -> str:
        """Box a typed value into void* for HOF callbacks."""
        if ct.is_pointer:
            return f"(void*){expr}"
        if ct.decl in ("double", "float"):
            return f"_prove_f64_box({expr})"
        # Struct types (non-pointer Prove_* types) must be heap-allocated
        if ct.decl.startswith("Prove_"):
            return f"({{{ct.decl} *_bx = malloc(sizeof({ct.decl})); *_bx = {expr}; (void*)_bx;}})"
        return f"(void*)(intptr_t){expr}"

    @staticmethod
    def _hof_unbox(expr: str, ct: CType) -> str:
        """Unbox a void* into a typed value for HOF callbacks."""
        if ct.is_pointer:
            return f"({ct.decl}){expr}"
        if ct.decl in ("double", "float"):
            return f"_prove_f64_unbox({expr})"
        # Struct types: dereference the heap-allocated pointer
        if ct.decl.startswith("Prove_"):
            return f"(*({ct.decl}*){expr})"
        return f"({ct.decl})(intptr_t){expr}"

    def _emit_hof_map(self, expr: CallExpr) -> str:
        """Emit prove_list_map or prove_array_map depending on collection type."""
        coll_type = self._infer_expr_type(expr.args[0])

        if isinstance(coll_type, ArrayType):
            return self._emit_array_hof_map(expr, coll_type)

        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])

        # Infer element type from the list
        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]

        # Determine result element type (may differ from input, e.g. Integer → String)
        fn_expr = expr.args[1]
        if isinstance(fn_expr, IdentifierExpr):
            fn_sig = self._symbols.resolve_function_any(fn_expr.name, arity=1)  # noqa: F841
        elif isinstance(fn_expr, LambdaExpr):
            # Infer from lambda body
            saved = dict(self._locals)
            if fn_expr.params:
                self._locals[fn_expr.params[0]] = elem_type
            self._infer_expr_type(fn_expr.body)
            self._locals = saved

        # Emit lambda with correct types
        fn_name, ctx_arg = self._emit_hof_lambda(fn_expr, elem_type, "map")
        return f"prove_list_map({list_arg}, {fn_name}, {ctx_arg})"

    def _emit_hof_par_map(self, expr: CallExpr) -> str:
        """Emit prove_par_map(list, fn, 0) — parallel map with auto-detect workers."""
        self._needed_headers.add("prove_par_map.h")
        list_arg = self._emit_expr(expr.args[0])

        coll_type = self._infer_expr_type(expr.args[0])
        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]

        fn_name, ctx_arg = self._emit_hof_lambda(expr.args[1], elem_type, "map")
        return f"prove_par_map({list_arg}, {fn_name}, {ctx_arg}, 0)"

    def _emit_hof_par_filter(self, expr: CallExpr) -> str:
        """Emit prove_par_filter(list, pred, 0) — parallel filter with auto-detect workers."""
        self._needed_headers.add("prove_par_map.h")
        list_arg = self._emit_expr(expr.args[0])

        coll_type = self._infer_expr_type(expr.args[0])
        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]

        fn_name, ctx_arg = self._emit_hof_lambda(expr.args[1], elem_type, "filter")
        return f"prove_par_filter({list_arg}, {fn_name}, {ctx_arg}, 0)"

    def _emit_hof_par_reduce(self, expr: CallExpr) -> str:
        """Emit prove_par_reduce(list, init, fn, 0) — parallel reduce with auto-detect workers."""
        self._needed_headers.add("prove_par_map.h")
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])

        coll_type = self._infer_expr_type(expr.args[0])
        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]

        accum_type = self._infer_expr_type(expr.args[1])
        accum_ct = map_type(accum_type)

        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[1])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        fn_name, ctx_arg = self._emit_hof_lambda(
            expr.args[2],
            elem_type,
            "reduce",
            accum_type=accum_type,
        )
        init_cast = self._hof_box(accum_tmp, accum_ct)
        result_tmp = self._tmp()
        self._line(
            f"void *{result_tmp} = prove_par_reduce("
            f"{list_arg}, {init_cast}, {fn_name}, {ctx_arg}, 0);"
        )
        return self._hof_unbox(result_tmp, accum_ct)

    def _emit_hof_par_each(self, expr: CallExpr) -> str:
        """Emit prove_par_each(list, fn, 0) — parallel each with auto-detect workers."""
        self._needed_headers.add("prove_par_map.h")
        list_arg = self._emit_expr(expr.args[0])

        coll_type = self._infer_expr_type(expr.args[0])
        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]

        fn_name, ctx_arg = self._emit_hof_lambda(expr.args[1], elem_type, "each")
        return f"prove_par_each({list_arg}, {fn_name}, {ctx_arg}, 0)"

    def _emit_hof_each(self, expr: CallExpr) -> str:
        """Emit each as inline loop (avoids closure issues)."""
        coll_type = self._infer_expr_type(expr.args[0])
        if isinstance(coll_type, ArrayType):
            return self._emit_array_hof_each(expr, coll_type)

        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            self._line("")
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1
            elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
            self._line(f"{elem_ct.decl} {param} = {elem_get};")
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            # Retain captured pointer vars before the call — the callee
            # releases its params, but we reuse captured vars each iteration.
            self._emit_loop_body_retains(lam.body, param)
            body_code = self._emit_expr(lam.body)
            # If lambda body is a bare function reference (not a local var),
            # resolve it to a proper C function call with the lambda param.
            if (
                isinstance(lam.body, IdentifierExpr)
                and lam.body.name != param
                and lam.body.name not in saved_locals
            ):
                fn_ref = lam.body.name
                n_params = len(lam.params) if lam.params else 0
                fn_sig = self._symbols.resolve_function_any(fn_ref, arity=n_params)
                if fn_sig is None:
                    fn_sig = self._symbols.resolve_function(None, fn_ref, n_params)
                if fn_sig:
                    if fn_sig.module:
                        c_name = self._resolve_stdlib_c_name(fn_sig)
                        if c_name:
                            body_code = f"{c_name}({param})"
                    elif fn_sig.verb is not None:
                        mangled = mangle_name(
                            fn_sig.verb,
                            fn_sig.name,
                            fn_sig.param_types,
                            module=self._sig_module(fn_sig),
                        )
                        body_code = f"{mangled}({param})"
            self._locals = saved_locals
            self._line(f"{body_code};")
            self._indent -= 1
            self._line("}")
            return "(void)0"
        # Non-lambda IdentifierExpr: inline loop with resolved function call
        if isinstance(lam, IdentifierExpr):
            fn_sig = self._symbols.resolve_function_any(lam.name, arity=1)
            if fn_sig is None:
                fn_sig = self._symbols.resolve_function(None, lam.name, 1)
            if fn_sig:
                if fn_sig.module:
                    c_fn = self._resolve_stdlib_c_name(fn_sig)
                    if c_fn is None:
                        c_fn = mangle_name(
                            fn_sig.verb,
                            fn_sig.name,
                            fn_sig.param_types,
                            module=self._sig_module(fn_sig),
                        )
                else:
                    c_fn = mangle_name(fn_sig.verb, fn_sig.name, fn_sig.param_types)
                if c_fn:
                    param = self._named_tmp("x")
                    idx = self._named_tmp("i")
                    self._line("")
                    self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
                    self._indent += 1
                    elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
                    self._line(f"{elem_ct.decl} {param} = {elem_get};")
                    self._line(f"{c_fn}({param});")
                    self._indent -= 1
                    self._line("}")
                    return "(void)0"
        # Fall back to prove_list_each with callback wrapper
        self._needed_headers.add("prove_hof.h")
        fn_name, ctx_arg = self._emit_hof_lambda(lam, elem_type, "each")
        return f"prove_list_each({list_arg}, {fn_name}, {ctx_arg})"

    def _emit_hof_filter(self, expr: CallExpr) -> str:
        """Emit prove_list_filter or prove_array_filter depending on collection type."""
        coll_type = self._infer_expr_type(expr.args[0])

        if isinstance(coll_type, ArrayType):
            return self._emit_array_hof_filter(expr, coll_type)

        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])

        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]

        fn_name, ctx_arg = self._emit_hof_lambda(expr.args[1], elem_type, "filter")
        filtered = f"prove_list_filter({list_arg}, {fn_name}, {ctx_arg})"

        # filter(List<Option<T>>, |x| unit(x) == false) → unwrap Options to List<T>
        if (
            isinstance(elem_type, GenericInstance)
            and elem_type.base_name == "Option"
            and elem_type.args
            and self._is_option_none_filter(expr.args[1])
        ):
            inner_ct = map_type(elem_type.args[0])
            tmp_filtered = self._tmp()
            tmp_unwrapped = self._tmp()
            self._line(f"Prove_List *{tmp_filtered} = {filtered};")
            self._line(f"Prove_List *{tmp_unwrapped} = prove_list_new({tmp_filtered}->length);")
            idx = self._tmp()
            self._line(f"for (int64_t {idx} = 0; {idx} < {tmp_filtered}->length; {idx}++) {{")
            self._indent += 1
            self._line(f"Prove_Option _opt = (*(Prove_Option*){tmp_filtered}->data[{idx}]);")
            if inner_ct.is_pointer:
                self._line(f"prove_list_push({tmp_unwrapped}, (void*)({inner_ct.decl})_opt.value);")
            else:
                self._line(f"prove_list_push({tmp_unwrapped}, _opt.value);")
            self._indent -= 1
            self._line("}")
            return tmp_unwrapped

        return filtered

    def _emit_hof_all(self, expr: CallExpr) -> str:
        """Emit all as inline loop — true if predicate holds for every element."""
        coll_type = self._infer_expr_type(expr.args[0])

        self._needed_headers.add("prove_list.h")
        list_arg = self._emit_expr(expr.args[0])

        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        result_var = self._tmp()
        self._line(f"bool {result_var} = true;")

        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1
            elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
            self._line(f"{elem_ct.decl} {param} = {elem_get};")
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(lam.body)
            self._locals = saved_locals
            self._line(f"if (!({body_code})) {{ {result_var} = false; break; }}")
            self._indent -= 1
            self._line("}")
            return result_var

        # Fallback: use prove_list_all with callback wrapper
        self._needed_headers.add("prove_hof.h")
        fn_name, ctx_arg = self._emit_hof_lambda(lam, elem_type, "filter")
        return f"prove_list_all({list_arg}, {fn_name}, {ctx_arg})"

    def _emit_hof_any(self, expr: CallExpr) -> str:
        """Emit any as inline loop — true if predicate holds for at least one element."""
        coll_type = self._infer_expr_type(expr.args[0])

        self._needed_headers.add("prove_list.h")
        list_arg = self._emit_expr(expr.args[0])

        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        result_var = self._tmp()
        self._line(f"bool {result_var} = false;")

        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1
            elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
            self._line(f"{elem_ct.decl} {param} = {elem_get};")
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(lam.body)
            self._locals = saved_locals
            self._line(f"if ({body_code}) {{ {result_var} = true; break; }}")
            self._indent -= 1
            self._line("}")
            return result_var

        # Fallback: use prove_list_any with callback wrapper
        self._needed_headers.add("prove_hof.h")
        fn_name, ctx_arg = self._emit_hof_lambda(lam, elem_type, "filter")
        return f"prove_list_any({list_arg}, {fn_name}, {ctx_arg})"

    def _emit_hof_find(self, expr: CallExpr) -> str:
        """Emit find as inline loop — return first element matching predicate as Option."""
        coll_type = self._infer_expr_type(expr.args[0])

        self._needed_headers.add("prove_list.h")
        list_arg = self._emit_expr(expr.args[0])

        elem_type = INTEGER
        if isinstance(coll_type, ListType):
            elem_type = coll_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        result_var = self._tmp()
        self._line(f"Prove_Option {result_var} = {{ .tag = 0, .value = NULL }};")

        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1
            elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
            self._line(f"{elem_ct.decl} {param} = {elem_get};")
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(lam.body)
            self._locals = saved_locals
            if elem_ct.is_pointer or elem_ct.decl == "Prove_String*":
                box = f"(void*){param}"
            else:
                box = f"(void*)(intptr_t){param}"
            self._line(
                f"if ({body_code}) {{ {result_var}.tag = 1; {result_var}.value = {box}; break; }}"
            )
            self._indent -= 1
            self._line("}")
            return result_var

        # Fallback: use prove_list_filter + first
        self._needed_headers.add("prove_hof.h")
        fn_name, ctx_arg = self._emit_hof_lambda(lam, elem_type, "filter")
        return f"prove_list_ops_first({list_arg}, {fn_name}, {ctx_arg})"

    @staticmethod
    def _collect_string_literals(expr: Expr) -> set[str]:
        """Collect all string literal values from an expression AST."""
        result: set[str] = set()
        stack: list[Expr] = [expr]
        while stack:
            node = stack.pop()
            if isinstance(node, (StringLit, TripleStringLit, RawStringLit, PathLit)):
                result.add(node.value)
            elif isinstance(node, CallExpr):
                stack.extend(node.args)
                stack.append(node.func)
            elif isinstance(node, BinaryExpr):
                stack.append(node.left)
                stack.append(node.right)
            elif isinstance(node, FieldExpr):
                stack.append(node.obj)
            elif isinstance(node, LambdaExpr):
                stack.append(node.body)
        return result

    def _hoist_string_literals(self, literals: set[str]) -> None:
        """Emit hoisted Prove_String* variables for string literals before a loop."""
        for lit in sorted(literals):
            if lit not in self._string_literal_cache:
                escaped = self._escape_c_string(lit)
                if lit.isidentifier() and len(lit) <= 20:
                    tmp = self._named_tmp(f"_str_{lit}")
                else:
                    tmp = self._tmp()
                self._line(f'Prove_String *{tmp} = prove_string_from_cstr("{escaped}");')
                self._string_literal_cache[escaped] = tmp

    def _emit_hof_reduce(self, expr: CallExpr) -> str:
        """Emit reduce as inline for-loop when callback is a lambda."""
        coll_type = self._infer_expr_type(expr.args[0])
        if isinstance(coll_type, ArrayType):
            return self._emit_array_hof_reduce(expr, coll_type)

        callback = expr.args[2]

        # Inline path: lambda callback → direct for-loop (no boxing/indirection)
        if isinstance(callback, LambdaExpr) and len(callback.params) == 2:
            self._needed_headers.add("prove_list.h")
            list_arg, list_type = self._cache_list_arg(expr.args[0])

            elem_type = INTEGER
            if isinstance(list_type, ListType):
                elem_type = list_type.element  # type: ignore[assignment]
            elem_ct = map_type(elem_type)

            accum_type = self._infer_expr_type(expr.args[1])
            accum_ct = map_type(accum_type)

            accum_tmp = self._tmp()
            accum_val = self._emit_expr(expr.args[1])
            self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

            # Hoist string literals before the loop
            self._hoist_string_literals(self._collect_string_literals(callback.body))

            self._line("")
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
            self._indent += 1

            # Direct array access — compiler verified bounds
            elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)

            saved = dict(self._locals)
            saved_hof = self._in_hof_inline
            self._locals[callback.params[0]] = accum_type
            self._locals[callback.params[1]] = elem_type
            self._in_hof_inline = True
            self._line(f"{accum_ct.decl} {callback.params[0]} = {accum_tmp};")
            self._line(f"{elem_ct.decl} {callback.params[1]} = {elem_get};")
            body_code = self._emit_expr(callback.body)
            self._in_hof_inline = saved_hof
            self._locals = saved
            self._line(f"{accum_tmp} = {body_code};")

            self._indent -= 1
            self._line("}")
            return accum_tmp

        # Fallback: function reference → use prove_list_reduce with callback
        self._needed_headers.add("prove_hof.h")
        list_arg = self._emit_expr(expr.args[0])
        list_type = self._infer_expr_type(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]

        accum_type = self._infer_expr_type(expr.args[1])
        accum_ct = map_type(accum_type)

        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[1])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        fn_name, ctx_arg = self._emit_hof_lambda(
            callback,
            elem_type,
            "reduce",
            accum_type=accum_type,
        )
        init_cast = self._hof_box(accum_tmp, accum_ct)
        result_tmp = self._tmp()
        self._line(
            f"void *{result_tmp} = prove_list_reduce("
            f"{list_arg}, {init_cast}, {fn_name}, {ctx_arg});"
        )
        return self._hof_unbox(result_tmp, accum_ct)

    def _emit_verb_lambda(self, expr: LambdaExpr, func_type: FunctionType) -> str:
        """Hoist a lambda for a Verb<...> parameter with correct C signature."""
        name = f"_lambda_{self._tmp_counter}"
        self._tmp_counter += 1

        ret_ct = map_type(func_type.return_type)
        param_cts = [map_type(pt) for pt in func_type.param_types]

        c_params = []
        saved_locals = dict(self._locals)
        for i, pname in enumerate(expr.params):
            if i < len(param_cts):
                c_params.append(f"{param_cts[i].decl} {pname}")
                self._locals[pname] = func_type.param_types[i]

        body_code = self._emit_expr(expr.body)
        self._locals = saved_locals

        param_str = ", ".join(c_params) if c_params else "void"
        lam = f"static {ret_ct.decl} {name}({param_str}) {{\n"
        lam += f"    return {body_code};\n"
        lam += "}\n"
        self._lambdas.append(lam)
        return name

    def _emit_verb_thunk(self, target: str, sig: FunctionSignature) -> str:
        """Emit a void-returning thunk that calls *target* and discards its result.

        This is needed when a non-void function is passed as a bare Verb
        parameter: the call-through site uses a ``void (*)(...)`` cast, so
        the actual target must also be void-returning to avoid ABI mismatches
        (e.g. hidden sret pointer on ARM64).
        """
        thunk_name = f"_verb_thunk_{self._tmp_counter}"
        self._tmp_counter += 1

        param_cts = [map_type(pt) for pt in sig.param_types]
        c_params = []
        call_args = []
        for i, ct in enumerate(param_cts):
            pname = f"_a{i}"
            c_params.append(f"{ct.decl} {pname}")
            call_args.append(pname)

        param_str = ", ".join(c_params) if c_params else "void"
        call_str = f"{target}({', '.join(call_args)})"

        thunk = f"static void {thunk_name}({param_str}) {{\n"
        thunk += f"    (void){call_str};\n"
        thunk += "}\n"
        self._lambdas.append(thunk)
        return thunk_name

    def _lambda_owned_field_retains(
        self,
        body: Expr,
        param: str,
        elem_type: Type,
    ) -> list[str]:
        """Find pointer fields on *param* that need a retain in a hoisted lambda.

        When a field access like ``value.path`` appears as an argument to a
        function call (own position — the callee will release it), we must
        retain it so that any other (borrow) usage of the same pointer in the
        same expression survives the release.

        Returns a list of C expressions (e.g. ``"value->path"``) to retain.
        """
        from prove.ast_nodes import CallExpr, FieldExpr, IdentifierExpr

        owned: set[str] = set()

        def _walk(node: Expr) -> None:
            if isinstance(node, CallExpr):
                # Only real function calls release args; record constructors
                # (TypeIdentifierExpr) do not.
                is_func = isinstance(node.func, IdentifierExpr)
                for arg in node.args:
                    if (
                        is_func
                        and isinstance(arg, FieldExpr)
                        and isinstance(arg.obj, IdentifierExpr)
                        and arg.obj.name == param
                    ):
                        owned.add(arg.field)
                    _walk(arg)
            elif hasattr(node, "left"):
                _walk(node.left)
                _walk(node.right)
            elif isinstance(node, FieldExpr):
                _walk(node.obj)

        _walk(body)

        if not owned:
            return []

        # Keep only pointer-typed fields
        result: list[str] = []
        if isinstance(elem_type, RecordType):
            for fname in owned:
                ftype = elem_type.fields.get(fname)
                if ftype and map_type(ftype).is_pointer:
                    result.append(f"{param}->{fname}")
        else:
            # Binary/opaque struct — we don't have field type info,
            # so retain each owned field access directly (the field
            # is a pointer inside the struct, e.g. value->path).
            elem_ct = map_type(elem_type)
            accessor = "->" if elem_ct.is_pointer else "."
            for fname in owned:
                result.append(f"{param}{accessor}{fname}")
        return result

    def _collect_emitter_captures(
        self,
        body: Expr,
        param_names: set[str],
        captures: list[str],
    ) -> None:
        """Walk a lambda body to find references to enclosing local variables."""
        from prove.ast_nodes import (
            BinaryExpr,
            CallExpr,
            FieldExpr,
            IdentifierExpr,
            UnaryExpr,
        )

        if isinstance(body, IdentifierExpr):
            if (
                body.name not in param_names
                and body.name not in captures
                and body.name in self._locals
            ):
                captures.append(body.name)
        elif isinstance(body, BinaryExpr):
            self._collect_emitter_captures(body.left, param_names, captures)
            self._collect_emitter_captures(body.right, param_names, captures)
        elif isinstance(body, CallExpr):
            self._collect_emitter_captures(body.func, param_names, captures)
            for arg in body.args:
                self._collect_emitter_captures(arg, param_names, captures)
        elif isinstance(body, FieldExpr):
            self._collect_emitter_captures(body.obj, param_names, captures)
        elif isinstance(body, UnaryExpr):
            self._collect_emitter_captures(body.operand, param_names, captures)

    def _emit_hof_lambda(
        self,
        expr: Expr,
        elem_type: Type,
        kind: str,
        *,
        accum_type: Type | None = None,
    ) -> tuple[str, str]:
        """Emit a lambda for HOF use with correct C signature.

        Returns (fn_name, ctx_arg) where ctx_arg is "NULL" when there are
        no captures, or "&_ctx_N" after emitting a stack-allocated ctx struct.
        """
        if isinstance(expr, ValidExpr) and expr.args is None and kind == "filter":
            # valid error → wrap validates function as filter predicate
            sig = self._symbols.resolve_function_any(expr.name)
            pt = list(sig.param_types) if sig else None
            fn = mangle_name(
                "validates", expr.name, pt, module=self._sig_module(sig) if sig else None
            )
            wrapper = f"_lambda_{self._tmp_counter}"
            self._tmp_counter += 1
            elem_ct = map_type(elem_type)
            lam = (
                f"static bool {wrapper}(void *_arg, void *_ctx) {{\n"
                f"    (void)_ctx;\n"
                f"    {elem_ct.decl} _x = {self._hof_unbox('_arg', elem_ct)};\n"
                f"    return {fn}(_x);\n"
                f"}}\n"
            )
            self._lambdas.append(lam)
            return wrapper, "NULL"
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

                # Types.string() dispatches by element type
                _STRING_DISPATCH = {
                    "Integer": "prove_string_from_int",
                    "Float": "prove_string_from_double",
                    "Decimal": "prove_string_from_double",
                    "Boolean": "prove_string_from_bool",
                    "Character": "prove_string_from_char",
                    "Value": "prove_value_as_text",
                    "Time": "prove_time_string_time",
                    "Date": "prove_time_string_date",
                    "DateTime": "prove_time_string_datetime",
                    "Clock": "prove_time_string_clock",
                    "Duration": "prove_time_string_duration",
                }
                if expr.name == "string" and elem_name in _STRING_DISPATCH:
                    c_fn = _STRING_DISPATCH[elem_name]
                    ret_type = STRING
                elif ret_name == "String" and elem_name == "Integer":
                    c_fn = "prove_string_from_int"
                elif ret_name == "String" and elem_name in ("Float", "Decimal"):
                    c_fn = "prove_string_from_double"
                elif ret_name == "String" and elem_name == "Boolean":
                    c_fn = "prove_string_from_bool"
                elif fn_sig and fn_sig.module:
                    c_fn = self._resolve_stdlib_c_name(fn_sig, None)
                    if c_fn is None:
                        # Local module function — use mangled name
                        c_fn = mangle_name(
                            fn_sig.verb,
                            fn_sig.name,
                            list(fn_sig.param_types) if fn_sig.param_types else None,
                            module=fn_sig.module,
                        )
                elif fn_sig and not fn_sig.module:
                    # Same-module function — use mangled name
                    c_fn = mangle_name(
                        fn_sig.verb,
                        fn_sig.name,
                        list(fn_sig.param_types) if fn_sig.param_types else None,
                        module=self._module.name.lower() if self._module else None,
                    )

                # Failable function as HOF callback needs Result unwrapping
                if c_fn and fn_sig and fn_sig.can_fail and kind == "map":
                    wrapper = f"_lambda_{self._tmp_counter}"
                    self._tmp_counter += 1
                    elem_unbox = self._hof_unbox("_arg", elem_ct)
                    # Determine success type from Result<T, Error>
                    success_type = ret_type
                    if (
                        isinstance(ret_type, GenericInstance)
                        and ret_type.base_name == "Result"
                        and ret_type.args
                    ):
                        success_type = ret_type.args[0]
                    success_ct = map_type(success_type)
                    ret_box = self._hof_box(
                        f"({success_ct.decl})prove_result_unwrap_ptr(_r)"
                        if success_ct.is_pointer
                        else f"({success_ct.decl})(intptr_t)prove_result_unwrap_int(_r)",
                        success_ct,
                    )
                    self._needed_headers.add("prove_result.h")
                    lam = (
                        f"static void *{wrapper}(void *_arg, void *_ctx) {{\n"
                        f"    (void)_ctx;\n"
                        f"    {elem_ct.decl} _x = {elem_unbox};\n"
                        f"    Prove_Result _r = {c_fn}(_x);\n"
                        f'    if (prove_result_is_err(_r)) prove_panic("error in map callback");\n'
                        f"    return {ret_box};\n"
                        f"}}\n"
                    )
                    self._lambdas.append(lam)
                    return wrapper, "NULL"

                if c_fn:
                    wrapper = f"_lambda_{self._tmp_counter}"
                    self._tmp_counter += 1
                    ret_ct = map_type(ret_type) if ret_type else elem_ct
                    elem_unbox = self._hof_unbox("_arg", elem_ct)
                    if kind == "map":
                        ret_box = self._hof_box(f"{c_fn}(_x)", ret_ct)
                        lam = (
                            f"static void *{wrapper}(void *_arg, void *_ctx) {{\n"
                            f"    (void)_ctx;\n"
                            f"    {elem_ct.decl} _x = {elem_unbox};\n"
                            f"    return {ret_box};\n"
                            f"}}\n"
                        )
                    elif kind == "filter":
                        lam = (
                            f"static bool {wrapper}(void *_arg, void *_ctx) {{\n"
                            f"    (void)_ctx;\n"
                            f"    {elem_ct.decl} _x = {elem_unbox};\n"
                            f"    return {c_fn}(_x);\n"
                            f"}}\n"
                        )
                    else:
                        return self._emit_expr(expr), "NULL"
                    self._lambdas.append(lam)
                    return wrapper, "NULL"
            return self._emit_expr(expr), "NULL"

        name = f"_lambda_{self._tmp_counter}"
        self._tmp_counter += 1
        elem_ct = map_type(elem_type)

        elem_unbox_arg = self._hof_unbox("_arg", elem_ct)
        elem_unbox_elem = self._hof_unbox("_elem", elem_ct)

        # Collect captures for ctx struct generation.
        # Walk lambda body to find references to enclosing locals.
        captures = self._lambda_captures.get(id(expr))
        if captures is None:
            captures = []
            param_set = set(expr.params) if expr.params else set()
            self._collect_emitter_captures(expr.body, param_set, captures)
            self._lambda_captures[id(expr)] = captures
        has_ctx = bool(captures)
        ctx_struct = ""
        ctx_unpack = ""
        if has_ctx:
            struct_name = f"_ctx_{name}"
            fields = []
            for c in captures:
                cap_type = self._locals.get(c)
                if cap_type is not None:
                    cap_ct = map_type(cap_type)
                    fields.append(f"    {cap_ct.decl} {c};")
                else:
                    fields.append(f"    int64_t {c};")
            ctx_struct = f"struct {struct_name} {{\n" + "\n".join(fields) + "\n};\n"
            self._lambdas.append(ctx_struct)
            unpack_lines = [f"    struct {struct_name} *_c = (struct {struct_name} *)_ctx;"]
            for c in captures:
                cap_type = self._locals.get(c)
                if cap_type is not None:
                    cap_ct = map_type(cap_type)
                    unpack_lines.append(f"    {cap_ct.decl} {c} = _c->{c};")
                else:
                    unpack_lines.append(f"    int64_t {c} = _c->{c};")
            ctx_unpack = "\n".join(unpack_lines) + "\n"
        void_ctx = "" if has_ctx else "    (void)_ctx;\n"

        if kind == "map":
            # void *fn(void *_arg, void *_ctx)
            param = expr.params[0] if expr.params else "_x"
            # Save and set locals for lambda body
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type

            # FailPropExpr (call()!) in lambda body: _emit_fail_prop emits
            # statements via self._line() which would land in the *enclosing*
            # function, not the lambda.  Handle inline instead.
            if isinstance(expr.body, FailPropExpr):
                inner_code = self._emit_expr(expr.body.expr)
                body_type = self._infer_expr_type(expr.body)
                self._locals = saved_locals
                retains = self._lambda_owned_field_retains(expr.body.expr, param, elem_type)
                retain_lines = "".join(f"    prove_retain({r});\n" for r in retains)
                res_var = f"_r_{self._tmp_counter}"
                self._tmp_counter += 1
                lam = (
                    f"static void *{name}(void *_arg, void *_ctx) {{\n"
                    f"{void_ctx}"
                    f"{ctx_unpack}"
                    f"    {elem_ct.decl} {param} = {elem_unbox_arg};\n"
                    f"{retain_lines}"
                    f"    Prove_Result {res_var} = {inner_code};\n"
                    f"    if (prove_result_is_err({res_var}))"
                    f' prove_panic("error in map callback'
                    f" ({expr.span.file}:{expr.span.start_line})"
                    f'");\n'
                    f"    return prove_result_unwrap_ptr({res_var});\n"
                    f"}}\n"
                )
            else:
                body_code = self._emit_expr(expr.body)
                body_type = self._infer_expr_type(expr.body)
                self._locals = saved_locals
                body_ct = map_type(body_type)
                body_box = self._hof_box(body_code, body_ct)
                # Own/borrow: retain pointer fields passed to function calls
                retains = self._lambda_owned_field_retains(expr.body, param, elem_type)
                retain_lines = "".join(f"    prove_retain({r});\n" for r in retains)
                lam = (
                    f"static void *{name}(void *_arg, void *_ctx) {{\n"
                    f"{void_ctx}"
                    f"{ctx_unpack}"
                    f"    {elem_ct.decl} {param} = {elem_unbox_arg};\n"
                    f"{retain_lines}"
                    f"    return {body_box};\n"
                    f"}}\n"
                )
        elif kind == "filter":
            # bool fn(void *_arg, void *_ctx)
            param = expr.params[0] if expr.params else "_x"
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            retains = self._lambda_owned_field_retains(expr.body, param, elem_type)
            retain_lines = "".join(f"    prove_retain({r});\n" for r in retains)
            lam = (
                f"static bool {name}(void *_arg, void *_ctx) {{\n"
                f"{void_ctx}"
                f"{ctx_unpack}"
                f"    {elem_ct.decl} {param} = {elem_unbox_arg};\n"
                f"{retain_lines}"
                f"    return {body_code};\n"
                f"}}\n"
            )
        elif kind == "reduce":
            # void *fn(void *_accum, void *_elem, void *_ctx)
            accum_param = expr.params[0] if len(expr.params) > 0 else "_acc"
            elem_param = expr.params[1] if len(expr.params) > 1 else "_el"
            accum_ct = map_type(accum_type) if accum_type else elem_ct
            accum_unbox = self._hof_unbox("_accum", accum_ct)
            saved_locals = dict(self._locals)
            self._locals[accum_param] = accum_type if accum_type else elem_type
            self._locals[elem_param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            ret_box = self._hof_box(body_code, accum_ct)
            lam = (
                f"static void *{name}(void *_accum, void *_elem, void *_ctx) {{\n"
                f"{void_ctx}"
                f"{ctx_unpack}"
                f"    {accum_ct.decl} {accum_param} = {accum_unbox};\n"
                f"    {elem_ct.decl} {elem_param} = {elem_unbox_elem};\n"
                f"    return {ret_box};\n"
                f"}}\n"
            )
        elif kind == "each":
            # void fn(void *_arg, void *_ctx)
            param = expr.params[0] if expr.params else "_x"
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(expr.body)
            self._locals = saved_locals
            retains = self._lambda_owned_field_retains(expr.body, param, elem_type)
            retain_lines = "".join(f"    prove_retain({r});\n" for r in retains)
            lam = (
                f"static void {name}(void *_arg, void *_ctx) {{\n"
                f"{void_ctx}"
                f"{ctx_unpack}"
                f"    {elem_ct.decl} {param} = {elem_unbox_arg};\n"
                f"{retain_lines}"
                f"    {body_code};\n"
                f"}}\n"
            )
        else:
            return self._emit_expr(expr), "NULL"

        self._lambdas.append(lam)

        # Emit ctx struct initialization at the call site when captures exist
        ctx_arg = "NULL"
        if has_ctx:
            struct_name = f"_ctx_{name}"
            ctx_var = f"_ctxv_{self._tmp_counter}"
            self._tmp_counter += 1
            self._line(f"struct {struct_name} {ctx_var};")
            for c in captures:
                self._line(f"{ctx_var}.{c} = {c};")
            ctx_arg = f"&{ctx_var}"

        return name, ctx_arg

    # ── Array HOF emission ──────────────────────────────────────

    def _cache_array_arg(self, expr: Expr) -> tuple[str, "Type"]:
        """Emit an array expression into a temp variable before loop use."""
        arr_type = self._infer_expr_type(expr)
        # Skip alias when expression is already a simple variable
        if isinstance(expr, IdentifierExpr) and expr.name in self._locals:
            return expr.name, arr_type
        arr_code = self._emit_expr(expr)
        tmp = self._tmp()
        self._line(f"Prove_Array *{tmp} = {arr_code};")
        return tmp, arr_type

    def _array_elem_get(self, arr_var: str, idx_var: str, elem_ct) -> str:
        """Generate C code to get a typed element from an array at index."""
        if elem_ct.decl == "bool":
            if self._release_mode:
                self._needed_headers.add("prove_bitarray.h")
                return f"prove_bitarray_get({arr_var}, {idx_var})"
            return f"prove_array_get_bool({arr_var}, {idx_var})"
        elif elem_ct.decl == "int64_t":
            return f"prove_array_get_int({arr_var}, {idx_var})"
        return f"({elem_ct.decl})prove_array_get({arr_var}, {idx_var})"

    # ── BitArray release-mode rewriting ────────────────────────

    _BITARRAY_REWRITES: dict[str, str] = {
        "prove_array_new_bool": "prove_bitarray_new",
        "prove_array_get_bool": "prove_bitarray_get",
        "prove_array_set_mut_bool": "prove_bitarray_set",
    }

    def _bitarray_rewrite(self, c_name: str) -> str:
        """Rewrite Array<Boolean> runtime calls to BitArray equivalents."""
        rewritten = self._BITARRAY_REWRITES.get(c_name)
        if rewritten:
            self._needed_headers.add("prove_bitarray.h")
            return rewritten
        return c_name

    def _emit_array_hof_map(self, expr: CallExpr, arr_type: ArrayType) -> str:
        """Emit map over Array<T> as inline loop producing a new array."""
        self._needed_headers.add("prove_array.h")
        arr_arg, _ = self._cache_array_arg(expr.args[0])
        elem_type = arr_type.element if arr_type.element else INTEGER
        elem_ct = map_type(elem_type)

        fn_expr = expr.args[1]

        # Infer result element type
        result_elem_type = elem_type
        if isinstance(fn_expr, IdentifierExpr):
            fn_sig = self._symbols.resolve_function_any(fn_expr.name, arity=1)
            if fn_sig:
                result_elem_type = fn_sig.return_type
        elif isinstance(fn_expr, LambdaExpr):
            saved = dict(self._locals)
            if fn_expr.params:
                self._locals[fn_expr.params[0]] = elem_type
            result_elem_type = self._infer_expr_type(fn_expr.body)
            self._locals = saved
        result_ct = map_type(result_elem_type)

        # Allocate result array
        result_tmp = self._tmp()
        zero_tmp = self._tmp()
        self._line(f"{result_ct.decl} {zero_tmp} = 0;")
        self._line(
            f"Prove_Array *{result_tmp} = prove_array_new("
            f"{arr_arg}->length, sizeof({result_ct.decl}), &{zero_tmp});"
        )

        if isinstance(fn_expr, LambdaExpr) and fn_expr.params:
            param = fn_expr.params[0]
            self._line("")
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {arr_arg}->length; {idx}++) {{")
            self._indent += 1
            elem_get = self._array_elem_get(arr_arg, idx, elem_ct)
            self._line(f"{elem_ct.decl} {param} = {elem_get};")
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            body_code = self._emit_expr(fn_expr.body)
            self._locals = saved_locals
            # Store result
            mapped_tmp = self._tmp()
            self._line(f"{result_ct.decl} {mapped_tmp} = {body_code};")
            self._line(
                f"memcpy((char *){result_tmp}->data + {idx} * sizeof({result_ct.decl}), "
                f"&{mapped_tmp}, sizeof({result_ct.decl}));"
            )
            self._indent -= 1
            self._line("}")
            return result_tmp

        # Non-lambda: use runtime function
        fn_name, ctx_arg = self._emit_hof_lambda(fn_expr, elem_type, "map")
        return f"prove_array_map({arr_arg}, {fn_name}, {ctx_arg}, sizeof({result_ct.decl}))"

    def _emit_array_hof_each(self, expr: CallExpr, arr_type: ArrayType) -> str:
        """Emit each over Array<T> as inline loop."""
        self._needed_headers.add("prove_array.h")
        arr_arg, _ = self._cache_array_arg(expr.args[0])
        elem_type = arr_type.element if arr_type.element else INTEGER
        elem_ct = map_type(elem_type)

        lam = expr.args[1]
        if isinstance(lam, LambdaExpr):
            param = lam.params[0] if lam.params else "_x"
            self._line("")
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {arr_arg}->length; {idx}++) {{")
            self._indent += 1
            elem_get = self._array_elem_get(arr_arg, idx, elem_ct)
            self._line(f"{elem_ct.decl} {param} = {elem_get};")
            saved_locals = dict(self._locals)
            self._locals[param] = elem_type
            self._emit_loop_body_retains(lam.body, param)
            body_code = self._emit_expr(lam.body)
            self._locals = saved_locals
            self._line(f"{body_code};")
            self._indent -= 1
            self._line("}")
            return "(void)0"

        # Non-lambda: use runtime function
        self._needed_headers.add("prove_hof.h")
        fn_name, ctx_arg = self._emit_hof_lambda(lam, elem_type, "each")
        return f"prove_array_each({arr_arg}, {fn_name}, {ctx_arg})"

    def _emit_array_hof_filter(self, expr: CallExpr, arr_type: ArrayType) -> str:
        """Emit filter over Array<T> — returns Prove_List* (unknown output length)."""
        self._needed_headers.add("prove_array.h")
        arr_arg = self._emit_expr(expr.args[0])
        elem_type = arr_type.element if arr_type.element else INTEGER

        fn_name, ctx_arg = self._emit_hof_lambda(expr.args[1], elem_type, "filter")
        return f"prove_array_filter({arr_arg}, {fn_name}, {ctx_arg})"

    def _emit_array_hof_reduce(self, expr: CallExpr, arr_type: ArrayType) -> str:
        """Emit reduce over Array<T> as inline for-loop when callback is a lambda."""
        callback = expr.args[2]
        elem_type = arr_type.element if arr_type.element else INTEGER
        elem_ct = map_type(elem_type)

        # Inline path: lambda callback → direct for-loop
        if isinstance(callback, LambdaExpr) and len(callback.params) == 2:
            self._needed_headers.add("prove_array.h")
            arr_arg, _ = self._cache_array_arg(expr.args[0])

            accum_type = self._infer_expr_type(expr.args[1])
            accum_ct = map_type(accum_type)

            accum_tmp = self._tmp()
            accum_val = self._emit_expr(expr.args[1])
            self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

            self._hoist_string_literals(self._collect_string_literals(callback.body))

            self._line("")
            idx = self._named_tmp("i")
            self._line(f"for (int64_t {idx} = 0; {idx} < {arr_arg}->length; {idx}++) {{")
            self._indent += 1

            elem_get = self._array_elem_get(arr_arg, idx, elem_ct)

            saved = dict(self._locals)
            saved_hof = self._in_hof_inline
            self._locals[callback.params[0]] = accum_type
            self._locals[callback.params[1]] = elem_type
            self._in_hof_inline = True
            self._line(f"{accum_ct.decl} {callback.params[0]} = {accum_tmp};")
            self._line(f"{elem_ct.decl} {callback.params[1]} = {elem_get};")
            body_code = self._emit_expr(callback.body)
            self._in_hof_inline = saved_hof
            self._locals = saved
            self._line(f"{accum_tmp} = {body_code};")

            self._indent -= 1
            self._line("}")
            return accum_tmp

        # Fallback: function reference → use runtime
        self._needed_headers.add("prove_array.h")
        arr_arg = self._emit_expr(expr.args[0])

        accum_type = self._infer_expr_type(expr.args[1])
        accum_ct = map_type(accum_type)

        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[1])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        fn_name, ctx_arg = self._emit_hof_lambda(
            callback,
            elem_type,
            "reduce",
            accum_type=accum_type,
        )
        init_cast = self._hof_box(accum_tmp, accum_ct)
        result_tmp = self._tmp()
        self._line(
            f"void *{result_tmp} = prove_array_reduce("
            f"{arr_arg}, {init_cast}, {fn_name}, {ctx_arg});"
        )
        return self._hof_unbox(result_tmp, accum_ct)

    # ── Fused iterator emission ─────────────────────────────────

    def _emit_fused_map_filter(self, expr: CallExpr) -> str:
        """Emit map(filter(list, pred), func) as a single-pass loop.

        Args: [list, pred, func]
        Fuses filter+map into one loop: iterate, test predicate, if passes apply func.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        result_tmp = self._tmp()
        idx = self._named_tmp("i")
        elem_var = self._tmp()

        self._line(f"Prove_List *{result_tmp} = prove_list_new(8);")
        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        unwrap = f"({elem_ct.decl})" if elem_ct.is_pointer else f"({elem_ct.decl})(intptr_t)"
        self._line(f"{elem_ct.decl} {elem_var} = {unwrap}{list_arg}->data[{idx}];")

        # Emit predicate test
        pred_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        self._line(f"if ({pred_code}) {{")
        self._indent += 1

        # Emit map function application — infer result type for correct boxing
        map_fn = expr.args[2]
        map_result_type = elem_type
        if isinstance(map_fn, LambdaExpr) and map_fn.params:
            saved_locals = dict(self._locals)
            self._locals[map_fn.params[0]] = elem_type
            map_result_type = self._infer_expr_type(map_fn.body)
            self._locals = saved_locals
        map_result_ct = map_type(map_result_type)
        map_code = self._emit_fused_lambda_inline(expr.args[2], elem_var, elem_type)
        wrap = self._hof_box(str(map_code), map_result_ct)
        self._line(f"prove_list_push({result_tmp}, {wrap});")

        self._indent -= 1
        self._line("}")
        self._indent -= 1
        self._line("}")
        return result_tmp

    def _emit_fused_filter_map(self, expr: CallExpr) -> str:
        """Emit filter(map(list, func), pred) as a single-pass loop.

        Args: [list, func, pred]
        Fuses map+filter into one loop: iterate, apply func, test predicate on result.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        result_tmp = self._tmp()
        idx = self._named_tmp("i")
        elem_var = self._tmp()
        mapped_var = self._tmp()

        self._line(f"Prove_List *{result_tmp} = prove_list_new(8);")
        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        unwrap = f"({elem_ct.decl})" if elem_ct.is_pointer else f"({elem_ct.decl})(intptr_t)"
        self._line(f"{elem_ct.decl} {elem_var} = {unwrap}{list_arg}->data[{idx}];")

        # Infer the mapped element type from the map lambda
        map_fn = expr.args[1]
        mapped_type = elem_type
        if isinstance(map_fn, LambdaExpr) and map_fn.params:
            saved_locals = dict(self._locals)
            self._locals[map_fn.params[0]] = elem_type
            mapped_type = self._infer_expr_type(map_fn.body)
            self._locals = saved_locals
        mapped_ct = map_type(mapped_type)

        # Apply map function then test predicate
        map_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        # Struct types need boxing (e.g. Prove_Option)
        if mapped_ct.decl.startswith("Prove_") and not mapped_ct.is_pointer:
            self._line(f"void *{mapped_var} = {map_code};")
        else:
            self._line(f"void *{mapped_var} = (void*)(intptr_t){map_code};")

        # Test predicate on mapped result — unbox if map produced a boxed struct
        mapped_is_boxed = mapped_ct.decl.startswith("Prove_") and not mapped_ct.is_pointer
        pred_code = self._emit_fused_lambda_inline(
            expr.args[2],
            mapped_var,
            mapped_type,
            boxed=mapped_is_boxed,
        )
        self._line(f"if ({pred_code}) {{")
        self._indent += 1

        # If map produced Option<T> and the filter removes None values,
        # unwrap the Option to push the inner T* into the result list.
        if (
            isinstance(mapped_type, GenericInstance)
            and mapped_type.base_name == "Option"
            and mapped_type.args
        ):
            self._needed_headers.add("prove_option.h")
            wrap = f"(void*)prove_option_unwrap({self._hof_unbox(mapped_var, mapped_ct)})"
        else:
            wrap = f"{mapped_var}"
        self._line(f"prove_list_push({result_tmp}, {wrap});")

        self._indent -= 1
        self._line("}")
        self._indent -= 1
        self._line("}")
        return result_tmp

    def _emit_fused_map_map(self, expr: CallExpr) -> str:
        """Emit map(map(list, f), g) as a single-pass loop.

        Args: [list, f, g]
        Fuses two maps into one loop: iterate, apply f then g.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        result_tmp = self._tmp()
        idx = self._named_tmp("i")
        elem_var = self._tmp()

        self._line(f"Prove_List *{result_tmp} = prove_list_new(8);")
        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        unwrap = f"({elem_ct.decl})" if elem_ct.is_pointer else f"({elem_ct.decl})(intptr_t)"
        self._line(f"{elem_ct.decl} {elem_var} = {unwrap}{list_arg}->data[{idx}];")

        # Infer f's return type for correct intermediate boxing
        f_fn = expr.args[1]
        f_result_type = elem_type
        if isinstance(f_fn, LambdaExpr) and f_fn.params:
            saved_locals = dict(self._locals)
            self._locals[f_fn.params[0]] = elem_type
            f_result_type = self._infer_expr_type(f_fn.body)
            self._locals = saved_locals
        f_result_ct = map_type(f_result_type)

        # Apply f then g
        f_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        mid_var = self._tmp()
        if f_result_ct.decl.startswith("Prove_") and not f_result_ct.is_pointer:
            self._line(f"void *{mid_var} = {f_code};")
        else:
            self._line(f"void *{mid_var} = (void*)(intptr_t){f_code};")

        # Infer g's return type for final boxing
        g_fn = expr.args[2]
        g_result_type = f_result_type
        if isinstance(g_fn, LambdaExpr) and g_fn.params:
            saved_locals2 = dict(self._locals)
            self._locals[g_fn.params[0]] = f_result_type
            g_result_type = self._infer_expr_type(g_fn.body)
            self._locals = saved_locals2
        g_result_ct = map_type(g_result_type)

        # Apply g to f's result — unbox if f produced a boxed struct
        f_is_boxed = f_result_ct.decl.startswith("Prove_") and not f_result_ct.is_pointer
        g_code = self._emit_fused_lambda_inline(
            expr.args[2],
            mid_var,
            f_result_type,
            boxed=f_is_boxed,
        )
        wrap = self._hof_box(str(g_code), g_result_ct)
        self._line(f"prove_list_push({result_tmp}, {wrap});")

        self._indent -= 1
        self._line("}")
        return result_tmp

    def _emit_fused_filter_filter(self, expr: CallExpr) -> str:
        """Emit filter(filter(list, p1), p2) as a single-pass loop.

        Args: [list, p1, p2]
        Fuses two filters into one loop: keep elements passing both predicates.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        result_tmp = self._tmp()
        idx = self._named_tmp("i")
        elem_var = self._tmp()

        self._line(f"Prove_List *{result_tmp} = prove_list_new(8);")
        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        unwrap = f"({elem_ct.decl})" if elem_ct.is_pointer else f"({elem_ct.decl})(intptr_t)"
        self._line(f"{elem_ct.decl} {elem_var} = {unwrap}{list_arg}->data[{idx}];")

        p1_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        p2_code = self._emit_fused_lambda_inline(expr.args[2], elem_var, elem_type)
        self._line(f"if (({p1_code}) && ({p2_code})) {{")
        self._indent += 1

        wrap = f"(void*){elem_var}" if elem_ct.is_pointer else f"(void*)(intptr_t){elem_var}"
        self._line(f"prove_list_push({result_tmp}, {wrap});")

        self._indent -= 1
        self._line("}")
        self._indent -= 1
        self._line("}")
        return result_tmp

    def _emit_fused_reduce_map(self, expr: CallExpr) -> str:
        """Emit reduce(map(list, f), init, g) as a single-pass loop.

        Args: [list, f, init, g]
        Fuses map+reduce into one loop: apply f to each element, accumulate with g.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        accum_type = self._infer_expr_type(expr.args[2])
        accum_ct = map_type(accum_type)

        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[2])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        # Hoist string literals from both lambdas before the loop
        lits: set[str] = set()
        for arg in (expr.args[1], expr.args[3]):
            if isinstance(arg, LambdaExpr):
                lits |= self._collect_string_literals(arg.body)
        self._hoist_string_literals(lits)

        idx = self._named_tmp("i")
        elem_var = self._tmp()
        mapped_var = self._tmp()

        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        saved_hof = self._in_hof_inline
        self._in_hof_inline = True

        elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
        self._line(f"{elem_ct.decl} {elem_var} = {elem_get};")

        map_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        self._line(f"void *{mapped_var} = (void*)(intptr_t){map_code};")

        # Accumulate: accum = g(accum, mapped)
        g_expr = expr.args[3]
        if isinstance(g_expr, LambdaExpr) and len(g_expr.params) == 2:
            saved = dict(self._locals)
            self._locals[g_expr.params[0]] = accum_type
            self._locals[g_expr.params[1]] = elem_type
            self._line(f"{accum_ct.decl} {g_expr.params[0]} = {accum_tmp};")
            mapped_cast = self._hof_unbox(mapped_var, elem_ct)
            self._line(f"{elem_ct.decl} {g_expr.params[1]} = {mapped_cast};")
            body_code = self._emit_expr(g_expr.body)
            self._locals = saved
            self._line(f"{accum_tmp} = {body_code};")
        else:
            g_code = self._emit_expr(g_expr)
            acc_cast = self._hof_box(accum_tmp, accum_ct)
            result_void = self._tmp()
            self._line(
                f"void *{result_void} = prove_list_reduce_step({g_code}, {acc_cast}, {mapped_var});"
            )
            self._line(f"{accum_tmp} = {self._hof_unbox(result_void, accum_ct)};")

        self._in_hof_inline = saved_hof
        self._indent -= 1
        self._line("}")
        return accum_tmp

    def _emit_fused_reduce_filter(self, expr: CallExpr) -> str:
        """Emit reduce(filter(list, p), init, g) as a single-pass loop.

        Args: [list, p, init, g]
        Fuses filter+reduce into one loop: test predicate, if passes accumulate with g.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        accum_type = self._infer_expr_type(expr.args[2])
        accum_ct = map_type(accum_type)

        accum_tmp = self._tmp()
        accum_val = self._emit_expr(expr.args[2])
        self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        # Hoist string literals from both lambdas before the loop
        lits: set[str] = set()
        for arg in (expr.args[1], expr.args[3]):
            if isinstance(arg, LambdaExpr):
                lits |= self._collect_string_literals(arg.body)
        self._hoist_string_literals(lits)

        idx = self._named_tmp("i")
        elem_var = self._tmp()

        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        saved_hof = self._in_hof_inline
        self._in_hof_inline = True

        elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
        self._line(f"{elem_ct.decl} {elem_var} = {elem_get};")

        pred_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        self._line(f"if ({pred_code}) {{")
        self._indent += 1

        g_expr = expr.args[3]
        if isinstance(g_expr, LambdaExpr) and len(g_expr.params) == 2:
            saved = dict(self._locals)
            self._locals[g_expr.params[0]] = accum_type
            self._locals[g_expr.params[1]] = elem_type
            self._line(f"{accum_ct.decl} {g_expr.params[0]} = {accum_tmp};")
            self._line(f"{elem_ct.decl} {g_expr.params[1]} = {elem_var};")
            body_code = self._emit_expr(g_expr.body)
            self._locals = saved
            self._line(f"{accum_tmp} = {body_code};")
        else:
            g_code = self._emit_expr(g_expr)
            acc_cast = self._hof_box(accum_tmp, accum_ct)
            elem_cast = self._hof_box(elem_var, elem_ct)
            result_void = self._tmp()
            self._line(
                f"void *{result_void} = prove_list_reduce_step({g_code}, {acc_cast}, {elem_cast});"
            )
            self._line(f"{accum_tmp} = {self._hof_unbox(result_void, accum_ct)};")

        self._in_hof_inline = saved_hof
        self._indent -= 1
        self._line("}")
        self._indent -= 1
        self._line("}")
        return accum_tmp

    def _emit_fused_multi_reduce(self, expr: CallExpr) -> str:
        """Emit multiple reduce() calls on the same list as one fused loop.

        Args layout: [list, StringLit(name1), init1, lambda1, StringLit(name2), init2, lambda2, ...]
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        # Parse triples: (name, init, lambda)
        triples: list[tuple[str, Expr, LambdaExpr]] = []
        i = 1
        while i + 2 < len(expr.args):
            name_lit = expr.args[i]
            init_expr = expr.args[i + 1]
            lam_expr = expr.args[i + 2]
            name = name_lit.value if isinstance(name_lit, StringLit) else f"_fused_{i}"
            if isinstance(lam_expr, LambdaExpr):
                triples.append((name, init_expr, lam_expr))
            i += 3

        # Emit typed accumulators (prefixed to avoid shadowing lambda params)
        accum_tmps: list[str] = []
        accum_cts = []
        for name, init_expr, _lam in triples:
            accum_type = self._infer_expr_type(init_expr)
            accum_ct = map_type(accum_type)
            accum_cts.append(accum_ct)
            accum_tmp = self._named_tmp(f"_acc_{name}")
            accum_tmps.append(accum_tmp)
            accum_val = self._emit_expr(init_expr)
            self._line(f"{accum_ct.decl} {accum_tmp} = {accum_val};")

        # Hoist string literals from all lambda bodies
        all_lits: set[str] = set()
        for _name, _init, lam in triples:
            all_lits |= self._collect_string_literals(lam.body)
        self._hoist_string_literals(all_lits)

        # Single fused loop
        self._line("")
        idx = self._named_tmp("i")
        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        saved_hof = self._in_hof_inline
        self._in_hof_inline = True

        # Shared element variable
        elem_get = self._hof_unbox(f"{list_arg}->data[{idx}]", elem_ct)
        elem_var = self._tmp()
        self._line(f"{elem_ct.decl} {elem_var} = {elem_get};")

        # CSE: detect shared object(elem_param) calls across lambda bodies
        shared_obj = self._detect_shared_object_call(triples)
        obj_cache_var: str | None = None
        if shared_obj:
            obj_cache_var = self._tmp()
            self._line(f"Prove_Table* {obj_cache_var} = prove_value_as_object({elem_var});")

        # Inline each lambda body in its own block to isolate param names
        for k, (_name, _init, lam) in enumerate(triples):
            accum_type = self._infer_expr_type(_init)
            self._line("{")
            self._indent += 1
            saved = dict(self._locals)
            self._locals[lam.params[0]] = accum_type
            self._locals[lam.params[1]] = elem_type
            self._line(f"{accum_cts[k].decl} {lam.params[0]} = {accum_tmps[k]};")
            self._line(f"{elem_ct.decl} {lam.params[1]} = {elem_var};")
            # Set up CSE substitution for object(elem_param)
            saved_obj_cache = getattr(self, "_fused_object_cache", None)
            if obj_cache_var and len(lam.params) >= 2:
                self._fused_object_cache = (lam.params[1], obj_cache_var)
            body_code = self._emit_expr(lam.body)
            self._fused_object_cache = saved_obj_cache  # type: ignore[assignment]
            self._locals = saved
            self._line(f"{accum_tmps[k]} = {body_code};")
            self._indent -= 1
            self._line("}")

        self._in_hof_inline = saved_hof
        self._indent -= 1
        self._line("}")

        # Store results for __fused_multi_reduce_ref lookups
        self._fused_reduce_results = accum_tmps

        # Return the first accumulator (for the first VarDecl)
        return accum_tmps[0]

    def _emit_fused_multi_reduce_ref(self, expr: CallExpr) -> str:
        """Return a previously-computed accumulator from a fused multi-reduce."""
        if expr.args and isinstance(expr.args[0], IntegerLit):
            idx_str = expr.args[0].value
            try:
                idx = int(idx_str)
            except ValueError:
                return "0 /* fused reduce ref error */"
            if idx < len(self._fused_reduce_results):
                return self._fused_reduce_results[idx]
        return "0 /* fused reduce ref error */"

    @staticmethod
    def _detect_shared_object_call(
        triples: list[tuple[str, "Expr", "LambdaExpr"]],
    ) -> bool:
        """Check if >=2 lambda bodies contain object(elem_param) calls."""
        count = 0
        for _name, _init, lam in triples:
            if len(lam.params) < 2:
                continue
            elem_param = lam.params[1]
            if _has_object_call(lam.body, elem_param):
                count += 1
        return count >= 2

    def _emit_fused_each_map(self, expr: CallExpr) -> str:
        """Emit each(map(list, f), g) as a single-pass loop.

        Args: [list, f, g]
        Fuses map+each into one loop: apply f then pass result to side-effect g.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        idx = self._named_tmp("i")
        elem_var = self._tmp()
        mapped_var = self._tmp()

        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        unwrap = f"({elem_ct.decl})" if elem_ct.is_pointer else f"({elem_ct.decl})(intptr_t)"
        self._line(f"{elem_ct.decl} {elem_var} = {unwrap}{list_arg}->data[{idx}];")

        map_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        self._line(f"void *{mapped_var} = (void*)(intptr_t){map_code};")

        consumer_code = self._emit_fused_lambda_inline(expr.args[2], mapped_var, elem_type)
        self._line(f"(void){consumer_code};")

        self._indent -= 1
        self._line("}")
        return "((void*)0)"

    def _emit_fused_each_filter(self, expr: CallExpr) -> str:
        """Emit each(filter(list, p), g) as a single-pass loop.

        Args: [list, p, g]
        Fuses filter+each into one loop: test predicate, if passes run side-effect g.
        """
        self._needed_headers.add("prove_list.h")
        list_arg, list_type = self._cache_list_arg(expr.args[0])

        elem_type = INTEGER
        if isinstance(list_type, ListType):
            elem_type = list_type.element  # type: ignore[assignment]
        elem_ct = map_type(elem_type)

        idx = self._named_tmp("i")
        elem_var = self._tmp()

        self._line(f"for (int64_t {idx} = 0; {idx} < {list_arg}->length; {idx}++) {{")
        self._indent += 1

        unwrap = f"({elem_ct.decl})" if elem_ct.is_pointer else f"({elem_ct.decl})(intptr_t)"
        self._line(f"{elem_ct.decl} {elem_var} = {unwrap}{list_arg}->data[{idx}];")

        pred_code = self._emit_fused_lambda_inline(expr.args[1], elem_var, elem_type)
        self._line(f"if ({pred_code}) {{")
        self._indent += 1

        consumer_code = self._emit_fused_lambda_inline(expr.args[2], elem_var, elem_type)
        self._line(f"(void){consumer_code};")

        self._indent -= 1
        self._line("}")
        self._indent -= 1
        self._line("}")
        return "((void*)0)"

    def _cache_list_arg(self, expr: Expr) -> tuple[str, "Type"]:
        """Emit a list expression into a temp variable before loop use.

        Prevents re-evaluation of function calls (e.g. range()) on every loop
        iteration when list_arg is referenced in both the loop condition and body.
        If the expression is an ArrayType, convert to list for compatibility
        with list-based iteration (used by fused emitters).
        """
        list_type = self._infer_expr_type(expr)
        # Skip alias when expression is already a simple variable
        if isinstance(expr, IdentifierExpr) and expr.name in self._locals:
            if not isinstance(list_type, ArrayType):
                return expr.name, list_type
        list_code = self._emit_expr(expr)
        tmp = self._tmp()
        if isinstance(list_type, ArrayType):
            self._needed_headers.add("prove_array.h")
            arr_tmp = self._tmp()
            self._line(f"Prove_Array *{arr_tmp} = {list_code};")
            self._line(f"Prove_List *{tmp} = prove_array_to_list({arr_tmp});")
            return tmp, ListType(list_type.element)
        self._line(f"Prove_List *{tmp} = {list_code};")
        return tmp, list_type

    def _emit_fused_lambda_inline(
        self,
        expr: Expr,
        arg_var: str,
        elem_type: Type,
        *,
        boxed: bool = False,
    ) -> str:
        """Inline a lambda or function reference for fused iteration.

        When *boxed* is True, arg_var is a ``void*`` holding a heap-boxed
        struct and must be unboxed before use.
        """
        if isinstance(expr, LambdaExpr) and expr.params:
            old_param = expr.params[0]
            body = expr.body
            # Identity: lambda just returns its param — return the arg directly
            if isinstance(body, IdentifierExpr) and body.name == old_param:
                return arg_var
            # General case: wrap in a C block to isolate the param declaration.
            # This prevents redefinition errors when multiple lambdas share the
            # same param name (e.g. both use |n|) in the same enclosing scope.
            saved = dict(self._locals)
            self._locals[old_param] = elem_type
            elem_ct = map_type(elem_type)
            # Infer the body's return type for correct boxing
            body_type = self._infer_expr_type(body)
            body_ct = map_type(body_type)
            # Struct types (Prove_Option, etc.) need void* boxing, not int64_t
            needs_box = body_ct.decl.startswith("Prove_") and not body_ct.is_pointer
            result_tmp = self._tmp()
            if needs_box:
                self._line(f"void *{result_tmp} = NULL;")
            else:
                self._line(f"int64_t {result_tmp} = 0;")
            self._line("{")
            self._indent += 1
            if boxed:
                self._line(f"{elem_ct.decl} {old_param} = {self._hof_unbox(arg_var, elem_ct)};")
            else:
                self._line(f"{elem_ct.decl} {old_param} = {arg_var};")
            body_code = self._emit_expr(body)
            if needs_box:
                self._line(f"{result_tmp} = {self._hof_box(body_code, body_ct)};")
            else:
                self._line(f"{result_tmp} = (int64_t)(intptr_t)({body_code});")
            self._indent -= 1
            self._line("}")
            self._locals = saved
            return result_tmp
        if isinstance(expr, IdentifierExpr):
            # Named function reference
            fn_sig = self._symbols.resolve_function_any(expr.name, arity=1)
            if fn_sig:
                c_name = mangle_name(
                    fn_sig.verb,
                    expr.name,
                    list(fn_sig.param_types) if fn_sig.param_types else None,
                    module=self._sig_module(fn_sig),
                )
                return f"{c_name}({arg_var})"
        # Fallback: emit as regular call
        return f"(({self._emit_expr(expr)})((void*)(intptr_t){arg_var}))"

    def _emit_store_row_construction(self, type_name: str, expr: CallExpr, args: list[str]) -> str:
        """Emit store-backed row construction: Color(Red, "red", 0xFF0000).

        Emits variant name + column values array as C locals.
        The VarDecl name is used as the prefix for _variant and _vals.
        """
        from prove.ast_nodes import LookupTypeDef

        lookup = self._lookup_tables.get(type_name)
        if lookup is None or not isinstance(lookup, LookupTypeDef):
            return f"/* unknown store row type {type_name} */ 0"

        n_cols = len(lookup.value_types)
        row_tmp = self._tmp()

        # First arg is variant name (TypeIdentifierExpr) — emit as string
        variant_arg = expr.args[0]
        if hasattr(variant_arg, "name"):
            variant_str = variant_arg.name
        else:
            variant_str = str(args[0])
        escaped_variant = self._escape_c_string(variant_str)
        self._line(
            f'Prove_String *{row_tmp}_variant = prove_string_from_cstr("{escaped_variant}");'
        )

        # Column values — all stored as Prove_String* in StoreTable
        self._line(f"Prove_String *{row_tmp}_vals[{n_cols}];")
        for i in range(n_cols):
            arg_expr = expr.args[i + 1]  # skip variant arg
            col_type_name = ""
            if i < len(lookup.value_types):
                vt = lookup.value_types[i]
                col_type_name = vt.name if hasattr(vt, "name") else ""

            if isinstance(arg_expr, StringLit):
                escaped = self._escape_c_string(arg_expr.value)
                self._line(f'{row_tmp}_vals[{i}] = prove_string_from_cstr("{escaped}");')
            elif isinstance(arg_expr, IntegerLit):
                # Convert integer to string for storage
                self._line(f"{row_tmp}_vals[{i}] = prove_string_from_int({arg_expr.value}L);")
            else:
                # Generic: emit as-is, convert to string if needed
                c_val = args[i + 1]
                if col_type_name == "Integer":
                    self._line(f"{row_tmp}_vals[{i}] = prove_string_from_int({c_val});")
                else:
                    self._line(f"{row_tmp}_vals[{i}] = {c_val};")

        # Track this temp as a store row for add() to find
        if not hasattr(self, "_store_rows"):
            self._store_rows = {}
        self._store_rows[row_tmp] = (f"{row_tmp}_variant", f"{row_tmp}_vals")
        return row_tmp
