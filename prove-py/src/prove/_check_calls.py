"""Call inference mixin for Checker."""

from __future__ import annotations

from prove.ast_nodes import (
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    ListLiteral,
    PipeExpr,
    SimpleType,
    TypeIdentifierExpr,
)
from prove.errors import Diagnostic, DiagnosticLabel, Severity
from prove.source import Span
from prove.types import (
    ATTACHED,
    ERROR_TY,
    AlgebraicType,
    ArrayType,
    BorrowType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    StructType,
    Type,
    TypeVariable,
    has_mutable_modifier,
    has_own_modifier,
    is_json_serializable,
    resolve_type_vars,
    substitute_type_vars,
    type_name,
    types_compatible,
)

# Verbs considered pure (no IO side effects allowed)
_PURE_VERBS = frozenset({"transforms", "validates", "reads", "creates", "matches"})


class CallCheckMixin:
    _in_listens_worker_list: bool
    _inside_async_call: bool

    def _infer_call(self, expr: CallExpr, expected_type: Type | None = None) -> Type:
        # Early intercept: store-backed row construction Color(Red, "red", 0xFF0000)
        # Must happen before arg inference since the variant name (Red) is not resolvable.
        if isinstance(expr.func, TypeIdentifierExpr):
            func_name = expr.func.name
            if func_name in self._store_lookup_types:
                return self._infer_store_row_construction(expr, func_name)

        # Check for own/borrow overlap in arguments (W360)
        self._check_own_borrow_overlap(expr)

        # Pre-check: if calling a listens verb with a list literal first arg,
        # set flag so attached calls inside the list suppress E372
        _was_in_listens = self._in_listens_worker_list
        if (
            isinstance(expr.func, IdentifierExpr)
            and expr.args
            and isinstance(expr.args[0], ListLiteral)
        ):
            peek_sig = self.symbols.resolve_function_any(expr.func.name)
            if peek_sig and peek_sig.verb in ("listens", "renders"):
                self._in_listens_worker_list = True

        # Determine function name and resolve
        arg_types = [self._infer_expr(a) for a in expr.args]
        self._in_listens_worker_list = _was_in_listens
        arg_count = len(expr.args)

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
            # Try specific resolution first
            sig = self.symbols.resolve_function(None, name, arg_count)
            # Also try with verb from current function context
            if (
                sig is None
                and self._current_function
                and isinstance(self._current_function, FunctionDef)
            ):
                sig = self.symbols.resolve_function(
                    self._current_function.verb,
                    name,
                    arg_count,
                )

            # If not found or types don't match, or if multiple overloads might exist, try any
            if (
                sig is None
                or len(sig.param_types) != arg_count
                or not all(types_compatible(p, a) for p, a in zip(sig.param_types, arg_types))
                or expected_type is not None  # ALWAYS check any if we have an expected return type
            ):
                any_sig = self.symbols.resolve_function_any(
                    name, arg_types, expected_return=expected_type
                )
                if any_sig is not None:
                    sig = any_sig

            if sig is None:
                # Check if it's a known symbol (might be a variable holding a function)
                sym = self.symbols.lookup(name)
                if sym is not None:
                    sym.used = True
                    if isinstance(sym.resolved_type, FunctionType):
                        return sym.resolved_type.return_type
                    return ERROR_TY
                self._error("E311", f"undefined function '{name}'", expr.span)
                return ERROR_TY

            # Mark import as used for unqualified calls to imported functions
            if sig.module:
                self._used_imports.add((sig.module, name))

            # Check calls to async functions without &
            if sig.verb in ("detached", "attached", "listens", "renders"):
                if self._in_listens_worker_list and sig.verb == "attached":
                    # Attached calls inside listens worker list are worker
                    # registrations, not coroutine invocations — no & needed.
                    # Do NOT consume _inside_async_call (it belongs to the
                    # outer listens call wrapped in &).
                    return ATTACHED
                elif self._inside_async_call:
                    # Consumed: only applies to the direct callee, not args
                    self._inside_async_call = False
                else:
                    if sig.verb == "detached":
                        self._info(
                            "I378",
                            f"`detached` function '{name}' called without `&`; "
                            f"`prove format` will add it",
                            expr.span,
                        )
                    else:
                        self._error(
                            "E372",
                            f"async function '{name}' must be called with `&`",
                            expr.span,
                        )

            # Track verb-aware recursion
            if (
                self._current_function
                and isinstance(self._current_function, FunctionDef)
                and sig.name == self._current_function.name
                and sig.verb == self._current_function.verb
            ):
                self._is_recursive = True

            # Verb-aware purity check for channel dispatch: if the
            # resolved overload is IO but the caller is pure, emit E363.
            if (
                self._current_function
                and isinstance(self._current_function, FunctionDef)
                and self._current_function.verb in _PURE_VERBS
                and sig.verb in ("inputs", "outputs")
            ):
                self._error(
                    "E363",
                    f"pure function cannot call IO function '{name}'",
                    expr.span,
                )

            # Purity enforcement for par_map / par_filter / par_reduce:
            # the callback must be a named function with a pure verb.
            if name in ("par_map", "par_filter", "par_reduce"):
                # par_reduce: callback is 3rd arg (idx 2); others: 2nd arg (idx 1)
                cb_idx = 2 if name == "par_reduce" else 1
                if cb_idx < len(expr.args):
                    cb_arg = expr.args[cb_idx]
                    if isinstance(cb_arg, IdentifierExpr):
                        cb_arity = 2 if name == "par_reduce" else 1
                        cb_sig = self.symbols.resolve_function_any(cb_arg.name, arity=cb_arity)
                        if cb_sig and cb_sig.verb and cb_sig.verb not in _PURE_VERBS:
                            self._error(
                                "E368",
                                f"'{name}' requires a pure callback, but "
                                f"'{cb_arg.name}' has verb '{cb_sig.verb}'",
                                cb_arg.span,
                            )

            # par_each: IO callbacks are allowed; only reject async verbs.
            if name == "par_each":
                cb_idx = 1
                if cb_idx < len(expr.args):
                    cb_arg = expr.args[cb_idx]
                    if isinstance(cb_arg, IdentifierExpr):
                        cb_sig = self.symbols.resolve_function_any(cb_arg.name, arity=1)
                        if (
                            cb_sig
                            and cb_sig.verb
                            and cb_sig.verb in ("detached", "attached", "listens", "renders")
                        ):
                            self._error(
                                "E369",
                                f"'par_each' callback cannot be an async verb "
                                f"('{cb_sig.verb}'); use 'each' for sequential "
                                "iteration or restructure with 'attached'",
                                cb_arg.span,
                            )

            # Skip strict checks for imported functions (ErrorType return = unknown sig)
            if isinstance(sig.return_type, ErrorType):
                return sig.return_type

            # Check argument count
            if len(sig.param_types) != arg_count:
                expected_n = len(sig.param_types)
                sig_str = ", ".join(
                    f"{n}: {type_name(t)}" for n, t in zip(sig.param_names, sig.param_types)
                )
                diag = Diagnostic(
                    severity=Severity.ERROR,
                    code="E330",
                    message=(f"wrong number of arguments: expected {expected_n}, got {arg_count}"),
                    labels=[DiagnosticLabel(span=expr.span, message="")],
                    notes=[f"function signature: {name}({sig_str})"],
                )
                self.diagnostics.append(diag)
                return sig.return_type

            # Check argument types
            sig_str = ", ".join(
                f"{n} {type_name(t)}" for n, t in zip(sig.param_names, sig.param_types)
            )
            for i, (expected, actual) in enumerate(zip(sig.param_types, arg_types)):
                # TypeVariable("Value") in stdlib sigs acts as a dynamic type,
                # but only json-serializable types should silently coerce.
                # Non-serializable types (e.g. Time, Date) need an explicit
                # overload; passing them to a Value param is a type error.
                if (
                    isinstance(expected, TypeVariable)
                    and expected.name == "Value"
                    and not isinstance(actual, (ErrorType, TypeVariable))
                    and not is_json_serializable(actual)
                ):
                    param_name = sig.param_names[i] if i < len(sig.param_names) else str(i + 1)
                    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(i + 1, f"{i + 1}th")
                    arg_span = expr.args[i].span if i < len(expr.args) else expr.span
                    self._error(
                        "E335",
                        f"{ordinal} argument '{param_name}': "
                        f"type '{type_name(actual)}' cannot be used as Value",
                        arg_span,
                    )
                    continue
                if not types_compatible(expected, actual):
                    extra = self._builtin_extra_types.get((name, i))
                    if extra and any(types_compatible(e, actual) for e in extra):
                        continue
                    # Option<T> auto-unwraps where T is expected
                    if isinstance(actual, GenericInstance):
                        if actual.base_name == "Option" and actual.args:
                            inner = actual.args[0]
                            if types_compatible(expected, inner):
                                continue
                    if (
                        sig.module in ("parse", "types")
                        and sig.verb in ("creates", "validates")
                        and sig.name == "value"
                        and isinstance(expected, (SimpleType, PrimitiveType, TypeVariable))
                        and expected.name == "Source"
                        and is_json_serializable(actual)
                    ):
                        continue
                    param_name = sig.param_names[i] if i < len(sig.param_names) else str(i + 1)
                    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(i + 1, f"{i + 1}th")
                    arg_span = expr.args[i].span if i < len(expr.args) else expr.span
                    # E434: specific message for Struct field mismatch
                    if isinstance(expected, StructType) and isinstance(actual, RecordType):
                        missing = [f for f in expected.required_fields if f not in actual.fields]
                        wrong = [
                            f
                            for f in expected.required_fields
                            if f in actual.fields
                            and not types_compatible(expected.required_fields[f], actual.fields[f])
                        ]
                        parts = []
                        if missing:
                            parts.append(f"missing fields: {', '.join(missing)}")
                        if wrong:
                            parts.append(f"incompatible fields: {', '.join(wrong)}")
                        detail = "; ".join(parts) if parts else "type mismatch"
                        diag = Diagnostic(
                            severity=Severity.ERROR,
                            code="E434",
                            message=(
                                f"{ordinal} argument '{param_name}': "
                                f"record '{type_name(actual)}' does not satisfy "
                                f"Struct constraints ({detail})"
                            ),
                            labels=[
                                DiagnosticLabel(
                                    span=arg_span,
                                    message=f"expected '{type_name(expected)}'",
                                )
                            ],
                            notes=[f"function signature: {name}({sig_str})"],
                        )
                    else:
                        diag = Diagnostic(
                            severity=Severity.ERROR,
                            code="E331",
                            message=(
                                f"{ordinal} argument '{param_name}': "
                                f"expected '{type_name(expected)}', "
                                f"got '{type_name(actual)}'"
                            ),
                            labels=[
                                DiagnosticLabel(
                                    span=arg_span,
                                    message=f"expected '{type_name(expected)}'",
                                )
                            ],
                            notes=[f"function signature: {name}({sig_str})"],
                        )
                    self.diagnostics.append(diag)

            # Ownership tracking: mark variables as moved if passed to Own parameters
            self._track_moved_args(expr.args, sig.param_types)

            # E403/E404: validate registered workers for listens/renders call
            if sig.verb in ("listens", "renders") and expr.args:
                first_arg = expr.args[0]
                if isinstance(first_arg, ListLiteral):
                    for elem in first_arg.elements:
                        # Resolve the function name from bare ref or call
                        if isinstance(elem, IdentifierExpr):
                            elem_name = elem.name
                        elif isinstance(elem, CallExpr) and isinstance(elem.func, IdentifierExpr):
                            elem_name = elem.func.name
                        else:
                            continue
                        elem_sig = self.symbols.resolve_function_any(elem_name)
                        if elem_sig is None:
                            continue  # E311 will catch undefined
                        # renders registers listens verbs; listens registers attached verbs
                        expected_verb = "listens" if sig.verb == "renders" else "attached"
                        if elem_sig.verb != expected_verb:
                            self._error(
                                "E403",
                                f"registered function '{elem_name}' "
                                f"is not a `{expected_verb}` verb",
                                elem.span,
                            )
                        elif sig.event_type is not None and isinstance(
                            sig.event_type, AlgebraicType
                        ):
                            # E404: return type must match event_type or one of its variants
                            variant_names = {v.name for v in sig.event_type.variants}
                            ret_name = type_name(elem_sig.return_type)
                            if ret_name not in variant_names and ret_name != type_name(
                                sig.event_type
                            ):  # noqa: E501
                                self._error(
                                    "E404",
                                    f"return type of '{elem_name}' does not match "
                                    f"a variant of event type '{type_name(sig.event_type)}'",
                                    elem.span,
                                )

            # Verb-gated serialization: creates/validates value(V)
            # requires the argument to be json-serializable.
            if (
                sig.module
                and sig.module in ("parse", "types")
                and sig.verb in ("creates", "validates")
                and sig.name == "value"
                and arg_types
            ):
                actual_arg = arg_types[0]
                if not is_json_serializable(actual_arg):
                    self._error(
                        "E320",
                        f"type '{type_name(actual_arg)}' is not serializable to Value",
                        expr.span,
                    )

            ret = sig.return_type
            # Failable functions return Result<T, Error> at call site
            if sig.can_fail and not (
                isinstance(ret, GenericInstance) and ret.base_name == "Result"
            ):
                ret = GenericInstance("Result", [ret, PrimitiveType("Error")])
            # Resolve generic type variables in return type
            if sig.module and arg_types:
                bindings = resolve_type_vars(
                    sig.param_types,
                    arg_types,
                )
                if bindings:
                    ret = substitute_type_vars(ret, bindings)
            # Requires-based narrowing for unqualified calls:
            # Option<Value> → Value, Result<Value, Error> → Value
            if (
                isinstance(ret, GenericInstance)
                and ret.base_name in ("Option", "Result")
                and ret.args
                and self._requires_narrowings
                and sig.module
            ):
                if self._has_requires_narrowing(
                    sig.module,
                    expr.args,
                ):
                    return ret.args[0]
            return ret

        if isinstance(expr.func, TypeIdentifierExpr):
            # Type constructor call — try as function first (variant constructors)
            name = expr.func.name

            sig = self.symbols.resolve_function(None, name, arg_count)
            if sig is None:
                sig = self.symbols.resolve_function_any(name, arg_types)
            if sig is not None:
                if not isinstance(sig.return_type, ErrorType):
                    if len(sig.param_types) != arg_count:
                        expected_n = len(sig.param_types)
                        self._error(
                            "E330",
                            f"wrong number of arguments: expected {expected_n}, got {arg_count}",
                            expr.span,
                        )
                return sig.return_type
            # Fall back to type lookup (record constructor)
            resolved = self.symbols.resolve_type(name)
            if resolved is not None:
                self._used_types.add(name)
                # Type-check constructor arguments against record fields
                if isinstance(resolved, RecordType) and resolved.fields:
                    field_names = list(resolved.fields.keys())
                    expected_n = len(field_names)
                    # Single-arg deserialization: Record(structured_data)
                    # Lazily maps structured data fields to record fields.
                    # This can fail at runtime, so it produces a failable type.
                    if arg_count == 1:
                        actual = self._infer_expr(expr.args[0])
                        is_structured = (
                            isinstance(actual, PrimitiveType) and actual.name == "Value"
                        ) or (
                            isinstance(actual, GenericInstance)
                            and actual.base_name in ("Value", "Table", "Result")
                        )
                        if is_structured:
                            from prove.types import EffectType

                            return EffectType(resolved, frozenset({"Fail"}))
                    if arg_count != expected_n:
                        self._error(
                            "E330",
                            f"wrong number of arguments: expected {expected_n}, got {arg_count}",
                            expr.span,
                        )
                    else:
                        for i, fname in enumerate(field_names):
                            expected = resolved.fields[fname]
                            actual = (
                                self._infer_expr(expr.args[i]) if i < len(expr.args) else ERROR_TY
                            )
                            if not types_compatible(expected, actual):
                                self._error(
                                    "E321",
                                    f"type mismatch: field '{fname}' expects "
                                    f"'{type_name(expected)}', got '{type_name(actual)}'",
                                    expr.args[i].span if i < len(expr.args) else expr.span,
                                )
                return resolved
            self._error("E311", f"undefined function '{name}'", expr.span)
            return ERROR_TY

        # Namespaced call: Module.function(args)
        if isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, TypeIdentifierExpr):
            module_name = expr.func.obj.name
            func_name = expr.func.field
            # Verify the module is imported
            if not self._is_module_imported(module_name):
                from prove.stdlib_loader import is_stdlib_module

                known_modules = set(self._module_imports.keys())
                if self._local_modules:
                    known_modules.update(self._local_modules.keys())
                suggestion = self._fuzzy_match(module_name, known_modules)
                if is_stdlib_module(module_name) or (
                    self._local_modules and module_name in self._local_modules
                ):
                    msg = f"module `{module_name}` is not imported — add it to your module imports"
                elif suggestion:
                    msg = f"module `{module_name}` does not exist; did you mean `{suggestion}`?"
                else:
                    msg = f"module `{module_name}` does not exist"
                self._error("E313", msg, expr.func.obj.span)
                return ERROR_TY
            # Verify the function is explicitly imported from this module
            if not self._is_function_imported(module_name, func_name):
                self._error(
                    "E312",
                    f"function '{func_name}' not imported from module '{module_name}'",
                    expr.func.span,
                )
                return ERROR_TY
            # Mark import as used
            self._used_imports.add((module_name.lower(), func_name))
            # Resolve the function normally by name
            sig = self.symbols.resolve_function(None, func_name, arg_count)
            cur = self._current_function
            if sig is None and cur and isinstance(cur, FunctionDef):
                sig = self.symbols.resolve_function(
                    cur.verb,
                    func_name,
                    arg_count,
                )
            if sig is None:
                sig = self.symbols.resolve_function_any(
                    func_name, arg_types, expected_return=expected_type
                )
            if sig is None:
                self._error(
                    "E312",
                    f"undefined function '{func_name}' in module '{module_name}'",
                    expr.span,
                )
                return ERROR_TY
            ret = sig.return_type
            # Failable functions return Result<T, Error> at call site
            if sig.can_fail and not (
                isinstance(ret, GenericInstance) and ret.base_name == "Result"
            ):
                ret = GenericInstance("Result", [ret, PrimitiveType("Error")])
            # Resolve generic type variables in return type
            if arg_types:
                bindings = resolve_type_vars(
                    sig.param_types,
                    arg_types,
                )
                if bindings:
                    ret = substitute_type_vars(ret, bindings)
            # Requires-based narrowing: if the return type is Option<T>
            # or Result<T, E> and there is a matching validates call in
            # requires, narrow to T respectively.
            if (
                isinstance(ret, GenericInstance)
                and ret.base_name in ("Option", "Result")
                and ret.args
                and self._requires_narrowings
            ):
                if self._has_requires_narrowing(
                    module_name,
                    expr.args,
                ):
                    return ret.args[0]
            return ret

        # For complex expressions (e.g., method-like calls), infer the function type
        func_type = self._infer_expr(expr.func)
        if isinstance(func_type, FunctionType):
            return func_type.return_type
        return ERROR_TY

    def _infer_store_row_construction(self, expr: CallExpr, name: str) -> Type:
        """Type-check Color(Red, "red", 0xFF0000) for store-backed lookup types."""
        lookup = self._lookup_tables.get(name)
        arg_count = len(expr.args)
        if lookup and lookup.value_types:
            expected_n = len(lookup.value_types) + 1  # variant + columns
            if arg_count != expected_n:
                self._error(
                    "E330",
                    f"store-backed row constructor expects {expected_n} "
                    f"arguments (variant + {len(lookup.value_types)} columns), "
                    f"got {arg_count}",
                    expr.span,
                )
            # Skip first arg (variant name — a TypeIdentifierExpr, not resolvable);
            # infer remaining args (column values) to validate types.
            for a in expr.args[1:]:
                self._infer_expr(a)
        resolved = self.symbols.resolve_type(name)
        if resolved is not None:
            self._used_types.add(name)
            return resolved
        return ERROR_TY

    def _infer_field(self, expr: FieldExpr) -> Type:
        obj_type = self._infer_expr(expr.obj)

        if isinstance(obj_type, ErrorType):
            return ERROR_TY

        # Unwrap borrowed types to get inner type for field access
        if isinstance(obj_type, BorrowType):
            obj_type = obj_type.inner

        if isinstance(obj_type, PrimitiveType) and obj_type.modifiers:
            base = self.symbols.resolve_type(obj_type.name)
            if base is not None:
                obj_type = base

        if isinstance(obj_type, RecordType):
            field_type = obj_type.fields.get(expr.field)
            if field_type is None:
                self._error(
                    "E340",
                    f"no field '{expr.field}' on type '{type_name(obj_type)}'",
                    expr.span,
                )
                return ERROR_TY
            return field_type

        if isinstance(obj_type, StructType):
            field_type = obj_type.required_fields.get(expr.field)
            if field_type is None:
                self._error(
                    "E433",
                    f"field '{expr.field}' not declared in `with` constraints for Struct parameter",
                    expr.span,
                )
                return ERROR_TY
            return field_type

        if isinstance(obj_type, RefinementType) and isinstance(obj_type.base, RecordType):
            field_type = obj_type.base.fields.get(expr.field)
            if field_type is None:
                self._error(
                    "E340",
                    f"no field '{expr.field}' on type '{type_name(obj_type)}'",
                    expr.span,
                )
                return ERROR_TY
            return field_type

        # Table field access returns the value type
        if isinstance(obj_type, GenericInstance) and obj_type.base_name == "Table":
            if obj_type.args:
                inner = obj_type.args[0]
                # Concrete table access: resolve TypeVariable to PrimitiveType
                # so type checking catches mismatches (e.g. Value vs String)
                if isinstance(inner, TypeVariable):
                    return PrimitiveType(inner.name)
                return inner
            return ERROR_TY

        # Named column access on binary lookup: Prediction:Cat.probability
        from prove.ast_nodes import LookupAccessExpr, LookupTypeDef

        if isinstance(expr.obj, LookupAccessExpr):
            lookup = self._lookup_tables.get(expr.obj.type_name)
            if (
                lookup is not None
                and isinstance(lookup, LookupTypeDef)
                and lookup.is_binary
                and lookup.column_names
            ):
                field = expr.field
                for i, cname in enumerate(lookup.column_names):
                    if cname == field and i < len(lookup.value_types):
                        self._used_types.add(expr.obj.type_name)
                        return self._resolve_type_expr(lookup.value_types[i])
                self._error(
                    "E340",
                    f"no named column '{field}' on binary lookup '{expr.obj.type_name}'",
                    expr.span,
                )
                return ERROR_TY

        # Allow field access on GenericInstance, AlgebraicType, etc. without error
        # (duck typing / deferred check for generics)
        if isinstance(obj_type, (GenericInstance, TypeVariable, ListType, ArrayType)):
            return ERROR_TY

        self._error(
            "E340",
            f"no field '{expr.field}' on type '{type_name(obj_type)}'",
            expr.span,
        )
        return ERROR_TY

    def _infer_pipe(self, expr: PipeExpr) -> Type:
        """a |> f desugars to f(a)."""
        left_type = self._infer_expr(expr.left)

        # The right side should be a function name or call
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            sig = self.symbols.resolve_function(None, name, 1)
            # Type-based fallthrough: if first match has wrong param type,
            # try resolve_function_any with the piped arg type.
            if sig is None or (
                sig.param_types and not types_compatible(sig.param_types[0], left_type)
            ):
                any_sig = self.symbols.resolve_function_any(
                    name,
                    [left_type],
                )
                if any_sig is not None:
                    sig = any_sig
            if sig is None:
                self._error("E311", f"undefined function '{name}'", expr.right.span)
                return ERROR_TY
            return sig.return_type

        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            # a |> f(b, c) desugars to f(a, b, c)
            name = expr.right.func.name
            total_args = 1 + len(expr.right.args)
            extra_types = [self._infer_expr(a) for a in expr.right.args]
            all_types = [left_type] + extra_types
            sig = self.symbols.resolve_function(None, name, total_args)
            if sig is None or (
                sig.param_types and not types_compatible(sig.param_types[0], left_type)
            ):
                any_sig = self.symbols.resolve_function_any(
                    name,
                    all_types,
                )
                if any_sig is not None:
                    sig = any_sig
            if sig is None:
                self._error("E311", f"undefined function '{name}'", expr.right.span)
                return ERROR_TY
            return sig.return_type

        # Fallback: infer the right side
        right_type = self._infer_expr(expr.right)
        if isinstance(right_type, FunctionType):
            return right_type.return_type
        return ERROR_TY

    def _track_moved_args(self, args: list[Expr], param_types: list[Type]) -> None:
        """Mark arguments as moved if passed to parameters with Own modifier."""
        for arg, param_ty in zip(args, param_types):
            if has_own_modifier(param_ty):
                self._track_moved_expr(arg)
            # Check: can't pass a borrow to a mutable parameter
            if isinstance(arg, IdentifierExpr):
                sym = self.symbols.lookup(arg.name)
                if sym is not None and isinstance(sym.resolved_type, BorrowType):
                    if has_mutable_modifier(param_ty):
                        self._error(
                            "E341",
                            f"cannot pass borrowed value '{arg.name}' to mutable parameter",
                            arg.span,
                        )

    def _track_moved_expr(self, expr: Expr) -> None:
        """Mark variables as moved based on expression type.

        Handles complex expressions: nested calls (f(g(owned))),
        field access (x.inner), and pipe expressions (x |> f).
        """
        if isinstance(expr, IdentifierExpr):
            sym = self.symbols.lookup(expr.name)
            if sym is not None and has_own_modifier(sym.resolved_type):
                self._moved_vars.add(expr.name)
        elif isinstance(expr, FieldExpr):
            # Track field path for partial move: x.inner moves x.inner
            path = self._expr_to_field_path(expr)
            if path:
                self._moved_vars.add(path)
            # Also recurse into base for whole-object tracking
            self._track_moved_expr(expr.obj)
        elif isinstance(expr, CallExpr):
            # Nested calls: f(g(owned)) — owned is consumed by g
            for arg in expr.args:
                self._track_moved_expr(arg)
        elif isinstance(expr, PipeExpr):
            # x |> f — x is consumed
            self._track_moved_expr(expr.left)

    def _expr_to_field_path(self, expr: Expr) -> str | None:
        """Convert a FieldExpr chain to a dotted path string."""
        if isinstance(expr, IdentifierExpr):
            return expr.name
        if isinstance(expr, FieldExpr):
            base = self._expr_to_field_path(expr.obj)
            if base:
                return f"{base}.{expr.field}"
        return None

    def _check_own_borrow_overlap(self, expr: CallExpr) -> None:
        """W360: pointer field released by nested function call but also used elsewhere.

        Detects patterns like ``Constructor(x.field, func(x.field))`` where
        ``func`` owns (releases) ``x.field`` but the constructor also borrows
        it.  Because C evaluation order of arguments is unspecified, the
        release can happen before the borrow, causing use-after-free.
        """
        # Suppress inside lambda bodies — emitter adds retains automatically.
        if self._inside_lambda:
            return

        # Step 1: collect field paths that are args to IdentifierExpr calls
        # (these are "owned" — the callee will prove_release them).
        owned: set[str] = set()

        def _collect_owned(node: Expr) -> None:
            if isinstance(node, CallExpr) and isinstance(node.func, IdentifierExpr):
                for a in node.args:
                    p = self._expr_to_field_path(a)
                    if p and "." in p:
                        owned.add(p)
            if isinstance(node, CallExpr):
                for a in node.args:
                    _collect_owned(a)

        for arg in expr.args:
            _collect_owned(arg)

        if not owned:
            return

        # Step 2: count how many times each owned path appears in the
        # full argument list (including inside nested calls).
        counts: dict[str, int] = {p: 0 for p in owned}

        def _count(node: Expr) -> None:
            if isinstance(node, FieldExpr):
                p = self._expr_to_field_path(node)
                if p in counts:
                    counts[p] += 1
                return  # full path counted — don't recurse into sub-parts
            if isinstance(node, CallExpr):
                for a in node.args:
                    _count(a)

        for arg in expr.args:
            _count(arg)

        for path, n in counts.items():
            if n > 1:
                self._warning(
                    "W360",
                    f"'{path}' is released by function call but also used "
                    f"elsewhere in this expression; "
                    f"bind the function call to a variable first",
                    expr.span,
                )

    def _check_moved_var(self, name: str, span: Span) -> None:
        """Check if a variable has been moved and report error if so.

        Also checks for partial moves: if x.inner was moved,
        accessing x reports use-after-move.
        """
        if name in self._moved_vars:
            self._error(
                "E340",
                f"use of moved value '{name}'",
                span,
            )
            return
        # Check if any field of this variable was moved (partial move)
        prefix = f"{name}."
        for moved in self._moved_vars:
            if moved.startswith(prefix):
                self._error(
                    "E340",
                    f"use of partially moved value '{name}' (field '{moved}' was moved)",
                    span,
                )
                return
