"""Call inference mixin for Checker."""

from __future__ import annotations

from prove.ast_nodes import (
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    PipeExpr,
    SimpleType,
    TypeIdentifierExpr,
)
from prove.source import Span
from prove.errors import Diagnostic, DiagnosticLabel, Severity
from prove.types import (
    ERROR_TY,
    BorrowType,
    ErrorType,
    FunctionType,
    GenericInstance,
    PrimitiveType,
    RecordType,
    RefinementType,
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

    def _infer_call(self, expr: CallExpr) -> Type:
        # Determine function name and resolve
        arg_types = [self._infer_expr(a) for a in expr.args]
        arg_count = len(expr.args)

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
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
            if (
                sig is None
                or len(sig.param_types) != arg_count
                or not all(types_compatible(p, a) for p, a in zip(sig.param_types, arg_types))
            ):
                any_sig = self.symbols.resolve_function_any(name, arg_types)
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
            for i, (expected, actual) in enumerate(zip(sig.param_types, arg_types)):
                if not types_compatible(expected, actual):
                    extra = self._builtin_extra_types.get((name, i))
                    if extra and any(types_compatible(e, actual) for e in extra):
                        continue
                    if sig.verb == "validates" and isinstance(actual, GenericInstance):
                        if actual.base_name == "Option" and actual.args:
                            inner = actual.args[0]
                            if types_compatible(expected, inner):
                                continue
                    if (
                        sig.module == "parse"
                        and sig.verb in ("creates", "validates")
                        and sig.name == "value"
                        and isinstance(expected, (SimpleType, PrimitiveType))
                        and expected.name == "Source"
                        and is_json_serializable(actual)
                    ):
                        continue
                    self._error(
                        "E331",
                        f"argument type mismatch: expected "
                        f"'{type_name(expected)}', "
                        f"got '{type_name(actual)}'",
                        expr.span,
                    )

            # Ownership tracking: mark variables as moved if passed to Own parameters
            self._track_moved_args(expr.args, sig.param_types)

            # Verb-gated serialization: creates/validates value(V)
            # requires the argument to be json-serializable.
            if (
                sig.module
                and sig.module == "parse"
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
            # Requires-based narrowing for unqualified calls:
            # Option<V> → V, Result<T, E> → T
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
                    bindings = resolve_type_vars(
                        sig.param_types,
                        arg_types,
                    )
                    inner = substitute_type_vars(ret.args[0], bindings)
                    return inner
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
                sig = self.symbols.resolve_function_any(func_name, arg_types)
            if sig is None:
                self._error(
                    "E312",
                    f"undefined function '{func_name}' in module '{module_name}'",
                    expr.span,
                )
                return ERROR_TY
            ret = sig.return_type
            # Requires-based narrowing: if the return type is Option<V>
            # or Result<T, E> and there is a matching validates call in
            # requires, narrow to V or T respectively.
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
                    bindings = resolve_type_vars(
                        sig.param_types,
                        arg_types,
                    )
                    inner = substitute_type_vars(ret.args[0], bindings)
                    return inner
            return ret

        # For complex expressions (e.g., method-like calls), infer the function type
        func_type = self._infer_expr(expr.func)
        if isinstance(func_type, FunctionType):
            return func_type.return_type
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

        # Allow field access on GenericInstance, AlgebraicType, etc. without error
        # (duck typing / deferred check for generics)
        if isinstance(obj_type, (GenericInstance, TypeVariable)):
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
        """Mark variables as moved based on expression type."""
        if isinstance(expr, IdentifierExpr):
            sym = self.symbols.lookup(expr.name)
            if sym is not None and has_own_modifier(sym.resolved_type):
                self._moved_vars.add(expr.name)
        elif isinstance(expr, FieldExpr):
            self._track_moved_expr(expr.base)

    def _check_moved_var(self, name: str, span: Span) -> None:
        """Check if a variable has been moved and report error if so."""
        if name in self._moved_vars:
            self._error(
                "E340",
                f"use of moved value '{name}'",
                span,
            )
