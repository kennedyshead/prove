"""Type inference and resolution mixin for Checker."""

from __future__ import annotations

from prove.ast_nodes import (
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    ComptimeExpr,
    DecimalLit,
    Expr,
    FailPropExpr,
    FieldExpr,
    FloatLit,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    MainDef,
    MatchExpr,
    ModifiedType,
    PathLit,
    Pattern,
    PipeExpr,
    RawStringLit,
    RegexLit,
    SimpleType,
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeExpr,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VariantPattern,
    WildcardPattern,
)
from prove.errors import (
    Diagnostic,
    DiagnosticLabel,
    Severity,
    Suggestion,
    make_diagnostic,
)
from prove.source import Span
from prove.symbols import Symbol, SymbolKind
from prove.types import (
    BOOLEAN,
    CHARACTER,
    DECIMAL,
    ERROR_TY,
    FLOAT,
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    BorrowType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ArrayType,
    ListType,
    PrimitiveType,
    RecordType,
    Type,
    TypeVariable,
    numeric_widen,
    types_compatible,
)


class TypeCheckMixin:
    """Mixin providing type inference, pattern checking, and type resolution."""

    # ── Type inference ───────────────────────────────────────────

    def _infer_expr(self, expr: Expr) -> Type:
        """Infer the type of an expression."""
        if isinstance(expr, IntegerLit):
            return INTEGER
        if isinstance(expr, DecimalLit):
            return DECIMAL
        if isinstance(expr, FloatLit):
            return FLOAT
        if isinstance(expr, StringLit):
            return STRING
        if isinstance(expr, BooleanLit):
            return BOOLEAN
        if isinstance(expr, CharLit):
            return CHARACTER
        if isinstance(expr, RegexLit):
            return STRING  # regex patterns are strings at type level
        if isinstance(expr, RawStringLit):
            return PrimitiveType("String", ("Reg",))
        if isinstance(expr, PathLit):
            return STRING  # path literals are string-typed
        if isinstance(expr, TripleStringLit):
            return STRING
        if isinstance(expr, StringInterp):
            for part in expr.parts:
                if not isinstance(part, StringLit):
                    part_type = self._infer_expr(part)
                    if not self._is_stringable(part_type):
                        self._error(
                            "E325",
                            f"f-string interpolation requires a stringable type, got {part_type}",
                            part.span,
                        )
            return STRING
        if isinstance(expr, ListLiteral):
            return self._infer_list(expr)
        if isinstance(expr, IdentifierExpr):
            return self._infer_identifier(expr)
        if isinstance(expr, TypeIdentifierExpr):
            return self._infer_type_identifier(expr)
        if isinstance(expr, BinaryExpr):
            return self._infer_binary(expr)
        if isinstance(expr, UnaryExpr):
            return self._infer_unary(expr)
        if isinstance(expr, CallExpr):
            return self._infer_call(expr)
        if isinstance(expr, FieldExpr):
            return self._infer_field(expr)
        if isinstance(expr, PipeExpr):
            return self._infer_pipe(expr)
        if isinstance(expr, FailPropExpr):
            return self._infer_fail_prop(expr)
        if isinstance(expr, MatchExpr):
            return self._infer_match(expr)
        if isinstance(expr, LambdaExpr):
            return self._infer_lambda(expr)
        if isinstance(expr, IndexExpr):
            return self._infer_index(expr)
        if isinstance(expr, ValidExpr):
            if expr.args is None:
                # Function reference: valid error → FunctionType([Diagnostic], Boolean)
                sig = self.symbols.resolve_function_any(expr.name)
                if sig is not None and sig.param_types:
                    return FunctionType(list(sig.param_types), BOOLEAN)
            return BOOLEAN
        if isinstance(expr, ComptimeExpr):
            return self._infer_comptime(expr)
        if isinstance(expr, LookupAccessExpr):
            return self._check_lookup_access_expr(expr)
        if isinstance(expr, StoreLookupExpr):
            return self._check_store_lookup_expr(expr)
        return ERROR_TY

    def _infer_identifier(self, expr: IdentifierExpr) -> Type:
        sym = self.symbols.lookup(expr.name)
        if sym is None:
            diag = Diagnostic(
                severity=Severity.ERROR,
                code="E310",
                message=f"undefined name '{expr.name}'",
                labels=[DiagnosticLabel(span=expr.span, message="")],
            )
            suggestion = self._fuzzy_match(
                expr.name,
                self.symbols.all_known_names(),
            )
            if suggestion:
                diag.notes.append(f"did you mean '{suggestion}'?")
            self.diagnostics.append(diag)
            return ERROR_TY
        sym.used = True
        # Check for use-after-move error
        self._check_moved_var(expr.name, expr.span)
        return sym.resolved_type

    def _infer_type_identifier(self, expr: TypeIdentifierExpr) -> Type:
        """Type identifiers can be used as constructors or type references."""
        resolved = self.symbols.resolve_type(expr.name)
        if resolved is not None:
            self._used_types.add(expr.name)
            return resolved
        sym = self.symbols.lookup(expr.name)
        if sym is not None:
            sym.used = True
            return sym.resolved_type
        self._error("E310", f"undefined name '{expr.name}'", expr.span)
        return ERROR_TY

    def _infer_binary(self, expr: BinaryExpr) -> Type:
        left = self._infer_expr(expr.left)
        right = self._infer_expr(expr.right)

        # Error types propagate without cascading
        if isinstance(left, ErrorType) or isinstance(right, ErrorType):
            return ERROR_TY

        # Comparison operators always return Boolean
        if expr.op in ("==", "!=", "<", ">", "<=", ">="):
            return BOOLEAN

        # Logical operators require Boolean operands
        if expr.op in ("&&", "||"):
            if not types_compatible(BOOLEAN, left):
                self._error("E320", "type mismatch in binary expression", expr.span)
            if not types_compatible(BOOLEAN, right):
                self._error("E320", "type mismatch in binary expression", expr.span)
            return BOOLEAN

        # Arithmetic operators
        if expr.op in ("+", "-", "*", "/", "%"):
            if not types_compatible(left, right):
                # Try numeric widening (Integer → Decimal → Float)
                widened = numeric_widen(left, right)
                if widened is None:
                    self._error(
                        "E320",
                        "type mismatch in binary expression",
                        expr.span,
                    )
                    return ERROR_TY
                return widened
            # String concatenation
            if isinstance(left, PrimitiveType) and left.name == "String" and expr.op == "+":
                return STRING
            return left

        # Range
        if expr.op == "..":
            return ListType(left)

        return left

    def _infer_unary(self, expr: UnaryExpr) -> Type:
        operand = self._infer_expr(expr.operand)
        if expr.op == "!":
            return BOOLEAN
        if expr.op == "-":
            return operand
        return operand

    # ── Fail propagation, match, lambda, index, list, comptime ─

    def _infer_fail_prop(self, expr: FailPropExpr) -> Type:
        """Check fail propagation (!)."""
        inner = self._infer_expr(expr.expr)

        # Current function must be failable
        if self._current_function is not None:
            can_fail = False
            if isinstance(self._current_function, FunctionDef):
                can_fail = self._current_function.can_fail
            elif isinstance(self._current_function, MainDef):
                can_fail = self._current_function.can_fail
            if not can_fail:
                self.diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E350",
                        message="fail propagation in non-failable function",
                        labels=[DiagnosticLabel(span=expr.span, message="")],
                        suggestions=[
                            Suggestion(
                                message="mark the function as failable",
                                replacement="add '!' after the return type",
                            )
                        ],
                    )
                )

        # The inner expression should be Result-like; return its success type
        if isinstance(inner, GenericInstance) and inner.base_name == "Result":
            if inner.args:
                return inner.args[0]
        return ERROR_TY

    @staticmethod
    def _exprs_equal(a: Expr, b: Expr) -> bool:
        """Structurally compare two expressions ignoring spans."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IdentifierExpr):
            return a.name == b.name
        if isinstance(a, (IntegerLit, DecimalLit, StringLit)):
            return a.value == b.value
        if isinstance(a, BooleanLit):
            return a.value == b.value
        if isinstance(a, BinaryExpr):
            return (
                a.op == b.op
                and TypeCheckMixin._exprs_equal(a.left, b.left)
                and TypeCheckMixin._exprs_equal(a.right, b.right)
            )
        if isinstance(a, UnaryExpr):
            return a.op == b.op and TypeCheckMixin._exprs_equal(a.operand, b.operand)
        if isinstance(a, CallExpr):
            return (
                TypeCheckMixin._exprs_equal(a.func, b.func)
                and len(a.args) == len(b.args)
                and all(TypeCheckMixin._exprs_equal(x, y) for x, y in zip(a.args, b.args))
            )
        if isinstance(a, FieldExpr):
            return a.field == b.field and TypeCheckMixin._exprs_equal(a.obj, b.obj)
        if isinstance(a, TypeIdentifierExpr):
            return a.name == b.name
        return False

    def _infer_match(self, expr: MatchExpr) -> Type:
        subject_type = ERROR_TY
        if expr.subject is not None:
            subject_type = self._infer_expr(expr.subject)

        # W304: match on condition already guaranteed by requires
        if expr.subject is not None and isinstance(self._current_function, FunctionDef):
            for req in self._current_function.requires:
                if self._exprs_equal(expr.subject, req):
                    diag = make_diagnostic(
                        Severity.WARNING,
                        "W304",
                        "match condition is always true (guaranteed by requires)",
                        labels=[
                            DiagnosticLabel(
                                span=expr.span,
                                message="",
                            )
                        ],
                        notes=[
                            "The `requires` clause already guarantees this "
                            "condition. Remove the `match` and use the "
                            "`true` branch directly.",
                        ],
                    )
                    self.diagnostics.append(diag)
                    break

        # Check exhaustiveness for algebraic types
        if isinstance(subject_type, AlgebraicType):
            self._check_exhaustiveness(expr, subject_type)

        # I301: detect unreachable arms after always-matching record pattern
        resolved_subj = subject_type
        if isinstance(resolved_subj, PrimitiveType):
            rt = self.symbols.resolve_type(resolved_subj.name)
            if isinstance(rt, RecordType):
                resolved_subj = rt
        if isinstance(resolved_subj, RecordType):
            record_seen = False
            for arm in expr.arms:
                if record_seen:
                    self._info(
                        "I301",
                        "unreachable match arm after always-matching "
                        f"'{resolved_subj.name}' pattern",
                        arm.span,
                    )
                if (
                    isinstance(arm.pattern, VariantPattern)
                    and arm.pattern.name == resolved_subj.name
                ):
                    record_seen = True

        # Infer arm types
        result_type: Type = UNIT
        for arm in expr.arms:
            self.symbols.push_scope("match_arm")
            self._check_pattern(arm.pattern, subject_type)
            arm_type = UNIT
            for stmt in arm.body:
                arm_type = self._check_stmt(stmt)
            result_type = arm_type
            self.symbols.pop_scope()

        return result_type

    def _infer_lambda(self, expr: LambdaExpr) -> Type:
        self.symbols.push_scope("lambda")
        param_types: list[Type] = []
        param_names = set(expr.params)
        for pname in expr.params:
            pt = TypeVariable(pname)
            param_types.append(pt)
            self.symbols.define(
                Symbol(
                    name=pname,
                    kind=SymbolKind.PARAMETER,
                    resolved_type=pt,
                    span=expr.span,
                )
            )

        # Check for closure captures (not supported in v0.1)
        self._check_lambda_captures(expr.body, param_names, expr.span)

        body_type = self._infer_expr(expr.body)
        self.symbols.pop_scope()
        return FunctionType(param_types, body_type)

    def _check_lambda_captures(
        self,
        expr: Expr,
        param_names: set[str],
        span: Span,
    ) -> None:
        """Detect closure captures in lambda body (not supported)."""
        if isinstance(expr, IdentifierExpr):
            if expr.name not in param_names:
                # Check if it's a local variable from enclosing scope
                sym = self.symbols.lookup(expr.name)
                if sym is not None and sym.kind == SymbolKind.VARIABLE:
                    self._error(
                        "E364",
                        f"lambda captures variable '{expr.name}' (closures not supported)",
                        span,
                    )
        elif isinstance(expr, BinaryExpr):
            self._check_lambda_captures(expr.left, param_names, span)
            self._check_lambda_captures(expr.right, param_names, span)
        elif isinstance(expr, UnaryExpr):
            self._check_lambda_captures(expr.operand, param_names, span)
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._check_lambda_captures(arg, param_names, span)

    def _infer_index(self, expr: IndexExpr) -> Type:
        obj_type = self._infer_expr(expr.obj)
        self._infer_expr(expr.index)  # check index expression

        if isinstance(obj_type, ListType):
            return obj_type.element
        if isinstance(obj_type, ErrorType):
            return ERROR_TY
        return ERROR_TY

    def _is_stringable(self, ty: Type) -> bool:
        """Return True if the type can be interpolated into an f-string."""
        if isinstance(ty, BorrowType):
            ty = ty.inner
        if ty in (STRING, INTEGER, DECIMAL, FLOAT, BOOLEAN, CHARACTER):
            return True
        if isinstance(ty, PrimitiveType) and ty.name == "Error":
            return True
        return False

    def _infer_list(self, expr: ListLiteral) -> Type:
        if not expr.elements:
            return ListType(TypeVariable("Value"))
        first = self._infer_expr(expr.elements[0])
        for elem in expr.elements[1:]:
            self._infer_expr(elem)
        return ListType(first)

    def _infer_comptime(self, expr: ComptimeExpr) -> Type:
        # Register comptime built-in functions so type-checking passes
        comptime_builtins = {
            "platform": FunctionType([], STRING),
            "read": FunctionType([STRING], STRING),
        }
        for name, ty in comptime_builtins.items():
            if self.symbols.lookup(name) is None:
                self.symbols.define(
                    Symbol(
                        name=name,
                        kind=SymbolKind.FUNCTION,
                        resolved_type=ty,
                        span=expr.span,
                    )
                )
        result = UNIT
        for stmt in expr.body:
            result = self._check_stmt(stmt)
        return result

    # ── Pattern checking ────────────────────────────────────────

    def _check_pattern(self, pattern: Pattern, subject_type: Type) -> None:
        """Check a pattern and bind names."""
        if isinstance(pattern, BindingPattern):
            self.symbols.define(
                Symbol(
                    name=pattern.name,
                    kind=SymbolKind.VARIABLE,
                    resolved_type=subject_type,
                    span=pattern.span,
                )
            )
        elif isinstance(pattern, VariantPattern):
            # Check variant exists
            if isinstance(subject_type, AlgebraicType):
                found = False
                for v in subject_type.variants:
                    if v.name == pattern.name:
                        found = True
                        # Bind sub-patterns
                        for i, sub in enumerate(pattern.fields):
                            field_names = list(v.fields.keys())
                            if i < len(field_names):
                                ft = v.fields[field_names[i]]
                            else:
                                ft = ERROR_TY
                            self._check_pattern(sub, ft)
                        break
                if not found:
                    self._error("E370", f"unknown variant '{pattern.name}'", pattern.span)
        elif isinstance(pattern, WildcardPattern):
            pass  # matches everything
        elif isinstance(pattern, LiteralPattern):
            pass  # literal match

    # ── Match exhaustiveness ────────────────────────────────────

    def _check_exhaustiveness(self, expr: MatchExpr, subject_type: AlgebraicType) -> None:
        """Check match exhaustiveness for algebraic types."""
        variant_names = {v.name for v in subject_type.variants}
        covered: set[str] = set()
        has_wildcard = False
        wildcard_seen = False

        for arm in expr.arms:
            if wildcard_seen:
                self._info("I301", "unreachable match arm after wildcard", arm.span)

            if isinstance(arm.pattern, VariantPattern):
                if arm.pattern.name in variant_names:
                    covered.add(arm.pattern.name)
                else:
                    self._error("E370", f"unknown variant '{arm.pattern.name}'", arm.pattern.span)
            elif isinstance(arm.pattern, WildcardPattern):
                has_wildcard = True
                wildcard_seen = True
            elif isinstance(arm.pattern, BindingPattern):
                has_wildcard = True
                wildcard_seen = True

        if not has_wildcard:
            missing = variant_names - covered
            if missing:
                names = ", ".join(sorted(missing))
                arms_str = " | ".join(f"{v} => ..." for v in sorted(missing))
                self.diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E371",
                        message=f"non-exhaustive match: missing {names}",
                        labels=[DiagnosticLabel(span=expr.span, message="")],
                        suggestions=[
                            Suggestion(
                                message="add the missing arms",
                                replacement=arms_str,
                            )
                        ],
                    )
                )

    # ── Lookup table checking ────────────────────────────────────

    def _check_lookup_access_expr(self, expr: LookupAccessExpr) -> Type:
        """Resolve a TypeName:operand lookup expression (E376, E377, E378)."""
        type_name = expr.type_name

        # Find the lookup table for this type
        lookup = self._lookup_tables.get(type_name)
        if lookup is None:
            self._error(
                "E377",
                f"'{type_name}' is not a [Lookup] type",
                expr.span,
            )
            return ERROR_TY

        operand = expr.operand

        # Forward: literal -> variant (or binary cross-column lookup)
        if isinstance(operand, (StringLit, IntegerLit, BooleanLit)):
            value = operand.value
            if isinstance(operand, BooleanLit):
                value = "true" if operand.value else "false"

            # Binary lookup: search all columns, return target column type
            if lookup.is_binary and lookup.value_types:
                from prove.types import type_name as tn

                str_value = str(value)
                for entry in lookup.entries:
                    if str_value in entry.values:
                        # Found the row — determine return type from context
                        expected = self._expected_type
                        if expected is not None:
                            for vt in lookup.value_types:
                                col_type = self._resolve_type_expr(vt)
                                if tn(col_type) == tn(expected):
                                    self._used_types.add(type_name)
                                    return col_type
                        # No expected type — return the algebraic type
                        resolved = self.symbols.resolve_type(type_name)
                        if resolved is not None:
                            self._used_types.add(type_name)
                        return resolved if resolved else ERROR_TY
                self._error(
                    "E377",
                    f"value {value!r} not found in lookup table '{type_name}'",
                    expr.span,
                )
                return ERROR_TY

            # Single-column lookup: return algebraic type
            for entry in lookup.entries:
                if entry.value == str(value):
                    resolved = self.symbols.resolve_type(type_name)
                    if resolved is not None:
                        self._used_types.add(type_name)
                    return resolved if resolved else ERROR_TY
            self._error(
                "E377",
                f"value {value!r} not found in lookup table '{type_name}'",
                expr.span,
            )
            return ERROR_TY

        # Reverse: variant -> value
        if isinstance(operand, TypeIdentifierExpr):
            matches = [e for e in lookup.entries if e.variant == operand.name]
            if not matches:
                self._error(
                    "E377",
                    f"variant '{operand.name}' not found in lookup table '{type_name}'",
                    expr.span,
                )
                return ERROR_TY

            # Binary lookup with multiple columns: use expected type
            # to select the correct column
            if lookup.is_binary and lookup.value_types:
                # E399: reject ambiguous type-based access on duplicate types
                expected = self._expected_type
                if expected is not None:
                    from prove.types import type_name as tn

                    exp_name = tn(expected)
                    col_type_names = [
                        vt.name if hasattr(vt, "name") else str(vt)
                        for vt in lookup.value_types
                    ]
                    if col_type_names.count(exp_name) > 1:
                        has_names = lookup.column_names and any(
                            n is not None for n in lookup.column_names
                        )
                        if not has_names:
                            self._error(
                                "E399",
                                f"ambiguous column type '{exp_name}' in "
                                f"lookup '{type_name}'; "
                                f"use named columns to disambiguate",
                                expr.span,
                            )
                            return ERROR_TY

                    for vt in lookup.value_types:
                        col_type = self._resolve_type_expr(vt)
                        if tn(col_type) == exp_name:
                            self._used_types.add(type_name)
                            return col_type
                # No expected type or no match — return first column
                self._used_types.add(type_name)
                return self._resolve_type_expr(lookup.value_types[0])

            # Single-column lookup
            if len(matches) > 1:
                values = ", ".join(f'"{e.value}"' for e in matches)
                self._error(
                    "E378",
                    f"'{operand.name}' has {len(matches)} values "
                    f"({values}) — "
                    f"reverse lookup is ambiguous. "
                    f"Use a matches function instead.",
                    expr.span,
                )
                return ERROR_TY
            value_type = self._resolve_type_expr(lookup.value_type)
            return value_type

        # Dispatch lookup: any expression operand → verb dispatch
        if lookup.is_dispatch:
            self._infer_expr(operand)
            self._used_types.add(type_name)
            # Mark all entry verb functions as used so imports aren't pruned
            for entry in lookup.entries:
                sig = self.symbols.resolve_function_any(entry.variant)
                if sig is not None and sig.module:
                    self._used_imports.add((sig.module, entry.variant))
            return PrimitiveType("Verb")

        # Binary lookup: allow variable operands for runtime lookup
        if isinstance(operand, IdentifierExpr) and lookup.is_binary:
            return self._check_binary_lookup_access(expr, lookup)

        # Anything else (variable, call, etc.) is E376
        self._error(
            "E376",
            "lookup operand must be a literal or variant name",
            expr.span,
        )
        return ERROR_TY

    def _check_store_lookup_expr(self, expr: StoreLookupExpr) -> Type:
        """Type-check a store-backed lookup: variable:"key"."""
        from prove.ast_nodes import LookupTypeDef

        # Resolve the table variable
        sym = self.symbols.lookup(expr.table_var)
        if sym is None:
            self._error("E310", f"undefined name '{expr.table_var}'", expr.span)
            return ERROR_TY

        # Get the type name and check it's a store-backed lookup type
        var_type = sym.resolved_type
        type_name_str = getattr(var_type, "name", "")
        if type_name_str not in self._store_lookup_types:
            self._error(
                "E377",
                f"'{expr.table_var}' is not a store-backed [Lookup] variable",
                expr.span,
            )
            return ERROR_TY

        lookup = self._lookup_tables.get(type_name_str)
        if lookup is None or not isinstance(lookup, LookupTypeDef):
            return ERROR_TY

        # Infer operand type
        self._infer_expr(expr.operand)

        # Return type from expected context (e.g., Integer from `color as Integer = ...`)
        expected = self._expected_type
        if expected is not None:
            return expected

        # Fallback: return first column type
        if lookup.value_types:
            return self._resolve_type_expr(lookup.value_types[0])

        return ERROR_TY

    def _check_binary_lookup_access(self, expr: LookupAccessExpr, lookup: object) -> Type:
        """Resolve a binary lookup with a variable operand (runtime)."""
        from prove.ast_nodes import LookupTypeDef
        from prove.types import type_name

        assert isinstance(lookup, LookupTypeDef)
        operand = expr.operand
        assert isinstance(operand, IdentifierExpr)
        type_name_str_ = expr.type_name

        # Resolve the variable's type (validates operand)
        self._infer_expr(operand)

        # Determine target type: prefer expected type from VarDecl context,
        # fall back to enclosing function's return type
        ret_type: Type | None = self._expected_type
        if (
            ret_type is None
            and isinstance(self._current_function, FunctionDef)
            and self._current_function.return_type
        ):
            ret_type = self._resolve_type_expr(self._current_function.return_type)

        if ret_type is None:
            self._error(
                "E389",
                f"cannot determine return column for lookup '{type_name_str_}'",
                expr.span,
            )
            return ERROR_TY

        # Check if the return type matches any column type
        for vt in lookup.value_types:
            col_type = self._resolve_type_expr(vt)
            if type_name(col_type) == type_name(ret_type):
                self._used_types.add(type_name_str_)
                return ret_type

        # Check if return type is the algebraic type itself
        resolved_alg = self.symbols.resolve_type(type_name_str_)
        if resolved_alg and type_name(resolved_alg) == type_name(ret_type):
            self._used_types.add(type_name_str_)
            return ret_type

        # Unwrap RefinementType → ListType → element for HOF lambda context
        # (e.g. Plan = List<Verb> where true, lookup inside map lambda)
        from prove.types import ListType, RefinementType

        unwrapped: Type | None = ret_type
        if isinstance(unwrapped, RefinementType):
            unwrapped = unwrapped.base
        if isinstance(unwrapped, ListType):
            unwrapped = unwrapped.element
        if unwrapped is not ret_type:
            for vt in lookup.value_types:
                col_type = self._resolve_type_expr(vt)
                if type_name(col_type) == type_name(unwrapped):
                    self._used_types.add(type_name_str_)
                    return col_type

        self._error(
            "E389",
            f"return type '{type_name(ret_type)}' does not match any column "
            f"in lookup '{type_name_str_}'",
            expr.span,
        )
        return ERROR_TY

    # ── Type resolution ─────────────────────────────────────────

    def _error_undefined_type(self, name: str, span: Span) -> None:
        """Emit E300 with a 'did you mean' suggestion when possible."""
        candidates = set(self.symbols.all_types().keys())
        suggestion = self._fuzzy_match(name, candidates)
        msg = f"undefined type `{name}`"
        if suggestion:
            msg += f"; did you mean `{suggestion}`?"
        self._error("E300", msg, span)

    def _resolve_type_expr(self, type_expr: TypeExpr) -> Type:
        """Resolve a syntactic TypeExpr to a semantic Type."""
        if isinstance(type_expr, SimpleType):
            resolved = self.symbols.resolve_type(type_expr.name)
            if resolved is None:
                self._error_undefined_type(type_expr.name, type_expr.span)
                return ERROR_TY
            self._used_types.add(type_expr.name)
            return resolved

        if isinstance(type_expr, GenericType):
            args = [self._resolve_type_expr(a) for a in type_expr.args]
            # Special-case List<Value> → ListType
            if type_expr.name == "List" and len(args) == 1:
                return ListType(args[0])
            # Special-case Array<T> → ArrayType
            if type_expr.name == "Array" and len(args) == 1:
                mods = tuple(m.value for m in type_expr.modifiers)
                if mods:
                    return ArrayType(args[0], modifiers=mods)
                return ArrayType(args[0])
            # Special-case Verb<P1, ..., Pn, R> → FunctionType
            if type_expr.name == "Verb" and len(args) >= 1:
                return FunctionType(list(args[:-1]), args[-1])
            # Check base type exists
            base = self.symbols.resolve_type(type_expr.name)
            if base is None:
                self._error_undefined_type(type_expr.name, type_expr.span)
                return ERROR_TY
            self._used_types.add(type_expr.name)
            return GenericInstance(type_expr.name, args)

        if isinstance(type_expr, ModifiedType):
            base = self.symbols.resolve_type(type_expr.name)
            if base is None:
                self._error_undefined_type(type_expr.name, type_expr.span)
                return ERROR_TY
            self._used_types.add(type_expr.name)
            mods = tuple(m.value for m in type_expr.modifiers)
            return PrimitiveType(type_expr.name, mods)

        return ERROR_TY
