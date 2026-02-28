"""Two-pass semantic analyzer for the Prove language.

Pass 1: Register all top-level declarations (types, functions, constants, imports).
Pass 2: Check each declaration body (type inference, verb enforcement, exhaustiveness).
"""

from __future__ import annotations

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    IfExpr,
    ImportDecl,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    MainDef,
    MatchExpr,
    ModifiedType,
    Module,
    PipeExpr,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    Stmt,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeDef,
    TypeExpr,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    VariantPattern,
    WildcardPattern,
)
from prove.errors import Diagnostic, DiagnosticLabel, Severity
from prove.source import Span
from prove.symbols import FunctionSignature, Symbol, SymbolKind, SymbolTable
from prove.types import (
    BOOLEAN,
    BUILTINS,
    CHARACTER,
    DECIMAL,
    ERROR_TY,
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    TypeVariable,
    VariantInfo,
    type_name,
    types_compatible,
)

# Verbs considered pure (no IO side effects allowed)
_PURE_VERBS = frozenset({"transforms", "validates"})

# Built-in functions considered to perform IO
_IO_FUNCTIONS = frozenset({
    "println", "print", "readln", "read_file", "write_file",
    "open", "close", "flush", "sleep",
})


class Checker:
    """Semantic analyzer for a single module."""

    def __init__(self) -> None:
        self.symbols = SymbolTable()
        self.diagnostics: list[Diagnostic] = []
        self._current_function: FunctionDef | MainDef | None = None

    # ── Public API ──────────────────────────────────────────────

    def check(self, module: Module) -> SymbolTable:
        """Run both passes on a module. Raises nothing; check self.diagnostics."""
        self._register_builtins()
        # Pass 1: register all top-level declarations
        for decl in module.declarations:
            if isinstance(decl, TypeDef):
                self._register_type(decl)
            elif isinstance(decl, FunctionDef):
                self._register_function(decl)
            elif isinstance(decl, ConstantDef):
                self._register_constant(decl)
            elif isinstance(decl, ImportDecl):
                self._register_import(decl)
            elif isinstance(decl, MainDef):
                self._register_main(decl)

        # Pass 2: check bodies
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                self._check_function(decl)
            elif isinstance(decl, MainDef):
                self._check_main(decl)
            elif isinstance(decl, ConstantDef):
                self._check_constant(decl)
            elif isinstance(decl, TypeDef):
                self._check_type_def(decl)

        # Check unused variables (W300)
        self._check_unused()

        return self.symbols

    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)

    # ── Error helpers ───────────────────────────────────────────

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
        ))

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
        ))

    # ── Pass 1: Registration ────────────────────────────────────

    def _register_builtins(self) -> None:
        """Register built-in types and functions."""
        # Built-in primitive types
        for name, ty in BUILTINS.items():
            self.symbols.define_type(name, ty)

        # Generic constructors
        self.symbols.define_type("Result", GenericInstance(
            "Result", [TypeVariable("T"), TypeVariable("E")],
        ))
        self.symbols.define_type("Option", GenericInstance(
            "Option", [TypeVariable("T")],
        ))
        self.symbols.define_type("List", ListType(TypeVariable("T")))
        self.symbols.define_type("Error", PrimitiveType("Error"))

        _dummy = Span("<builtin>", 0, 0, 0, 0)

        # Common built-in functions
        builtins = [
            ("println", [STRING], UNIT),
            ("print", [STRING], UNIT),
            ("readln", [], STRING),
            ("len", [ListType(TypeVariable("T"))], INTEGER),
            ("map", [
                ListType(TypeVariable("T")),
                FunctionType([TypeVariable("T")], TypeVariable("U")),
            ], ListType(TypeVariable("U"))),
            ("filter", [
                ListType(TypeVariable("T")),
                FunctionType([TypeVariable("T")], BOOLEAN),
            ], ListType(TypeVariable("T"))),
            ("reduce", [
                ListType(TypeVariable("T")), TypeVariable("U"),
                FunctionType(
                    [TypeVariable("U"), TypeVariable("T")],
                    TypeVariable("U"),
                ),
            ], TypeVariable("U")),
            ("to_string", [TypeVariable("T")], STRING),
            ("clamp", [INTEGER, INTEGER, INTEGER], INTEGER),
        ]
        for name, param_types, return_type in builtins:
            sig = FunctionSignature(
                verb=None, name=name,
                param_names=[f"p{i}" for i in range(len(param_types))],
                param_types=param_types,
                return_type=return_type,
                can_fail=False,
                span=_dummy,
            )
            self.symbols.define_function(sig)

    def _register_type(self, td: TypeDef) -> None:
        """Register a user-defined type."""
        existing = self.symbols.resolve_type(td.name)
        if existing is not None and not isinstance(existing, TypeVariable):
            self._error("E301", f"duplicate definition of '{td.name}'", td.span)
            return

        type_params = tuple(td.type_params)
        body = td.body

        if isinstance(body, RecordTypeDef):
            fields: dict[str, Type] = {}
            for f in body.fields:
                ft = self._resolve_type_expr(f.type_expr)
                fields[f.name] = ft
            resolved: Type = RecordType(td.name, fields, type_params)

        elif isinstance(body, AlgebraicTypeDef):
            variants: list[VariantInfo] = []
            for v in body.variants:
                vfields: dict[str, Type] = {}
                for f in v.fields:
                    vfields[f.name] = self._resolve_type_expr(f.type_expr)
                variants.append(VariantInfo(v.name, vfields))
            resolved = AlgebraicType(td.name, variants, type_params)
            # Register each variant as a constructor function
            for v in body.variants:
                vfield_types = [self._resolve_type_expr(f.type_expr) for f in v.fields]
                vsig = FunctionSignature(
                    verb=None, name=v.name,
                    param_names=[f.name for f in v.fields],
                    param_types=vfield_types,
                    return_type=resolved,
                    can_fail=False,
                    span=v.span,
                )
                self.symbols.define_function(vsig)

        elif isinstance(body, RefinementTypeDef):
            base = self._resolve_type_expr(body.base_type)
            resolved = RefinementType(td.name, base)

        else:
            resolved = ERROR_TY

        self.symbols.define_type(td.name, resolved)
        # Also register in scope as a type symbol
        self.symbols.define(Symbol(
            name=td.name, kind=SymbolKind.TYPE,
            resolved_type=resolved, span=td.span,
        ))

    def _register_function(self, fd: FunctionDef) -> None:
        """Register a function signature."""
        param_types = [self._resolve_type_expr(p.type_expr) for p in fd.params]
        return_type = self._resolve_type_expr(fd.return_type) if fd.return_type else UNIT
        sig = FunctionSignature(
            verb=fd.verb, name=fd.name,
            param_names=[p.name for p in fd.params],
            param_types=param_types,
            return_type=return_type,
            can_fail=fd.can_fail,
            span=fd.span,
        )
        self.symbols.define_function(sig)
        self.symbols.define(Symbol(
            name=fd.name, kind=SymbolKind.FUNCTION,
            resolved_type=FunctionType(param_types, return_type),
            span=fd.span, verb=fd.verb,
        ))

    def _register_main(self, md: MainDef) -> None:
        """Register the main function."""
        return_type = self._resolve_type_expr(md.return_type) if md.return_type else UNIT
        sig = FunctionSignature(
            verb=None, name="main",
            param_names=[], param_types=[],
            return_type=return_type,
            can_fail=md.can_fail,
            span=md.span,
        )
        self.symbols.define_function(sig)

    def _register_constant(self, cd: ConstantDef) -> None:
        """Register a constant."""
        resolved = self._resolve_type_expr(cd.type_expr) if cd.type_expr else ERROR_TY
        existing = self.symbols.define(Symbol(
            name=cd.name, kind=SymbolKind.CONSTANT,
            resolved_type=resolved, span=cd.span,
        ))
        if existing is not None:
            self._error("E301", f"duplicate definition of '{cd.name}'", cd.span)

    def _register_import(self, imp: ImportDecl) -> None:
        """Register imported names (shallow — no cross-module resolution)."""
        for item in imp.items:
            self.symbols.define(Symbol(
                name=item.name, kind=SymbolKind.FUNCTION,
                resolved_type=ERROR_TY, span=item.span,
                verb=item.verb,
            ))
            # Also register a function signature so calls resolve
            sig = FunctionSignature(
                verb=item.verb, name=item.name,
                param_names=[], param_types=[],
                return_type=ERROR_TY,
                can_fail=False,
                span=item.span,
            )
            self.symbols.define_function(sig)

    # ── Pass 2: Checking ────────────────────────────────────────

    def _check_function(self, fd: FunctionDef) -> None:
        """Check a function body."""
        self._current_function = fd
        self.symbols.push_scope(fd.name)

        # Register parameters
        param_types = [self._resolve_type_expr(p.type_expr) for p in fd.params]
        for param, pty in zip(fd.params, param_types):
            self.symbols.define(Symbol(
                name=param.name, kind=SymbolKind.PARAMETER,
                resolved_type=pty, span=param.span,
            ))

        # Check verb rules
        self._check_verb_rules(fd)

        # Check body
        body_type = UNIT
        for stmt in fd.body:
            body_type = self._check_stmt(stmt)

        # Validate return type
        return_type = self._resolve_type_expr(fd.return_type) if fd.return_type else UNIT
        if fd.verb == "validates":
            # validates has implicit Boolean return
            if fd.return_type is not None:
                self._error(
                    "E360", "validates has implicit Boolean return", fd.span,
                )
        elif not isinstance(body_type, ErrorType) and not types_compatible(return_type, body_type):
            # For failable functions, body can return the success type
            # e.g. Result<Integer, Error>! function body can return Integer
            success_compatible = False
            if fd.can_fail and isinstance(return_type, GenericInstance):
                if return_type.base_name == "Result" and return_type.args:
                    success_compatible = types_compatible(return_type.args[0], body_type)
            if not success_compatible:
                self._error(
                    "E322",
                    f"return type mismatch: expected "
                    f"'{type_name(return_type)}', "
                    f"got '{type_name(body_type)}'",
                    fd.span,
                )

        # ── Contract type-checking ──
        self._check_contracts(fd, return_type, param_types)

        self.symbols.pop_scope()
        self._current_function = None

    def _check_main(self, md: MainDef) -> None:
        """Check the main function body."""
        self._current_function = md
        self.symbols.push_scope("main")

        for stmt in md.body:
            self._check_stmt(stmt)

        self.symbols.pop_scope()
        self._current_function = None

    def _check_constant(self, cd: ConstantDef) -> None:
        """Check a constant definition."""
        inferred = self._infer_expr(cd.value)
        if cd.type_expr is not None:
            expected = self._resolve_type_expr(cd.type_expr)
            if not types_compatible(expected, inferred):
                self._error(
                    "E321",
                    f"type mismatch: expected '{type_name(expected)}', got '{type_name(inferred)}'",
                    cd.span,
                )

    def _check_type_def(self, td: TypeDef) -> None:
        """Validate field types exist."""
        body = td.body
        if isinstance(body, RecordTypeDef):
            for f in body.fields:
                self._resolve_type_expr(f.type_expr)
        elif isinstance(body, AlgebraicTypeDef):
            for v in body.variants:
                for f in v.fields:
                    self._resolve_type_expr(f.type_expr)

    # ── Contract checking ──────────────────────────────────────

    def _check_contracts(self, fd: FunctionDef, return_type: Type, param_types: list[Type]) -> None:
        """Type-check ensures/requires/know/assume/believe contracts."""
        # Type-check `ensures` — push sub-scope with `result` bound to return type
        for ens_expr in fd.ensures:
            self.symbols.push_scope("ensures")
            self.symbols.define(Symbol(
                name="result", kind=SymbolKind.VARIABLE,
                resolved_type=return_type, span=fd.span,
            ))
            ens_type = self._infer_expr(ens_expr)
            if not isinstance(ens_type, ErrorType) and not types_compatible(BOOLEAN, ens_type):
                self._error(
                    "E380",
                    f"ensures expression must be Boolean, got '{type_name(ens_type)}'",
                    ens_expr.span if hasattr(ens_expr, 'span') else fd.span,
                )
            self.symbols.pop_scope()

        # Type-check `requires` — params are already in scope
        for req_expr in fd.requires:
            req_type = self._infer_expr(req_expr)
            if not isinstance(req_type, ErrorType) and not types_compatible(BOOLEAN, req_type):
                self._error(
                    "E381",
                    f"requires expression must be Boolean, got '{type_name(req_type)}'",
                    req_expr.span if hasattr(req_expr, 'span') else fd.span,
                )

        # Type-check `know`
        for know_expr in fd.know:
            know_type = self._infer_expr(know_expr)
            if not isinstance(know_type, ErrorType) and not types_compatible(BOOLEAN, know_type):
                self._error(
                    "E384",
                    f"know expression must be Boolean, got '{type_name(know_type)}'",
                    know_expr.span if hasattr(know_expr, 'span') else fd.span,
                )

        # Type-check `assume`
        for assume_expr in fd.assume:
            assume_type = self._infer_expr(assume_expr)
            if (not isinstance(assume_type, ErrorType)
                    and not types_compatible(BOOLEAN, assume_type)):
                self._error(
                    "E385",
                    f"assume expression must be Boolean, got '{type_name(assume_type)}'",
                    assume_expr.span if hasattr(assume_expr, 'span') else fd.span,
                )

        # Type-check `believe`
        for believe_expr in fd.believe:
            self.symbols.push_scope("believe")
            self.symbols.define(Symbol(
                name="result", kind=SymbolKind.VARIABLE,
                resolved_type=return_type, span=fd.span,
            ))
            believe_type = self._infer_expr(believe_expr)
            if (not isinstance(believe_type, ErrorType)
                    and not types_compatible(BOOLEAN, believe_type)):
                self._error(
                    "E386",
                    f"believe expression must be Boolean, got '{type_name(believe_type)}'",
                    believe_expr.span if hasattr(believe_expr, 'span') else fd.span,
                )
            self.symbols.pop_scope()

        # Validate `satisfies` — each named type must exist
        for sat_name in fd.satisfies:
            resolved = self.symbols.resolve_type(sat_name)
            if resolved is None:
                self._error(
                    "E382",
                    f"satisfies references undefined type '{sat_name}'",
                    fd.span,
                )

        # Warning: intent set but no ensures/requires
        if fd.intent and not fd.ensures and not fd.requires:
            self._warning(
                "W310",
                "intent declared but no ensures or requires to validate it",
                fd.span,
            )

    # ── Verb enforcement ────────────────────────────────────────

    def _check_verb_rules(self, fd: FunctionDef) -> None:
        """Enforce verb purity constraints."""
        verb = fd.verb
        if verb in _PURE_VERBS:
            # Pure functions cannot be failable
            if fd.can_fail:
                self._error("E361", "pure function cannot be failable", fd.span)
            # Check body for IO calls
            self._check_pure_body(fd.body, fd.span)

    def _check_pure_body(self, body: list[Stmt | MatchExpr], span: Span) -> None:
        """Check that a body doesn't contain IO calls."""
        for stmt in body:
            self._check_pure_stmt(stmt)

    def _check_pure_stmt(self, stmt: Stmt | MatchExpr) -> None:
        """Check a single statement for IO calls."""
        if isinstance(stmt, VarDecl):
            self._check_pure_expr(stmt.value)
        elif isinstance(stmt, Assignment):
            self._check_pure_expr(stmt.value)
        elif isinstance(stmt, ExprStmt):
            self._check_pure_expr(stmt.expr)
        elif isinstance(stmt, MatchExpr):
            if stmt.subject:
                self._check_pure_expr(stmt.subject)
            for arm in stmt.arms:
                for s in arm.body:
                    self._check_pure_stmt(s)

    def _check_pure_expr(self, expr: Expr) -> None:
        """Check an expression for IO calls."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr) and expr.func.name in _IO_FUNCTIONS:
                self._error(
                    "E362", f"pure function cannot call IO function '{expr.func.name}'",
                    expr.span,
                )
            for arg in expr.args:
                self._check_pure_expr(arg)
        elif isinstance(expr, BinaryExpr):
            self._check_pure_expr(expr.left)
            self._check_pure_expr(expr.right)
        elif isinstance(expr, UnaryExpr):
            self._check_pure_expr(expr.operand)
        elif isinstance(expr, PipeExpr):
            self._check_pure_expr(expr.left)
            self._check_pure_expr(expr.right)
        elif isinstance(expr, IfExpr):
            self._check_pure_expr(expr.condition)
            for s in expr.then_body:
                self._check_pure_stmt(s)
            for s in expr.else_body:
                self._check_pure_stmt(s)
        elif isinstance(expr, FailPropExpr):
            self._check_pure_expr(expr.expr)
        elif isinstance(expr, LambdaExpr):
            self._check_pure_expr(expr.body)

    # ── Statement checking ──────────────────────────────────────

    def _check_stmt(self, stmt: Stmt | MatchExpr) -> Type:
        """Check a statement and return its type (for last-expression semantics)."""
        if isinstance(stmt, VarDecl):
            return self._check_var_decl(stmt)
        if isinstance(stmt, Assignment):
            return self._check_assignment(stmt)
        if isinstance(stmt, ExprStmt):
            return self._infer_expr(stmt.expr)
        if isinstance(stmt, MatchExpr):
            return self._infer_match(stmt)
        return UNIT

    def _check_var_decl(self, vd: VarDecl) -> Type:
        """Check a variable declaration."""
        inferred = self._infer_expr(vd.value)

        if vd.type_expr is not None:
            expected = self._resolve_type_expr(vd.type_expr)
            if not types_compatible(expected, inferred):
                self._error(
                    "E321",
                    f"type mismatch: expected '{type_name(expected)}', got '{type_name(inferred)}'",
                    vd.span,
                )
            resolved = expected
        else:
            resolved = inferred

        existing = self.symbols.define(Symbol(
            name=vd.name, kind=SymbolKind.VARIABLE,
            resolved_type=resolved, span=vd.span,
        ))
        if existing is not None:
            self._error("E302", f"variable '{vd.name}' already defined in this scope", vd.span)

        return UNIT

    def _check_assignment(self, assign: Assignment) -> Type:
        """Check an assignment statement."""
        sym = self.symbols.lookup(assign.target)
        if sym is None:
            self._error("E310", f"undefined name '{assign.target}'", assign.span)
            return UNIT

        sym.used = True
        value_type = self._infer_expr(assign.value)
        if not types_compatible(sym.resolved_type, value_type):
            self._error(
                "E321",
                f"type mismatch: expected "
                f"'{type_name(sym.resolved_type)}', "
                f"got '{type_name(value_type)}'",
                assign.span,
            )
        return UNIT

    # ── Expression type inference ───────────────────────────────

    def _infer_expr(self, expr: Expr) -> Type:
        """Infer the type of an expression."""
        if isinstance(expr, IntegerLit):
            return INTEGER
        if isinstance(expr, DecimalLit):
            return DECIMAL
        if isinstance(expr, StringLit):
            return STRING
        if isinstance(expr, BooleanLit):
            return BOOLEAN
        if isinstance(expr, CharLit):
            return CHARACTER
        if isinstance(expr, RegexLit):
            return STRING  # regex patterns are strings at type level
        if isinstance(expr, TripleStringLit):
            return STRING
        if isinstance(expr, StringInterp):
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
        if isinstance(expr, IfExpr):
            return self._infer_if(expr)
        if isinstance(expr, MatchExpr):
            return self._infer_match(expr)
        if isinstance(expr, LambdaExpr):
            return self._infer_lambda(expr)
        if isinstance(expr, IndexExpr):
            return self._infer_index(expr)
        if isinstance(expr, ValidExpr):
            return BOOLEAN
        if isinstance(expr, ComptimeExpr):
            return self._infer_comptime(expr)
        return ERROR_TY

    def _infer_identifier(self, expr: IdentifierExpr) -> Type:
        sym = self.symbols.lookup(expr.name)
        if sym is None:
            self._error("E310", f"undefined name '{expr.name}'", expr.span)
            return ERROR_TY
        sym.used = True
        return sym.resolved_type

    def _infer_type_identifier(self, expr: TypeIdentifierExpr) -> Type:
        """Type identifiers can be used as constructors or type references."""
        resolved = self.symbols.resolve_type(expr.name)
        if resolved is not None:
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
                self._error("E320", "type mismatch in binary expression", expr.span)
                return ERROR_TY
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

    def _infer_call(self, expr: CallExpr) -> Type:
        # Determine function name and resolve
        arg_types = [self._infer_expr(a) for a in expr.args]
        arg_count = len(expr.args)

        if isinstance(expr.func, IdentifierExpr):
            name = expr.func.name
            sig = self.symbols.resolve_function(None, name, arg_count)
            # Also try with verb from current function context
            if (sig is None and self._current_function
                    and isinstance(self._current_function, FunctionDef)):
                sig = self.symbols.resolve_function(
                    self._current_function.verb, name, arg_count,
                )
            if sig is None:
                sig = self.symbols.resolve_function_any(name)

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

            # Skip strict checks for imported functions (ErrorType return = unknown sig)
            if isinstance(sig.return_type, ErrorType):
                return sig.return_type

            # Check argument count
            if len(sig.param_types) != arg_count:
                expected_n = len(sig.param_types)
                self._error(
                    "E330",
                    f"wrong number of arguments: "
                    f"expected {expected_n}, got {arg_count}",
                    expr.span,
                )
                return sig.return_type

            # Check argument types
            for i, (expected, actual) in enumerate(zip(sig.param_types, arg_types)):
                if not types_compatible(expected, actual):
                    self._error(
                        "E331",
                        f"argument type mismatch: expected "
                        f"'{type_name(expected)}', "
                        f"got '{type_name(actual)}'",
                        expr.span,
                    )

            return sig.return_type

        if isinstance(expr.func, TypeIdentifierExpr):
            # Type constructor call — try as function first (variant constructors)
            name = expr.func.name
            sig = self.symbols.resolve_function(None, name, arg_count)
            if sig is None:
                sig = self.symbols.resolve_function_any(name)
            if sig is not None:
                if not isinstance(sig.return_type, ErrorType):
                    if len(sig.param_types) != arg_count:
                        expected_n = len(sig.param_types)
                        self._error(
                            "E330",
                            f"wrong number of arguments: "
                            f"expected {expected_n}, got {arg_count}",
                            expr.span,
                        )
                return sig.return_type
            # Fall back to type lookup (record constructor)
            resolved = self.symbols.resolve_type(name)
            if resolved is not None:
                return resolved
            self._error("E311", f"undefined function '{name}'", expr.span)
            return ERROR_TY

        # For complex expressions (e.g., method-like calls), infer the function type
        func_type = self._infer_expr(expr.func)
        if isinstance(func_type, FunctionType):
            return func_type.return_type
        return ERROR_TY

    def _infer_field(self, expr: FieldExpr) -> Type:
        obj_type = self._infer_expr(expr.obj)

        if isinstance(obj_type, ErrorType):
            return ERROR_TY

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
        self._infer_expr(expr.left)  # check left side for errors

        # The right side should be a function name or call
        if isinstance(expr.right, IdentifierExpr):
            name = expr.right.name
            sig = self.symbols.resolve_function(None, name, 1)
            if sig is None:
                sig = self.symbols.resolve_function_any(name)
            if sig is None:
                self._error("E311", f"undefined function '{name}'", expr.right.span)
                return ERROR_TY
            return sig.return_type

        if isinstance(expr.right, CallExpr) and isinstance(expr.right.func, IdentifierExpr):
            # a |> f(b, c) desugars to f(a, b, c)
            name = expr.right.func.name
            total_args = 1 + len(expr.right.args)
            sig = self.symbols.resolve_function(None, name, total_args)
            if sig is None:
                sig = self.symbols.resolve_function_any(name)
            if sig is None:
                self._error("E311", f"undefined function '{name}'", expr.right.span)
                return ERROR_TY
            return sig.return_type

        # Fallback: infer the right side
        right_type = self._infer_expr(expr.right)
        if isinstance(right_type, FunctionType):
            return right_type.return_type
        return ERROR_TY

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
                self._error(
                    "E350", "fail propagation in non-failable function", expr.span,
                )

        # The inner expression should be Result-like; return its success type
        if isinstance(inner, GenericInstance) and inner.base_name == "Result":
            if inner.args:
                return inner.args[0]
        return ERROR_TY

    def _infer_if(self, expr: IfExpr) -> Type:
        cond_type = self._infer_expr(expr.condition)
        if not isinstance(cond_type, ErrorType) and not types_compatible(BOOLEAN, cond_type):
            self._error(
                "E321",
                f"type mismatch: expected 'Boolean', got '{type_name(cond_type)}'",
                expr.condition.span if hasattr(expr.condition, 'span') else expr.span,
            )

        # Infer branch types
        then_type = UNIT
        for stmt in expr.then_body:
            then_type = self._check_stmt(stmt)

        else_type = UNIT
        for stmt in expr.else_body:
            else_type = self._check_stmt(stmt)

        # Both branches should be compatible
        if types_compatible(then_type, else_type):
            return then_type
        return ERROR_TY

    def _infer_match(self, expr: MatchExpr) -> Type:
        subject_type = ERROR_TY
        if expr.subject is not None:
            subject_type = self._infer_expr(expr.subject)

        # Check exhaustiveness for algebraic types
        if isinstance(subject_type, AlgebraicType):
            self._check_exhaustiveness(expr, subject_type)

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
        for pname in expr.params:
            pt = TypeVariable(pname)
            param_types.append(pt)
            self.symbols.define(Symbol(
                name=pname, kind=SymbolKind.PARAMETER,
                resolved_type=pt, span=expr.span,
            ))
        body_type = self._infer_expr(expr.body)
        self.symbols.pop_scope()
        return FunctionType(param_types, body_type)

    def _infer_index(self, expr: IndexExpr) -> Type:
        obj_type = self._infer_expr(expr.obj)
        self._infer_expr(expr.index)  # check index expression

        if isinstance(obj_type, ListType):
            return obj_type.element
        if isinstance(obj_type, ErrorType):
            return ERROR_TY
        return ERROR_TY

    def _infer_list(self, expr: ListLiteral) -> Type:
        if not expr.elements:
            return ListType(TypeVariable("T"))
        first = self._infer_expr(expr.elements[0])
        for elem in expr.elements[1:]:
            self._infer_expr(elem)
        return ListType(first)

    def _infer_comptime(self, expr: ComptimeExpr) -> Type:
        result = UNIT
        for stmt in expr.body:
            result = self._check_stmt(stmt)
        return result

    # ── Pattern checking ────────────────────────────────────────

    def _check_pattern(self, pattern, subject_type: Type) -> None:
        """Check a pattern and bind names."""
        if isinstance(pattern, BindingPattern):
            self.symbols.define(Symbol(
                name=pattern.name, kind=SymbolKind.VARIABLE,
                resolved_type=subject_type, span=pattern.span,
            ))
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
                self._warning("W301", "unreachable match arm after wildcard", arm.span)

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
                self._error(
                    "E371",
                    f"non-exhaustive match: missing {names}",
                    expr.span,
                )

    # ── Type resolution ─────────────────────────────────────────

    def _resolve_type_expr(self, type_expr: TypeExpr) -> Type:
        """Resolve a syntactic TypeExpr to a semantic Type."""
        if isinstance(type_expr, SimpleType):
            resolved = self.symbols.resolve_type(type_expr.name)
            if resolved is None:
                self._error("E300", f"undefined type '{type_expr.name}'", type_expr.span)
                return ERROR_TY
            return resolved

        if isinstance(type_expr, GenericType):
            args = [self._resolve_type_expr(a) for a in type_expr.args]
            # Special-case List<T> → ListType
            if type_expr.name == "List" and len(args) == 1:
                return ListType(args[0])
            # Check base type exists
            base = self.symbols.resolve_type(type_expr.name)
            if base is None:
                self._error("E300", f"undefined type '{type_expr.name}'", type_expr.span)
                return ERROR_TY
            return GenericInstance(type_expr.name, args)

        if isinstance(type_expr, ModifiedType):
            base = self.symbols.resolve_type(type_expr.name)
            if base is None:
                self._error("E300", f"undefined type '{type_expr.name}'", type_expr.span)
                return ERROR_TY
            mods = tuple(m.value for m in type_expr.modifiers)
            return PrimitiveType(type_expr.name, mods)

        return ERROR_TY

    # ── Unused checks ───────────────────────────────────────────

    def _check_unused(self) -> None:
        """Warn about unused variables in module scope."""
        for sym in self.symbols.current_scope.all_symbols():
            if sym.kind == SymbolKind.VARIABLE and not sym.used:
                self._warning("W300", f"unused variable '{sym.name}'", sym.span)
