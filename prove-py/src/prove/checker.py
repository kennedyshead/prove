"""Two-pass semantic analyzer for the Prove language.

Pass 1: Register all top-level declarations (types, functions, constants, imports).
Pass 2: Check each declaration body (type inference, verb enforcement, exhaustiveness).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from prove._check_calls import CallCheckMixin
from prove._check_contracts import ContractCheckMixin
from prove._check_types import TypeCheckMixin
from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    AsyncCallExpr,
    BinaryDef,
    BinaryExpr,
    BinaryLookupExpr,
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
    FieldAssignment,
    FieldExpr,
    FloatLit,
    ForeignBlock,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    ImportDecl,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupPattern,
    LookupTypeDef,
    MainDef,
    MatchArm,
    MatchExpr,
    ModifiedType,
    Module,
    ModuleDecl,
    Param,
    PathLit,
    Pattern,
    PipeExpr,
    RawStringLit,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    Stmt,
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TodoStmt,
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
from prove.errors import (
    Diagnostic,
    DiagnosticLabel,
    Severity,
    Suggestion,
    make_diagnostic,
)
from prove.prover import ProofVerifier
from prove.source import Span
from prove.symbols import FunctionSignature, Symbol, SymbolKind, SymbolTable
from prove.types import (
    BOOLEAN,
    BUILTIN_FUNCTIONS,
    BUILTINS,
    CHARACTER,
    DECIMAL,
    ERROR_TY,
    FLOAT,
    INTEGER,
    STORE_BACKED_TYPES,
    STRING,
    UNIT,
    AlgebraicType,
    ArrayType,
    BorrowType,  # noqa: E501
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
    UnitType,
    VariantInfo,
    get_scale,
    has_mutable_modifier,
    has_own_modifier,
    numeric_widen,
    type_name,
    types_compatible,
)


def _count_decimal_places(literal: str) -> int:
    """Count decimal places in a numeric literal string like '3.14159'."""
    if "." in literal:
        return len(literal.split(".")[1].rstrip("0") or "0")
    return 0


# Verbs considered pure (no IO side effects allowed)
_PURE_VERBS = frozenset({"transforms", "validates", "reads", "creates", "matches"})

# Async verb family
_ASYNC_VERBS = frozenset({"detached", "attached", "listens", "renders"})

# IO (blocking) verbs — forbidden inside async bodies
_BLOCKING_VERBS = frozenset({"inputs", "outputs", "streams"})

# Verbs that need ownership of their parameters (skip borrow inference)
_VERBS_NEED_OWNERSHIP = frozenset(
    {
        "outputs",
        "matches",
        "creates",
        "validates",
        "inputs",
        "transforms",
        "reads",
        "detached",
        "attached",
        "listens",
        "streams",
    }
)

# Built-in functions considered to perform IO
_IO_FUNCTIONS = frozenset(
    {
        "sleep",
    }
)

# Re-export for external consumers (export.py)
_BUILTIN_FUNCTIONS = BUILTIN_FUNCTIONS

# Built-in type names that user code must not shadow
_BUILTIN_TYPE_NAMES = frozenset(
    {
        "Integer",
        "Decimal",
        "Float",
        "Boolean",
        "String",
        "Character",
        "Byte",
        "Unit",
        "List",
        "Option",
        "Result",
        "Error",
        "Table",
        "Value",
        "Source",
        "Verb",
        "Attached",
        "Listens",
    }
)


def _edit_distance(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _extract_call_targets(
    stmts: list[Stmt | MatchExpr],
) -> list[tuple[str, "Span"]]:
    """Walk a function body and extract (callee_name, call_span) pairs."""
    from prove.source import Span as _Span  # noqa: F811

    targets: list[tuple[str, _Span]] = []

    def _walk_expr(expr: Expr) -> None:
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                targets.append((expr.func.name, expr.span))
            elif isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, IdentifierExpr):
                # Module.func() → just track the function name
                targets.append((expr.func.field, expr.span))
            for arg in expr.args:
                _walk_expr(arg)
        elif isinstance(expr, BinaryExpr):
            _walk_expr(expr.left)
            _walk_expr(expr.right)
        elif isinstance(expr, UnaryExpr):
            _walk_expr(expr.operand)
        elif isinstance(expr, FieldExpr):
            _walk_expr(expr.obj)
        elif isinstance(expr, PipeExpr):
            _walk_expr(expr.left)
            _walk_expr(expr.right)
        elif isinstance(expr, MatchExpr):
            if expr.subject:
                _walk_expr(expr.subject)
            for arm in expr.arms:
                _walk_stmts(arm.body)
        elif isinstance(expr, IndexExpr):
            _walk_expr(expr.obj)
            _walk_expr(expr.index)
        elif isinstance(expr, LambdaExpr):
            _walk_expr(expr.body)
        elif isinstance(expr, FailPropExpr):
            _walk_expr(expr.expr)
        elif isinstance(expr, ValidExpr) and expr.args:
            for arg in expr.args:
                _walk_expr(arg)
        elif isinstance(expr, AsyncCallExpr):
            _walk_expr(expr.expr)
        elif isinstance(expr, ListLiteral):
            for e in expr.elements:
                _walk_expr(e)

    def _walk_stmts(stmts: list) -> None:
        for stmt in stmts:
            if isinstance(stmt, ExprStmt):
                _walk_expr(stmt.expr)
            elif isinstance(stmt, VarDecl) and stmt.value is not None:
                _walk_expr(stmt.value)
            elif isinstance(stmt, Assignment):
                _walk_expr(stmt.value)
            elif isinstance(stmt, MatchExpr):
                if stmt.subject:
                    _walk_expr(stmt.subject)
                for arm in stmt.arms:
                    _walk_stmts(arm.body)
            elif hasattr(stmt, "expr"):
                _walk_expr(stmt.expr)

    _walk_stmts(stmts)
    return targets


def _match_arms_have_fail_prop(match_expr: MatchExpr) -> bool:
    """Return True if any arm body contains a FailPropExpr (failable call).

    A match with failable calls cannot be extracted to a 'matches' verb
    (which must be pure), so I367 must not be suggested.
    """

    def _expr_has_fail(expr: Expr) -> bool:
        if isinstance(expr, FailPropExpr):
            return True
        if isinstance(expr, CallExpr):
            return any(_expr_has_fail(a) for a in expr.args)
        if isinstance(expr, BinaryExpr):
            return _expr_has_fail(expr.left) or _expr_has_fail(expr.right)
        if isinstance(expr, UnaryExpr):
            return _expr_has_fail(expr.operand)
        if isinstance(expr, PipeExpr):
            return _expr_has_fail(expr.left) or _expr_has_fail(expr.right)
        if isinstance(expr, LambdaExpr):
            return _expr_has_fail(expr.body)
        if isinstance(expr, AsyncCallExpr):
            return _expr_has_fail(expr.expr)
        return False

    def _stmt_has_fail(stmt: Stmt | MatchExpr) -> bool:
        if isinstance(stmt, ExprStmt):
            return _expr_has_fail(stmt.expr)
        if isinstance(stmt, VarDecl) and stmt.value is not None:
            return _expr_has_fail(stmt.value)
        if isinstance(stmt, Assignment):
            return _expr_has_fail(stmt.value)
        return False

    return any(_stmt_has_fail(stmt) for arm in match_expr.arms for stmt in arm.body)


class Checker(TypeCheckMixin, CallCheckMixin, ContractCheckMixin):
    """Semantic analyzer for a single module."""

    def __init__(
        self,
        local_modules: dict[str, object] | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self.symbols = SymbolTable()
        self.diagnostics: list[Diagnostic] = []
        self._current_function: FunctionDef | MainDef | None = None
        self._io_function_names: set[str] = set()
        self._attached_with_io: set[str] = set()
        # Track imports: module_name -> set of imported function names
        self._module_imports: dict[str, set[str]] = {}
        # Track which imports are actually used: (module_name, func_name)
        self._used_imports: set[tuple[str, str]] = set()
        # Track import spans for I302 reporting: (module, name) -> spans
        self._import_spans: dict[tuple[str, str], list[Span]] = {}
        # Track user-defined type names and their spans for W303
        self._user_types: dict[str, Span] = {}
        # Track which user-defined types are referenced
        self._used_types: set[str] = set()
        # Track user-defined constant names and their spans for I304
        self._user_constants: dict[str, Span] = {}
        # Requires-based narrowing: list of (module, args)
        self._requires_narrowings: list[tuple[str, list[Expr]]] = []
        # Inferred types for untyped VarDecl nodes: (start_line, start_col) -> type_name
        self.inlay_type_map: dict[tuple[int, int], str] = {}
        # Mutation survivors from previous --mutate runs
        self._survivors: list[dict] = []
        if project_dir:
            from prove.mutator import load_survivors

            self._survivors = load_survivors(project_dir)
        # Local (sibling) module info for cross-file imports
        self._local_modules = local_modules
        # Lookup tables per type name for TypeName: resolution
        self._lookup_tables: dict[str, LookupTypeDef] = {}
        # Store-backed lookup type names (runtime data, not compile-time)
        self._store_lookup_types: set[str] = set()
        STORE_BACKED_TYPES.clear()
        # Expected type context for bidirectional type inference (e.g. binary lookups)
        self._expected_type: Type | None = None
        # Ownership tracking: variables that have been moved (passed to Own parameters)
        self._moved_vars: set[str] = set()
        # Track scope depth for ownership - reset on function entry
        self._ownership_scope_stack: list[set[str]] = []
        # Track invariant network names for satisfies validation
        self._invariant_networks: set[str] = set()
        # Full invariant network definitions for constraint type-checking
        self._invariant_network_defs: dict[str, InvariantNetwork] = {}
        # Temporal ordering: list of step names from module temporal declaration
        self._temporal_order: list[str] = []
        # Coherence checking enabled (set via CLI --coherence flag)
        self._coherence: bool = False
        # Set when checking a stdlib module itself (skip E316 for builtins it provides)
        self._is_stdlib: bool = False
        # Flag: current expression is the direct callee of an AsyncCallExpr (&)
        self._inside_async_call: bool = False
        # Flag: inferring elements of a listens worker list (suppresses E372)
        self._in_listens_worker_list: bool = False
        # Flag: inside a HOF lambda body (emitter adds retains, suppress W360)
        self._inside_lambda: bool = False
        # Verification chain tracking: function_name -> "verified"/"trusted"/"unverified"
        self._verification_status: dict[str, str] = {}
        # Strict verification chain checking (--strict enables W371)
        self._strict: bool = False
        # Lambda capture tracking: id(LambdaExpr) -> list of captured var names
        self._lambda_captures: dict[int, list[str]] = {}
        # Current module name (set from ModuleDecl) for function signature tagging
        self._module_name: str | None = None
        # Match arm depth: >0 when checking statements inside a match arm body
        self._match_arm_depth: int = 0
        # Unique ID for the current match arm (incremented per arm)
        self._match_arm_id: int = 0

    # ── Public API ──────────────────────────────────────────────

    def check(self, module: Module) -> SymbolTable:
        """Run both passes on a module. Raises nothing; check self.diagnostics."""
        self._register_builtins()

        # Require a module declaration with narrative (skip for internal sources)
        source_name = module.span.file if module.span else ""
        if not source_name.startswith("<"):
            mod_decls = [d for d in module.declarations if isinstance(d, ModuleDecl)]
            if not mod_decls:
                self._info(
                    "I201",
                    "Prove requires a module declaration with narrative",
                    module.span,
                )
            elif mod_decls[0].narrative is None:
                self._info(
                    "I201",
                    "module declaration requires a narrative",
                    mod_decls[0].span,
                )

        # Pass 1: register all top-level declarations
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                self._register_function(decl)
            elif isinstance(decl, MainDef):
                self._register_main(decl)
            elif isinstance(decl, ModuleDecl):
                from prove.stdlib_loader import is_stdlib_module

                self._is_stdlib = is_stdlib_module(decl.name)
                if not self._is_stdlib and decl.name.lower() != "main":
                    self._module_name = decl.name.lower()
                for imp in decl.imports:
                    self._register_import(imp)
                for td in decl.types:
                    self._register_type(td)
                for cd in decl.constants:
                    self._register_constant(cd)
                for fb in decl.foreign_blocks:
                    self._register_foreign_block(fb)
                for inv in decl.invariants:
                    self._invariant_networks.add(inv.name)
                    self._invariant_network_defs[inv.name] = inv
                if decl.temporal:
                    self._temporal_order = list(decl.temporal)
                for item in decl.body:
                    if isinstance(item, FunctionDef):
                        self._register_function(item)
                    elif isinstance(item, MainDef):
                        self._register_main(item)

        # Collect user-defined IO function names (inputs/outputs verbs)
        for decl in module.declarations:
            if isinstance(decl, FunctionDef) and decl.verb in ("inputs", "outputs"):
                self._io_function_names.add(decl.name)

        # Collect attached functions whose bodies contain blocking IO calls
        for decl in module.declarations:
            if isinstance(decl, FunctionDef) and decl.verb == "attached":
                if self._body_has_blocking_calls(decl.body):
                    self._attached_with_io.add(decl.name)
            elif isinstance(decl, ModuleDecl):
                for item in decl.body:
                    if isinstance(item, FunctionDef) and item.verb == "attached":
                        if self._body_has_blocking_calls(item.body):
                            self._attached_with_io.add(item.name)

        # Pass 2: check bodies
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                self._check_function(decl)
            elif isinstance(decl, MainDef):
                self._check_main(decl)
            elif isinstance(decl, ModuleDecl):
                for cd in decl.constants:
                    self._check_constant(cd)
                for td in decl.types:
                    self._check_type_def(td)
                for item in decl.body:
                    if isinstance(item, FunctionDef):
                        self._check_function(item)
                    elif isinstance(item, MainDef):
                        self._check_main(item)

        # Check unused variables (W300)
        self._check_unused()

        # Check unused imports (W302)
        self._check_unused_imports()

        # Check unused type definitions (W303)
        self._check_unused_types()

        # Check unused constants (I304)
        self._check_unused_constants()

        # Domain profile enforcement (W340-W342)
        self._check_domain_profiles(module)

        # Verification chain analysis (W370-W371)
        self._check_verification_chains(module)

        # Coherence checking (I340-I341)
        if self._coherence:
            self._check_coherence(module)

        return self.symbols

    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)

    # ── Error helpers ───────────────────────────────────────────

    @staticmethod
    def _fuzzy_match(name: str, candidates: set[str], max_dist: int = 2) -> str | None:
        """Find the closest match for *name* among *candidates*."""
        best: str | None = None
        best_dist = max_dist + 1
        for c in candidates:
            d = _edit_distance(name, c)
            if d < best_dist:
                best_dist = d
                best = c
        return best if best_dist <= max_dist else None

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code=code,
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
            )
        )

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code=code,
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
            )
        )

    def _info(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.NOTE,
                code=code,
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
            )
        )

    @staticmethod
    def _is_value_coercion(inferred: Type, expected: Type) -> bool:
        """Check if this is a Value → concrete type coercion."""
        is_value = (isinstance(inferred, TypeVariable) and inferred.name == "Value") or (
            isinstance(inferred, PrimitiveType) and inferred.name == "Value"
        )
        if not is_value:
            return False
        # Target must be a concrete container or primitive, not Value itself
        if isinstance(expected, TypeVariable) and expected.name == "Value":
            return False
        if isinstance(expected, PrimitiveType) and expected.name == "Value":
            return False
        if isinstance(expected, (GenericInstance, ListType, PrimitiveType)):
            return True
        return False

    # ── Pass 1: Registration ────────────────────────────────────

    def _register_builtins(self) -> None:
        """Register built-in types and functions."""
        # Built-in primitive types
        for name, ty in BUILTINS.items():
            self.symbols.define_type(name, ty)

        # Generic constructors
        self.symbols.define_type(
            "Result",
            GenericInstance(
                "Result",
                [TypeVariable("Value"), TypeVariable("Error")],
            ),
        )
        self.symbols.define_type(
            "Option",
            GenericInstance(
                "Option",
                [TypeVariable("Value")],
            ),
        )
        self.symbols.define_type("List", ListType(TypeVariable("Value")))
        self.symbols.define_type(
            "Table",
            GenericInstance(
                "Table",
                [TypeVariable("Value")],
            ),
        )
        self.symbols.define_type("Error", PrimitiveType("Error"))
        self.symbols.define_type("Value", TypeVariable("Value"))
        self.symbols.define_type("Source", TypeVariable("Source"))
        self.symbols.define_type("Verb", PrimitiveType("Verb"))
        self.symbols.define_type("Attached", PrimitiveType("Attached"))
        self.symbols.define_type("Listens", PrimitiveType("Listens"))

        _dummy = Span("<builtin>", 0, 0, 0, 0)

        # Common built-in functions
        # Builtins that accept additional types beyond their signature.
        # Maps (func_name, param_index) → frozenset of extra types.
        self._builtin_extra_types: dict[tuple[str, int], frozenset[Type]] = {
            ("len", 0): frozenset({STRING}),
        }

        builtins = [
            ("len", [ListType(TypeVariable("Value"))], INTEGER),
            (
                "map",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], TypeVariable("Output")),
                ],
                ListType(TypeVariable("Output")),
            ),
            (
                "each",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], TypeVariable("Output")),
                ],
                UNIT,
            ),
            (
                "filter",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], BOOLEAN),
                ],
                ListType(TypeVariable("Value")),
            ),
            (
                "reduce",
                [
                    ListType(TypeVariable("Value")),
                    TypeVariable("Output"),
                    FunctionType(
                        [TypeVariable("Output"), TypeVariable("Value")],
                        TypeVariable("Output"),
                    ),
                ],
                TypeVariable("Output"),
            ),
            # Parallel HOFs: same signatures as sequential counterparts
            (
                "par_map",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], TypeVariable("Output")),
                ],
                ListType(TypeVariable("Output")),
            ),
            (
                "par_filter",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], BOOLEAN),
                ],
                ListType(TypeVariable("Value")),
            ),
            (
                "par_reduce",
                [
                    ListType(TypeVariable("Value")),
                    TypeVariable("Output"),
                    FunctionType(
                        [TypeVariable("Output"), TypeVariable("Value")],
                        TypeVariable("Output"),
                    ),
                ],
                TypeVariable("Output"),
            ),
            (
                "par_each",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], TypeVariable("Output")),
                ],
                UNIT,
            ),
            ("to_string", [TypeVariable("Value")], STRING),
            ("clamp", [INTEGER, INTEGER, INTEGER], INTEGER),
        ]
        for name, param_types, return_type in builtins:
            sig = FunctionSignature(
                verb=None,
                name=name,
                param_names=[f"p{i}" for i in range(len(param_types))],
                param_types=param_types,
                return_type=return_type,
                can_fail=False,
                span=_dummy,
                requires=[],
            )
            self.symbols.define_function(sig)

    def _register_type(self, td: TypeDef) -> None:
        """Register a user-defined type."""
        # E317: type name shadows builtin type (but allow Table for module<>type collision)
        if td.name in _BUILTIN_TYPE_NAMES:
            self._error(
                "E317",
                f"'{td.name}' conflicts with the built-in type '{td.name}'. "
                f"Choose a different name.",
                td.span,
            )
            return
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
            # Check if first variant is actually a base algebraic type (inheritance)
            inherited_variants: list[VariantInfo] = []
            own_variants_start = 0
            if body.variants:
                first_v = body.variants[0]
                if not first_v.fields:
                    base_type = self.symbols.resolve_type(first_v.name)
                    # Type must be explicitly imported — no auto-resolve.
                    # Search stdlib modules to give a helpful error message.
                    if base_type is None:
                        from prove.stdlib_loader import (
                            _STDLIB_MODULES,
                            load_stdlib_types,
                        )

                        for mod_name in _STDLIB_MODULES:
                            stdlib_types = load_stdlib_types(mod_name)
                            if first_v.name in stdlib_types:
                                hint = (
                                    f" (add `types {first_v.name}` to your "
                                    f"{mod_name.capitalize()} import)"
                                    if mod_name.lower() in {k.lower() for k in self._module_imports}
                                    else f" (available from module '{mod_name}')"
                                )
                                self._error(
                                    "E300",
                                    f"undefined type `{first_v.name}`{hint}",
                                    first_v.span,
                                )
                                break
                    if isinstance(base_type, AlgebraicType):
                        inherited_variants = list(base_type.variants)
                        own_variants_start = 1
                        self._used_types.add(first_v.name)
            variants.extend(inherited_variants)
            for v in body.variants[own_variants_start:]:
                vfields: dict[str, Type] = {}
                for f in v.fields:
                    vfields[f.name] = self._resolve_type_expr(f.type_expr)
                variants.append(VariantInfo(v.name, vfields))
            resolved = AlgebraicType(td.name, variants, type_params)
            # Register each variant as a constructor function
            # (both inherited and own variants)
            for vi in variants:
                vsig = FunctionSignature(
                    verb=None,
                    name=vi.name,
                    param_names=list(vi.fields.keys()),
                    param_types=list(vi.fields.values()),
                    return_type=resolved,
                    can_fail=False,
                    span=td.span,
                    requires=[],
                )
                self.symbols.define_function(vsig)

        elif isinstance(body, RefinementTypeDef):
            base = self._resolve_type_expr(body.base_type)
            resolved = RefinementType(td.name, base, body.constraint)

        elif isinstance(body, BinaryDef):
            # E397: `binary` type body is reserved for stdlib type definitions
            if not self._is_stdlib:
                self._error(
                    "E397",
                    "`binary` is reserved for stdlib type definitions",
                    td.span,
                )
            # Binary types are opaque C-backed types — no fields visible to Prove
            resolved = PrimitiveType(td.name)

        elif isinstance(body, LookupTypeDef):
            if body.is_store_backed:
                # Store-backed lookup: zero variants (dynamic), register schema
                resolved = AlgebraicType(td.name, [], type_params)
                self._lookup_tables[td.name] = body
                self._store_lookup_types.add(td.name)
                STORE_BACKED_TYPES.add(td.name)
                # Validate column types
                if body.is_binary:
                    self._validate_binary_lookup(body, td.span)
            else:
                # Static lookup types: build AlgebraicType from entries
                seen_variants: dict[str, None] = {}
                for entry in body.entries:
                    seen_variants[entry.variant] = None
                variant_names = list(seen_variants.keys())
                variants = [VariantInfo(name, {}) for name in variant_names]
                resolved = AlgebraicType(td.name, variants, type_params)
                # Store lookup table for accessor resolution
                self._lookup_tables[td.name] = body
                # Register each variant as a zero-arg constructor
                for name in variant_names:
                    vsig = FunctionSignature(
                        verb=None,
                        name=name,
                        param_names=[],
                        param_types=[],
                        return_type=resolved,
                        can_fail=False,
                        span=td.span,
                    )
                    self.symbols.define_function(vsig)

                if body.is_binary:
                    # Validate binary lookup table
                    self._validate_binary_lookup(body, td.span)
                else:
                    # Validate: check for duplicate values (E375)
                    seen_values: set[str] = set()
                    for entry in body.entries:
                        if entry.value in seen_values:
                            self._error(
                                "E375",
                                f"duplicate value '{entry.value}' in lookup table",
                                entry.span,
                            )
                        seen_values.add(entry.value)

        else:
            resolved = ERROR_TY

        self.symbols.define_type(td.name, resolved)
        self._user_types[td.name] = td.span
        # Also register in scope as a type symbol
        self.symbols.define(
            Symbol(
                name=td.name,
                kind=SymbolKind.TYPE,
                resolved_type=resolved,
                span=td.span,
            )
        )

    def _register_function(self, fd: FunctionDef) -> None:
        """Register a function signature."""
        param_types = [self._resolve_type_expr(p.type_expr) for p in fd.params]
        # E316: function name shadows builtin (only if param types also match —
        # overloads with different types are allowed; stdlib modules are exempt)
        if fd.name in _BUILTIN_FUNCTIONS and not self._is_stdlib:
            builtin_sig = self.symbols.resolve_function(None, fd.name, len(param_types))
            if builtin_sig is not None and all(
                types_compatible(a, b) for a, b in zip(builtin_sig.param_types, param_types)
            ):
                self._error(
                    "E316",
                    f"'{fd.name}' shadows the built-in function '{fd.name}'. Choose a different name.",  # noqa: E501
                    fd.span,
                )
        return_type = self._resolve_type_expr(fd.return_type) if fd.return_type else UNIT
        # validates always returns Boolean — override implicit Unit
        if fd.verb == "validates" and not fd.return_type:
            return_type = BOOLEAN
        resolved_event_type = self._resolve_type_expr(fd.event_type) if fd.event_type else None
        sig = FunctionSignature(
            verb=fd.verb,
            name=fd.name,
            param_names=[p.name for p in fd.params],
            param_types=param_types,
            return_type=return_type,
            can_fail=fd.can_fail,
            span=fd.span,
            module=self._module_name,
            requires=fd.requires,
            doc_comment=fd.doc_comment,
            event_type=resolved_event_type,
            ensures=fd.ensures,
        )
        # E301: duplicate function definition (exact same verb + name + param types)
        existing = self.symbols.find_exact_duplicate(sig)
        if existing is not None:
            param_str = ", ".join(type_name(t) for t in param_types)
            self._error(
                "E301",
                f"duplicate function definition: '{fd.verb} {fd.name}({param_str})' "
                f"already defined at line {existing.span.start_line}",
                fd.span,
            )
            return
        self.symbols.define_function(sig)
        self.symbols.define(
            Symbol(
                name=fd.name,
                kind=SymbolKind.FUNCTION,
                resolved_type=FunctionType(param_types, return_type),
                span=fd.span,
                verb=fd.verb,
            )
        )

    def _register_main(self, md: MainDef) -> None:
        """Register the main function."""
        return_type = self._resolve_type_expr(md.return_type) if md.return_type else UNIT
        sig = FunctionSignature(
            verb=None,
            name="main",
            param_names=[],
            param_types=[],
            return_type=return_type,
            can_fail=md.can_fail,
            span=md.span,
        )
        self.symbols.define_function(sig)

    def _register_constant(self, cd: ConstantDef) -> None:
        """Register a constant."""
        resolved = self._resolve_type_expr(cd.type_expr) if cd.type_expr else ERROR_TY
        existing = self.symbols.define(
            Symbol(
                name=cd.name,
                kind=SymbolKind.CONSTANT,
                resolved_type=resolved,
                span=cd.span,
            )
        )
        if existing is not None:
            self._error("E301", f"duplicate definition of '{cd.name}'", cd.span)
        if not self._is_stdlib:
            self._user_constants[cd.name] = cd.span

    def _register_foreign_block(self, fb: ForeignBlock) -> None:
        """Register foreign (C FFI) functions in the symbol table."""
        for ff in fb.functions:
            param_types: list[Type] = []
            param_names: list[str] = []
            for p in ff.params:
                param_names.append(p.name)
                param_types.append(self._resolve_type_expr(p.type_expr))

            ret_type: Type = UNIT
            if ff.return_type is not None:
                ret_type = self._resolve_type_expr(ff.return_type)

            sig = FunctionSignature(
                verb=None,
                name=ff.name,
                param_names=param_names,
                param_types=param_types,
                return_type=ret_type,
                can_fail=False,
                span=ff.span,
                module=None,
            )
            self.symbols.define_function(sig)

    def _register_import(self, imp: ImportDecl) -> None:
        """Register imported names, loading from stdlib if available."""
        from prove.stdlib_loader import is_stdlib_module, load_stdlib, load_stdlib_types

        # .ModuleName prefix forces local-only resolution
        if getattr(imp, "local", False):
            if self._local_modules and imp.module in self._local_modules:
                self._register_local_import(imp)
            else:
                self._module_imports.setdefault(imp.module, set())
                self._info(
                    "I314",
                    f"unknown local module '{imp.module}'",
                    imp.span,
                )
            return

        # Try loading real signatures from stdlib
        is_known = is_stdlib_module(imp.module)
        if not is_known:
            # Check local (sibling) modules before giving up
            if self._local_modules and imp.module in self._local_modules:
                self._register_local_import(imp)
                return
            # Register the module name so we know it was declared,
            # but don't add function names — call sites will flag them.
            self._module_imports.setdefault(imp.module, set())
            self._info(
                "I314",
                f"unknown module '{imp.module}'",
                imp.span,
            )
            return

        # Ambiguity check: local module shadows stdlib module
        if self._local_modules and imp.module in self._local_modules:
            self._error(
                "E316",
                f"module '{imp.module}' is ambiguous: a local module and a stdlib module share "
                f"this name. Use '.{imp.module}' to import the local module.",
                imp.span,
            )
            return

        # Track which functions are imported from this known module
        names = self._module_imports.setdefault(imp.module, set())
        for item in imp.items:
            names.add(item.name)
            self._import_spans.setdefault(
                (imp.module.lower(), item.name),
                [],
            ).append(item.span)

        stdlib_sigs = load_stdlib(imp.module)
        # Index by name → all overloads (different verbs)
        stdlib_all_by_name: dict[str, list[FunctionSignature]] = {}
        for s in stdlib_sigs:
            stdlib_all_by_name.setdefault(s.name, []).append(s)

        # Load constants for constant-import detection
        from prove.stdlib_loader import load_stdlib_constants

        stdlib_consts = load_stdlib_constants(imp.module)
        stdlib_consts_by_name = {c.name: c for c in stdlib_consts}

        for item in imp.items:
            # Constant imports (explicit 'constants' verb or ALL_CAPS names)
            is_const_name = item.verb == "constants" or (
                len(item.name) >= 2
                and all(c.isupper() or c.isdigit() or c == "_" for c in item.name)
            )
            if is_const_name:
                const = stdlib_consts_by_name.get(item.name)
                if const is not None:
                    resolved = PrimitiveType(const.type_name)
                    self.symbols.define(
                        Symbol(
                            name=item.name,
                            kind=SymbolKind.CONSTANT,
                            resolved_type=resolved,
                            span=item.span,
                            is_imported=True,
                        )
                    )
                else:
                    self._error(
                        "E315",
                        f"constant '{item.name}' not found in module '{imp.module}'",
                        item.span,
                    )
                continue

            # Type imports (verb="types" or bare CamelCase with no verb)
            is_type_import = item.verb == "types" or (item.verb is None and item.name[:1].isupper())
            if is_type_import:
                # Try to load rich type definition from stdlib
                stdlib_types = load_stdlib_types(imp.module)
                resolved: Type = stdlib_types.get(item.name, PrimitiveType(item.name))
                self.symbols.define(
                    Symbol(
                        name=item.name,
                        kind=SymbolKind.TYPE,
                        resolved_type=resolved,
                        span=item.span,
                        verb=item.verb,
                        is_imported=True,
                    )
                )
                self.symbols.define_type(item.name, resolved)
                # Register variant constructors for algebraic types
                if isinstance(resolved, AlgebraicType):
                    for vi in resolved.variants:
                        vsig = FunctionSignature(
                            verb=None,
                            name=vi.name,
                            param_names=list(vi.fields.keys()),
                            param_types=list(vi.fields.values()),
                            return_type=resolved,
                            can_fail=False,
                            span=item.span,
                            requires=[],
                        )
                        self.symbols.define_function(vsig)
                continue

            # Register ALL verb overloads of the function so channel
            # dispatch (same name, different verbs) works at call sites.
            sigs_to_register = stdlib_all_by_name.get(
                item.name,
                [],
            )
            if sigs_to_register:
                # Warn if the import specifies a verb that doesn't
                # match any available signature for this function.
                if item.verb and item.verb != "types":
                    verbs = {s.verb for s in sigs_to_register}
                    if item.verb not in verbs:
                        self._warning(
                            "W312",
                            f"'{imp.module}' has no '{item.verb} {item.name}'; "
                            f"available: {', '.join(sorted(v for v in verbs if v))}",
                            item.span,
                        )
                for sig in sigs_to_register:
                    ret = sig.return_type
                    ft = FunctionType(sig.param_types, ret)
                    self.symbols.define(
                        Symbol(
                            name=item.name,
                            kind=SymbolKind.FUNCTION,
                            resolved_type=ft,
                            span=item.span,
                            verb=sig.verb,
                            is_imported=True,
                        )
                    )
                    self.symbols.define_function(sig)
            else:
                # Known stdlib module but function not found — error
                self._error(
                    "E315",
                    f"function '{item.name}' not found in module '{imp.module}'",
                    item.span,
                )

    def _register_local_import(self, imp: ImportDecl) -> None:
        """Register imports from a local (sibling) module."""
        local_info = self._local_modules[imp.module]  # type: ignore[index]

        names = self._module_imports.setdefault(imp.module, set())
        for item in imp.items:
            names.add(item.name)
            self._import_spans.setdefault(
                (imp.module.lower(), item.name),
                [],
            ).append(item.span)

        for item in imp.items:
            # Constant imports (explicit 'constants' verb or ALL_CAPS names)
            is_const_import = item.verb == "constants" or (
                item.verb is None
                and len(item.name) >= 2
                and all(c.isupper() or c.isdigit() or c == "_" for c in item.name)
            )
            if is_const_import:
                if hasattr(local_info, "constants") and item.name in local_info.constants:
                    resolved = PrimitiveType("String")
                    self.symbols.define(
                        Symbol(
                            name=item.name,
                            kind=SymbolKind.CONSTANT,
                            resolved_type=resolved,
                            span=item.span,
                            is_imported=True,
                        )
                    )
                else:
                    self._error(
                        "E315",
                        f"constant '{item.name}' not found in module '{imp.module}'",
                        item.span,
                    )
                continue

            # Type imports (verb="types" or bare CamelCase with no verb)
            is_type_import = item.verb == "types" or (item.verb is None and item.name[:1].isupper())
            if is_type_import:
                resolved = local_info.types.get(item.name)
                if resolved is not None:
                    self.symbols.define_type(item.name, resolved)
                    self.symbols.define(
                        Symbol(
                            name=item.name,
                            kind=SymbolKind.TYPE,
                            resolved_type=resolved,
                            span=item.span,
                            verb=item.verb,
                            is_imported=True,
                        )
                    )
                    # Register variant constructors for algebraic types
                    if isinstance(resolved, AlgebraicType):
                        for vsig in local_info.functions:
                            if vsig.verb is None and any(
                                v.name == vsig.name for v in resolved.variants
                            ):
                                self.symbols.define_function(vsig)
                else:
                    self._error(
                        "E315",
                        f"type '{item.name}' not found in module '{imp.module}'",
                        item.span,
                    )
                continue

            # Function imports — register all verb overloads
            found = False
            for sig in local_info.functions:
                if sig.name == item.name:
                    found = True
                    ft = FunctionType(sig.param_types, sig.return_type)
                    self.symbols.define(
                        Symbol(
                            name=item.name,
                            kind=SymbolKind.FUNCTION,
                            resolved_type=ft,
                            span=item.span,
                            verb=sig.verb,
                            is_imported=True,
                        )
                    )
                    self.symbols.define_function(sig)

            if not found:
                self._error(
                    "E315",
                    f"function '{item.name}' not found in module '{imp.module}'",
                    item.span,
                )

    def _is_module_imported(self, module_name: str) -> bool:
        """Check if a module has any imports."""
        return module_name in self._module_imports

    def _is_function_imported(self, module_name: str, func_name: str) -> bool:
        """Check if a specific function is imported from a module."""
        names = self._module_imports.get(module_name)
        return names is not None and func_name in names

    @staticmethod
    def _has_implicit_value_coercion(
        expected: Type,
        actual: Type,
    ) -> bool:
        """Detect when Value (TypeVariable) silently satisfies a concrete type.

        Returns True when ``actual`` is bare Value where ``expected`` is
        concrete, or when a Table<Value> is used where Table<String> etc.
        is declared.  Skips List<Value> since that commonly arises from
        HOF type inference (filter/map/reduce) rather than Parse.
        """
        # Bare Value → concrete type (e.g. requires-narrowed Result<Value>)
        if isinstance(actual, TypeVariable) and actual.name == "Value":
            if isinstance(expected, TypeVariable) and expected.name == "Value":
                return False
            if isinstance(expected, PrimitiveType) and expected.name == "Value":
                return False
            return True
        # Table<Value> → Table<String> (Parse table mismatch)
        if (
            isinstance(expected, GenericInstance)
            and isinstance(actual, GenericInstance)
            and expected.base_name == actual.base_name
            and expected.base_name == "Table"
            and len(expected.args) == len(actual.args)
        ):
            return any(
                Checker._has_implicit_value_coercion(e, a)
                for e, a in zip(expected.args, actual.args)
            )
        return False

    # ── Pass 2: Checking ────────────────────────────────────────

    def _check_function(self, fd: FunctionDef) -> None:
        """Check a function body."""
        self._current_function = fd
        self._is_recursive = False
        self._inside_async_call = False
        self.symbols.push_scope(fd.name)
        # Reset ownership tracking for this function
        self._moved_vars.clear()
        self._ownership_scope_stack.clear()
        self._ownership_scope_stack.append(set())

        # Register parameters
        param_types = [self._resolve_type_expr(p.type_expr) for p in fd.params]

        # Infer borrows only for parameters without explicit ownership modifiers
        # Skip for verbs that need ownership of their parameters
        if fd.verb not in _VERBS_NEED_OWNERSHIP:
            param_has_explicit_modifier = [
                isinstance(p.type_expr, ModifiedType) and bool(p.type_expr.modifiers)
                for p in fd.params
            ]
            # Only infer borrows for params without explicit modifiers
            eligible_params = [
                p for p, has_mod in zip(fd.params, param_has_explicit_modifier) if not has_mod
            ]
            eligible_types = [
                ty for ty, has_mod in zip(param_types, param_has_explicit_modifier) if not has_mod
            ]
            if eligible_params:
                borrowed_params = self._infer_param_borrows(
                    eligible_params, eligible_types, fd.body
                )
                for i, p in enumerate(fd.params):
                    if p.name in borrowed_params:
                        param_types[i] = borrowed_params[p.name]

        # Narrow Struct-typed parameters using `with` constraints
        if fd.with_constraints:
            param_index = {p.name: i for i, p in enumerate(fd.params)}
            fields_by_param: dict[str, dict[str, Type]] = {}
            for wc in fd.with_constraints:
                if wc.param_name not in param_index:
                    continue  # validated in _check_contracts
                if not isinstance(param_types[param_index[wc.param_name]], StructType):
                    continue  # validated in _check_contracts
                fields = fields_by_param.setdefault(wc.param_name, {})
                fields[wc.field_name] = self._resolve_type_expr(wc.field_type)
            for pname, fields in fields_by_param.items():
                idx = param_index[pname]
                param_types[idx] = StructType(fields)

        for param, pty in zip(fd.params, param_types):
            # E316: parameter name shadows builtin function
            if param.name in _BUILTIN_FUNCTIONS:
                self._error(
                    "E316",
                    f"'{param.name}' shadows the built-in function "
                    f"'{param.name}'. Choose a different name.",
                    param.span,
                )
            self.symbols.define(
                Symbol(
                    name=param.name,
                    kind=SymbolKind.PARAMETER,
                    resolved_type=pty,
                    span=param.span,
                )
            )

        # Collect requires-based option narrowings
        self._requires_narrowings = self._collect_requires_narrowings(fd)

        # Narrow parameter types based on requires valid clauses
        for _mod, req_args in self._requires_narrowings:
            for arg in req_args:
                if isinstance(arg, IdentifierExpr):
                    sym = self.symbols.lookup(arg.name)
                    if (
                        sym is not None
                        and isinstance(sym.resolved_type, GenericInstance)
                        and sym.resolved_type.base_name in ("Result", "Option")
                        and sym.resolved_type.args
                    ):
                        sym.resolved_type = sym.resolved_type.args[0]

        # Bind implicit variables for renders/listens verbs
        # These are marked as used since they're consumed by the runtime dispatch
        if fd.verb in ("renders", "listens") and fd.event_type is not None:
            evt_type = self._resolve_type_expr(fd.event_type)
            if evt_type is not None:
                ev_sym = Symbol(
                    name="event",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=evt_type,
                    span=fd.span,
                )
                ev_sym.used = True
                self.symbols.define(ev_sym)
        if fd.verb == "renders" and fd.state_init is not None:
            state_type = self._infer_expr(fd.state_init)
            if state_type is not None:
                st_sym = Symbol(
                    name="state",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=state_type,
                    span=fd.span,
                )
                st_sym.used = True
                self.symbols.define(st_sym)
        if fd.verb == "listens" and fd.state_type is not None:
            st = self._resolve_type_expr(fd.state_type)
            if st is not None:
                st_sym = Symbol(
                    name="state",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=st,
                    span=fd.span,
                )
                st_sym.used = True
                self.symbols.define(st_sym)

        # Check verb rules
        self._check_verb_rules(fd)

        # E397: `binary` body marker is reserved for stdlib implementations
        if fd.binary and not self._is_stdlib:
            self._error(
                "E397",
                "`binary` is reserved for stdlib implementations",
                fd.span,
            )

        # Binary functions have no Prove body — skip body and return checks
        if fd.binary:
            self.symbols.pop_scope()
            self._current_function = None
            return

        # Check body
        has_todo = any(isinstance(s, TodoStmt) for s in fd.body)
        body_type = UNIT
        for i, stmt in enumerate(fd.body):
            # W332: warn on unused pure function result (except for last statement)
            if i < len(fd.body) - 1:
                self._check_unused_pure_result(stmt)
            body_type = self._check_stmt(stmt)  # type: ignore[assignment]

        # I601: function has incomplete implementation (todo)
        if has_todo:
            self._info(
                "I601",
                f"function '{fd.name}' has incomplete implementation (todo)",
                fd.span,
            )

        # Track return-position move: if the last expression is an Own-typed
        # identifier, mark it as moved (consumed by the return). This closes
        # the tracking gap where returning an owned variable wasn't recorded.
        # Only handles simple identifiers to avoid false positives on field
        # accesses and complex expressions.
        if fd.body and not isinstance(fd.body[-1], VarDecl):
            last_stmt = fd.body[-1]
            ret_expr = last_stmt.expr if isinstance(last_stmt, ExprStmt) else None
            if isinstance(ret_expr, IdentifierExpr):
                ret_sym = self.symbols.lookup(ret_expr.name)
                if ret_sym is not None and has_own_modifier(ret_sym.resolved_type):
                    self._moved_vars.add(ret_expr.name)

        # Validate return type
        return_type = self._resolve_type_expr(fd.return_type) if fd.return_type else UNIT
        if fd.verb == "validates":
            # validates has implicit Boolean return
            if fd.return_type is not None:
                self.diagnostics.append(
                    Diagnostic(
                        severity=Severity.NOTE,
                        code="I360",
                        message="validates has implicit Boolean return",
                        labels=[DiagnosticLabel(span=fd.span, message="")],
                        suggestions=[
                            Suggestion(
                                message="remove the return type annotation",
                                replacement=f"validates {fd.name}(...)",
                            )
                        ],
                    )
                )
        elif (
            fd.verb not in ("renders", "listens")
            and not isinstance(body_type, ErrorType)
            and not types_compatible(return_type, body_type)
        ):
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

        # Check for implicit Value → concrete coercion:
        # types_compatible passes because Value is a TypeVariable,
        # but the user needs explicit conversion (e.g. Parse.text()).
        if (
            fd.verb != "validates"
            and not isinstance(body_type, ErrorType)
            and not isinstance(return_type, ErrorType)
            and self._has_implicit_value_coercion(return_type, body_type)
        ):
            self._error(
                "E395",
                f"implicit Value conversion: body returns "
                f"'{type_name(body_type)}' but function declares "
                f"'{type_name(return_type)}'; "
                f"use Parse accessors to extract the concrete type",
                fd.span,
            )

        # ── Contract type-checking ──
        self._check_contracts(fd, return_type, param_types)

        # ── Intent prose check ──
        if fd.intent:
            self._check_intent_prose(fd)

        # ── Counterfactual annotation checks (always active) ──
        if fd.chosen or fd.why_not:
            self._check_chosen_has_why_not(fd)
            self._check_chosen_body_coherence(fd)
            self._check_why_not_names(fd, self.symbols.all_known_names())
            self._check_why_not_contradiction(fd)

        # ── Explain condition type-checking ──
        if fd.explain is not None:
            for entry in fd.explain.entries:
                if entry.condition is not None:
                    cond_type = self._infer_expr(entry.condition)
                    if not isinstance(cond_type, ErrorType) and not types_compatible(
                        BOOLEAN, cond_type
                    ):
                        self._error(
                            "E394",
                            f"explain condition must be Boolean, got '{type_name(cond_type)}'",
                            entry.condition.span,
                        )

        # ── Recursion checks (verb-aware, using resolved signatures) ──
        if self._is_recursive:
            if fd.terminates is None and fd.trusted is None:
                self._error(
                    "E366",
                    f"recursive function '{fd.name}' missing terminates",
                    fd.span,
                )

        # ── Explain verification ──
        verifier = ProofVerifier()
        verifier.verify(fd)
        self.diagnostics.extend(verifier.diagnostics)

        # ── Mutation testing recommendation ──
        # Flag functions with >1 statement but no contracts
        # Also flag transforms/matches (even with 1 statement, complex logic needs contracts)
        # Skip inputs without arguments - nothing meaningful to mutate
        is_inputs_no_args = fd.verb == "inputs" and not fd.params
        body_len = len(fd.body)
        no_contracts = not fd.requires and not fd.ensures
        is_trusted = fd.trusted is not None
        if body_len > 5 and no_contracts and not is_inputs_no_args and not is_trusted:
            self._info(
                "I320",
                f"Function '{fd.name}' has {body_len} statements but no contracts. "
                "Consider adding requires/ensures for mutation testing.",
                fd.span,
            )
        elif (
            body_len > 1
            and fd.verb in ("transforms", "matches")
            and no_contracts
            and not is_trusted
        ):
            self._info(
                "I320",
                f"Function '{fd.name}' ({fd.verb}) has {body_len} statements but no contracts. "
                "Consider adding requires/ensures for mutation testing.",
                fd.span,
            )

        # Check if this function had surviving mutants in previous mutation testing
        for survivor in self._survivors:
            loc = survivor.get("location", "")
            if loc and ":" in loc:
                parts = loc.split(":")
                try:
                    line_num = int(parts[0])
                    col_num = int(parts[1]) if len(parts) > 1 else 0
                    # Check if survivor location falls within function span
                    in_line_range = fd.span.start_line <= line_num <= fd.span.end_line
                    in_col_range = (
                        fd.span.start_col <= col_num <= fd.span.end_col
                        if line_num == fd.span.start_line
                        else True
                    )
                    if in_line_range and in_col_range:
                        self._warning(
                            "W330",
                            f"Function '{fd.name}' had a surviving mutant: {survivor.get('description', 'unknown')}. "  # noqa: E501
                            "Add contracts to catch this mutation.",
                            fd.span,
                        )
                except (ValueError, IndexError):
                    pass

        # Track verification status for chain analysis
        if fd.trusted is not None:
            self._verification_status[fd.name] = "trusted"
        elif fd.ensures:
            self._verification_status[fd.name] = "verified"
        else:
            self._verification_status[fd.name] = "unverified"

        # W300: warn about unused local variables
        # I301: variable initialized outside its used scope
        for sym in self.symbols.current_scope.all_symbols():
            if sym.kind == SymbolKind.VARIABLE and not sym.name.startswith("_"):
                if not sym.used:
                    self._warning("W300", f"unused variable '{sym.name}'", sym.span)
                elif sym.used and not sym.used_outside_match and len(sym.match_arm_ids) == 1:
                    self._info(
                        "I305",
                        f"'{sym.name}' is initialized at function scope but "
                        f"only used inside a single match arm; consider "
                        f"moving it into the arm where it is used",
                        sym.span,
                    )

        self.symbols.pop_scope()
        self._current_function = None
        self._requires_narrowings = []

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
            # Static refinement check for constants
            self._static_check_refinement(expected, cd.value, cd.span)

    def _validate_binary_lookup(self, body: LookupTypeDef, span: Span) -> None:
        """Validate a binary lookup table (E379, E387, W350)."""
        if span.file.startswith("<stdlib:"):
            return  # Skip validation for stdlib types
        num_columns = len(body.value_types)
        _ALLOWED_BINARY_TYPES = {"String", "Integer", "Decimal", "Float", "Boolean", "Verb"}
        for vt in body.value_types:
            tname = vt.name if hasattr(vt, "name") else str(vt)
            if tname not in _ALLOWED_BINARY_TYPES:
                self._error(
                    "E387",
                    f"unsupported type '{tname}' in lookup column "
                    f"(allowed: {', '.join(sorted(_ALLOWED_BINARY_TYPES))})",
                    span,
                )
        for entry in body.entries:
            if len(entry.values) != num_columns:
                self._error(
                    "E379",
                    f"entry '{entry.variant}' has {len(entry.values)} values "
                    f"but binary table has {num_columns} columns",
                    entry.span,
                )
        # W350: warn when duplicate column types exist without named columns
        type_names = [vt.name if hasattr(vt, "name") else str(vt) for vt in body.value_types]
        seen: dict[str, int] = {}
        for tn in type_names:
            seen[tn] = seen.get(tn, 0) + 1
        all_unnamed = not body.column_names or all(n is None for n in body.column_names)
        if all_unnamed:
            for tn, count in seen.items():
                if count > 1:
                    self._warning(
                        "W350",
                        f"lookup has duplicate column type '{tn}'; "
                        f"use named columns to disambiguate (e.g. name:{tn})",
                        span,
                    )

    def _check_type_def(self, td: TypeDef) -> None:
        """Validate field types and where constraints."""
        body = td.body
        if isinstance(body, RecordTypeDef):
            for f in body.fields:
                ft = self._resolve_type_expr(f.type_expr)
                if isinstance(ft, UnitType):
                    self._error(
                        "E435",
                        f"field '{f.name}' has type Unit, which has no "
                        f"runtime representation and cannot be used as "
                        f"a struct field",
                        f.span,
                    )
                if f.constraint is not None:
                    self._check_where_constraint(f.constraint)
        elif isinstance(body, AlgebraicTypeDef):
            for v in body.variants:
                for f in v.fields:
                    self._resolve_type_expr(f.type_expr)
                    if f.constraint is not None:
                        self._check_where_constraint(f.constraint)
        elif isinstance(body, RefinementTypeDef):
            self._check_where_constraint(body.constraint)

    def _check_where_constraint(self, expr: Expr) -> None:
        """Validate that a where constraint only uses primitive expressions.

        Allowed: literals, self, comparisons, ranges (..), boolean ops,
        unary negation, field access (self.x).
        Disallowed: function calls, pipes, lambdas, match, etc.
        """
        if isinstance(
            expr,
            (
                IntegerLit,
                DecimalLit,
                FloatLit,
                BooleanLit,
                StringLit,
                CharLit,
                RegexLit,
                RawStringLit,
                TripleStringLit,
            ),
        ):
            return
        if isinstance(expr, IdentifierExpr):
            return
        if isinstance(expr, FieldExpr):
            # Allow self.field access
            self._check_where_constraint(expr.obj)
            return
        if isinstance(expr, UnaryExpr):
            self._check_where_constraint(expr.operand)
            return
        if isinstance(expr, BinaryExpr):
            self._check_where_constraint(expr.left)
            self._check_where_constraint(expr.right)
            return
        # Everything else is disallowed
        self._error(
            "E352",
            "function calls are not allowed in `where` constraints; "
            "use primitive expressions (comparisons, ranges, boolean ops)",
            expr.span,
        )

    def _static_check_refinement(self, resolved: Type, value: Expr, span: Span) -> None:
        """Statically check refinement type constraints for constant values.

        When assigning a literal to a refinement type, evaluate the constraint
        at compile time. Emit E355 if the constraint fails.
        """
        if not isinstance(resolved, RefinementType) or resolved.constraint is None:
            return

        # Extract the literal value from the expression
        lit_value = self._extract_literal_value(value)
        if lit_value is None:
            return  # Non-literal — fall through to runtime check

        # Evaluate the constraint with the literal substituted for 'self'
        result = self._eval_refinement_constraint(resolved.constraint, lit_value)
        if result is False:
            self._error(
                "E355",
                f"value {lit_value!r} violates refinement constraint on '{resolved.name}'",
                span,
            )

    def _extract_literal_value(self, expr: Expr) -> object | None:
        """Extract a Python literal value from an AST literal expression."""
        if isinstance(expr, IntegerLit):
            return int(expr.value)
        if isinstance(expr, DecimalLit):
            return float(expr.value)
        if isinstance(expr, FloatLit):
            return float(expr.value[:-1])
        if isinstance(expr, StringLit):
            return expr.value
        if isinstance(expr, BooleanLit):
            return expr.value
        if isinstance(expr, CharLit):
            return expr.value
        if isinstance(expr, UnaryExpr) and expr.op == "-":
            inner = self._extract_literal_value(expr.operand)
            if isinstance(inner, (int, float)):
                return -inner
        return None

    def _eval_refinement_constraint(self, constraint: Expr, value: object) -> bool | None:
        """Evaluate a refinement constraint with a concrete value.

        Returns True (passes), False (fails), or None (indeterminate).
        """
        if isinstance(constraint, BinaryExpr):
            # Range: 1..65535 means value >= 1 and value <= 65535
            if constraint.op == "..":
                lo = self._extract_literal_value(constraint.left)
                hi = self._extract_literal_value(constraint.right)
                if lo is not None and hi is not None and isinstance(value, (int, float)):
                    return lo <= value and value <= hi  # type: ignore[operator]
                return None

            left = self._eval_refinement_constraint_expr(constraint.left, value)
            right = self._eval_refinement_constraint_expr(constraint.right, value)
            if left is None or right is None:
                return None

            op = constraint.op
            if op == ">=":
                return (left) >= (right)  # type: ignore[operator]
            if op == "<=":
                return (left) <= (right)  # type: ignore[operator]
            if op == ">":
                return (left) > (right)  # type: ignore[operator]
            if op == "<":
                return (left) < (right)  # type: ignore[operator]
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == "&&":
                return bool(left) and bool(right)
            if op == "||":
                return bool(left) or bool(right)

        if isinstance(constraint, UnaryExpr) and constraint.op == "!":
            inner = self._eval_refinement_constraint(constraint.operand, value)
            if inner is not None:
                return not inner

        # RegexLit constraints: can validate string literals
        if isinstance(constraint, (RegexLit, RawStringLit)):
            if isinstance(value, str):
                import re

                pattern = (
                    constraint.pattern if isinstance(constraint, RegexLit) else constraint.value
                )
                try:
                    return bool(re.fullmatch(pattern, value))
                except re.error:
                    return None

        return None

    def _eval_refinement_constraint_expr(self, expr: Expr, value: object) -> object | None:
        """Evaluate a sub-expression in a refinement constraint."""
        if isinstance(expr, IdentifierExpr) and expr.name == "self":
            return value
        if isinstance(expr, IntegerLit):
            return int(expr.value)
        if isinstance(expr, DecimalLit):
            return float(expr.value)
        if isinstance(expr, FloatLit):
            return float(expr.value[:-1])
        if isinstance(expr, StringLit):
            return expr.value
        if isinstance(expr, BooleanLit):
            return expr.value
        if isinstance(expr, UnaryExpr) and expr.op == "-":
            inner = self._eval_refinement_constraint_expr(expr.operand, value)
            if isinstance(inner, (int, float)):
                return -inner
        if isinstance(expr, BinaryExpr):
            left = self._eval_refinement_constraint_expr(expr.left, value)
            right = self._eval_refinement_constraint_expr(expr.right, value)
            if left is not None and right is not None:
                op = expr.op
                if op == "+":
                    return (left) + (right)  # type: ignore[operator]
                if op == "-":
                    return (left) - (right)  # type: ignore[operator]
                if op == "*":
                    return (left) * (right)  # type: ignore[operator]
                if op == "%":
                    return (left) % (right)  # type: ignore[operator]
        return None

    # ── Requires-based option narrowing ─────────────────────────

    def _collect_requires_narrowings(
        self,
        fd: FunctionDef,
    ) -> list[tuple[str, list[Expr]]]:
        """Scan fd.requires for validates calls and valid expressions.

        Returns a list of (module_name, args) tuples that can be used to
        narrow Option<Value> → Value and Result<Value, Error> → Value in the function body.
        """
        narrowings: list[tuple[str, list[Expr]]] = []
        # Flatten &&-conjunctions so each ValidExpr/CallExpr is processed individually
        exprs_to_check: list[Expr] = []
        for req_expr in fd.requires:
            stack = [req_expr]
            while stack:
                e = stack.pop()
                if isinstance(e, BinaryExpr) and e.op == "&&":
                    stack.append(e.left)
                    stack.append(e.right)
                else:
                    exprs_to_check.append(e)
        for req_expr in exprs_to_check:
            # valid file(path) → ValidExpr
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                func_name = req_expr.name
                args = req_expr.args
                n_args = len(args)
                # Infer arg types for accurate overload resolution among validates
                arg_types = [self._infer_expr(a) for a in args]
                sig = self.symbols.resolve_function_by_types(
                    "validates",
                    func_name,
                    arg_types,
                )
                if sig is None:
                    sig = self.symbols.resolve_function(
                        "validates",
                        func_name,
                        n_args,
                    )
                if sig is not None and sig.verb == "validates":
                    mod = sig.module or "_local"
                    narrowings.append((mod, args))
                continue
            # has(key, table) or Table.has(key, table)
            if not isinstance(req_expr, CallExpr):
                continue
            func = req_expr.func
            module_name: str | None = None
            func_name_: str | None = None
            if isinstance(func, FieldExpr) and isinstance(func.obj, TypeIdentifierExpr):
                module_name = func.obj.name
                func_name_ = func.field
            elif isinstance(func, IdentifierExpr):
                func_name_ = func.name
            else:
                continue
            n_args = len(req_expr.args)
            # Infer arg types for accurate overload resolution among validates
            arg_types = [self._infer_expr(a) for a in req_expr.args]
            sig = self.symbols.resolve_function_by_types(
                "validates",
                func_name_,
                arg_types,
            )
            if sig is None:
                sig = self.symbols.resolve_function(
                    "validates",
                    func_name_,
                    n_args,
                )
            if sig is not None and sig.verb == "validates":
                mod = module_name or sig.module  # type: ignore[assignment]
                if mod:
                    narrowings.append((mod, req_expr.args))
        return narrowings

    def _has_requires_narrowing(
        self,
        module: str,
        call_args: list[Expr],
    ) -> bool:
        """Check if a matching validates precondition exists."""
        for mod, req_args in self._requires_narrowings:
            if mod != module:
                continue
            if len(req_args) != len(call_args):
                continue
            if all(self._exprs_equal(a, b) for a, b in zip(req_args, call_args)):
                return True
        return False

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

        # matches verb: first parameter must be a matchable type
        if verb == "matches":
            if fd.params:
                first_type = self._resolve_type_expr(fd.params[0].type_expr)
                is_matchable = (
                    isinstance(first_type, (AlgebraicType, ErrorType))
                    or (
                        isinstance(first_type, PrimitiveType)
                        and first_type.name in ("String", "Integer")
                    )
                    or (
                        isinstance(first_type, GenericInstance)
                        and first_type.base_name in ("Result", "Option")
                    )
                )
                if not is_matchable:
                    self._error(
                        "E365",
                        f"matches verb requires first parameter to be "
                        f"a matchable type (algebraic, String, or "
                        f"Integer), got '{type_name(first_type)}'",
                        fd.params[0].span,
                    )
            else:
                self._error(
                    "E365",
                    "matches verb requires at least one parameter",
                    fd.span,
                )

        # Async verb rules
        if verb in _ASYNC_VERBS:
            self._check_async_body(fd)
            if verb == "attached" and fd.return_type is None:
                self._error("E370", "`attached` verb must have a return type", fd.span)
            if verb in ("detached", "renders") and fd.return_type is not None:
                self._error(
                    "E374",
                    f"`{verb}` verb cannot declare a return type; "
                    f"the caller does not wait for a result",
                    fd.span,
                )
        # event_type annotation rules (listens/renders event dispatcher)
        if fd.event_type is not None and verb not in ("listens", "renders", "attached"):
            self._error(
                "E405",
                "`event_type` annotation is only valid on `listens`, `renders`, or `attached` verb",
                fd.span,
            )
        if verb in ("listens", "renders"):
            if fd.event_type is None:
                self._error(
                    "E406",
                    f"`{verb}` verb requires an `event_type` annotation",
                    fd.span,
                )
            else:
                resolved_et = self._resolve_type_expr(fd.event_type)
                # For renders, event_type must be algebraic; for listens, it can be
                # a variant name used as an event filter (e.g. KeyDown)
                if (
                    verb == "renders"
                    and resolved_et is not None
                    and not isinstance(resolved_et, AlgebraicType)
                ):
                    self._error(
                        "E401",
                        "`event_type` must reference an algebraic type",
                        fd.event_type.span,
                    )
            # E402: renders requires List<Listens>, listens optionally takes List<Attached>
            if verb == "renders":
                expected_elem = "Listens"
                if not fd.params:
                    self._error(
                        "E402",
                        "`renders` first parameter must be `List<Listens>`",
                        fd.span,
                    )
                else:
                    first_type = self._resolve_type_expr(fd.params[0].type_expr)
                    if not (
                        isinstance(first_type, ListType)
                        and isinstance(first_type.element, PrimitiveType)
                        and first_type.element.name == expected_elem
                    ):
                        self._error(
                            "E402",
                            "`renders` first parameter must be `List<Listens>`",
                            fd.params[0].span,
                        )
            elif verb == "listens" and fd.params:
                first_type = self._resolve_type_expr(fd.params[0].type_expr)
                if first_type is not None and not (
                    isinstance(first_type, ListType)
                    and isinstance(first_type.element, PrimitiveType)
                    and first_type.element.name == "Attached"
                ):
                    self._error(
                        "E402",
                        "`listens` first parameter, if present, must be `List<Attached>`",
                        fd.params[0].span,
                    )
        # state_init annotation rules (renders only)
        if fd.state_init is not None and verb != "renders":
            self._error(
                "E407",
                "`state_init` annotation is only valid on `renders` verb",
                fd.span,
            )
        if verb == "renders" and fd.state_init is None:
            self._error(
                "E408",
                "`renders` verb requires a `state_init` annotation",
                fd.span,
            )
        # state_type annotation rules (listens only)
        if fd.state_type is not None and verb != "listens":
            self._error(
                "E409",
                "`state_type` annotation is only valid on `listens` verb",
                fd.span,
            )

        # I367: suggest extracting match to a matches verb function
        # listens/streams/renders bodies are inherently match-based, so exempt
        if verb not in ("matches", "listens", "streams", "renders"):
            self._check_match_restriction(fd.body, fd.span)

    def _check_async_body(self, fd: FunctionDef) -> None:
        """Enforce async body rules: no blocking IO calls; async calls must use &."""
        for stmt in fd.body:
            self._check_async_stmt(stmt, fd)

    def _check_async_stmt(self, stmt: Stmt | MatchExpr, fd: FunctionDef) -> None:
        if isinstance(stmt, VarDecl):
            self._check_async_expr(stmt.value, fd)
        elif isinstance(stmt, Assignment):
            self._check_async_expr(stmt.value, fd)
        elif isinstance(stmt, ExprStmt):
            self._check_async_expr(stmt.expr, fd)
        elif isinstance(stmt, MatchExpr):
            if stmt.subject:
                self._check_async_expr(stmt.subject, fd)
            for arm in stmt.arms:
                for s in arm.body:
                    self._check_async_stmt(s, fd)

    def _check_async_expr(self, expr: Expr, fd: FunctionDef) -> None:
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                fname = expr.func.name
                sig = self.symbols.resolve_function_any(fname)
                if sig:
                    if sig.verb in _BLOCKING_VERBS and fd.verb not in (
                        "detached",
                        "attached",
                        "renders",
                    ):
                        self._error(
                            "E371",
                            f"async body cannot call blocking IO function '{fname}'; "
                            f"use an async verb instead",
                            expr.span,
                        )
            for arg in expr.args:
                self._check_async_expr(arg, fd)
        elif isinstance(expr, AsyncCallExpr):
            # The & wrapper satisfies E371/E372, so only check arguments
            inner = expr.expr
            if isinstance(inner, FailPropExpr):
                inner = inner.expr
            if isinstance(inner, CallExpr):
                for arg in inner.args:
                    self._check_async_expr(arg, fd)
        elif isinstance(expr, FailPropExpr):
            self._check_async_expr(expr.expr, fd)
        elif isinstance(expr, BinaryExpr):
            self._check_async_expr(expr.left, fd)
            self._check_async_expr(expr.right, fd)
        elif isinstance(expr, UnaryExpr):
            self._check_async_expr(expr.operand, fd)
        elif isinstance(expr, PipeExpr):
            self._check_async_expr(expr.left, fd)
            self._check_async_expr(expr.right, fd)

    def _body_has_blocking_calls(self, body: list) -> bool:
        """Check if body contains direct calls to blocking IO functions."""
        for stmt in body:
            if isinstance(stmt, VarDecl) and self._expr_has_blocking_call(stmt.value):
                return True
            if isinstance(stmt, ExprStmt) and self._expr_has_blocking_call(stmt.expr):
                return True
            if isinstance(stmt, Assignment) and self._expr_has_blocking_call(stmt.value):
                return True
            if isinstance(stmt, MatchExpr):
                for arm in stmt.arms:
                    if self._body_has_blocking_calls(arm.body):
                        return True
        return False

    def _expr_has_blocking_call(self, expr: Expr) -> bool:
        """Check if expression contains a call to a blocking IO function."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                sig = self.symbols.resolve_function_any(expr.func.name)
                if sig and sig.verb in _BLOCKING_VERBS:
                    return True
            return any(self._expr_has_blocking_call(a) for a in expr.args)
        if isinstance(expr, FailPropExpr):
            return self._expr_has_blocking_call(expr.expr)
        if isinstance(expr, AsyncCallExpr):
            return self._expr_has_blocking_call(expr.expr)
        if isinstance(expr, BinaryExpr):
            return self._expr_has_blocking_call(expr.left) or self._expr_has_blocking_call(
                expr.right
            )
        if isinstance(expr, PipeExpr):
            return self._expr_has_blocking_call(expr.left) or self._expr_has_blocking_call(
                expr.right
            )
        if isinstance(expr, UnaryExpr):
            return self._expr_has_blocking_call(expr.operand)
        return False

    def _has_pure_overload(self, name: str) -> bool:
        """Check if a function name has at least one pure verb overload."""
        for verb, fname in self.symbols.all_functions():
            if fname == name and verb in _PURE_VERBS:
                return True
        return False

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
        elif isinstance(stmt, FieldAssignment):
            self._error(
                "E331",
                "field mutation in pure function; construct a new value instead",
                stmt.span,
            )
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
            if isinstance(expr.func, IdentifierExpr):
                fname = expr.func.name
                if fname in _IO_FUNCTIONS:
                    self._error(
                        "E362",
                        f"pure function cannot call IO function '{fname}'",
                        expr.span,
                    )
                elif fname in self._io_function_names:
                    # Skip if the name also has a pure overload (channel
                    # dispatch) — the actual verb check will happen in
                    # _infer_call once the correct overload is resolved.
                    if not self._has_pure_overload(fname):
                        self._error(
                            "E363",
                            f"pure function cannot call IO function '{fname}'",
                            expr.span,
                        )
                else:
                    # Also check if resolved function has an IO verb
                    sig = self.symbols.resolve_function_any(fname)
                    if sig and sig.verb in ("inputs", "outputs"):
                        self._error(
                            "E362",
                            f"pure function cannot call IO function '{fname}'",
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
        elif isinstance(expr, FailPropExpr):
            self._check_pure_expr(expr.expr)
        elif isinstance(expr, AsyncCallExpr):
            self._check_pure_expr(expr.expr)
        elif isinstance(expr, LambdaExpr):
            self._check_pure_expr(expr.body)
        elif isinstance(expr, MatchExpr):
            if expr.subject:
                self._check_pure_expr(expr.subject)
            for arm in expr.arms:
                for s in arm.body:
                    self._check_pure_stmt(s)

    # ── Match restriction (I367) ────────────────────────────────

    def _check_match_restriction(
        self,
        body: list[Stmt | MatchExpr],
        span: Span,
    ) -> None:
        """I367: suggest extracting match to a 'matches' verb function."""
        for stmt in body:
            if isinstance(stmt, MatchExpr):
                if len(stmt.arms) >= 3 and not _match_arms_have_fail_prop(stmt):
                    self._info(
                        "I367",
                        "consider extracting match to a 'matches' verb function for better code flow",  # noqa: E501
                        stmt.span,
                    )
            elif isinstance(stmt, VarDecl):
                self._check_match_in_expr(stmt.value)
            elif isinstance(stmt, Assignment):
                self._check_match_in_expr(stmt.value)
            elif isinstance(stmt, FieldAssignment):
                self._check_match_in_expr(stmt.value)
            elif isinstance(stmt, ExprStmt):
                self._check_match_in_expr(stmt.expr)

    def _check_match_in_expr(self, expr: Expr) -> None:
        """Walk an expression looking for MatchExpr nodes."""
        if isinstance(expr, MatchExpr):
            if len(expr.arms) >= 3 and not _match_arms_have_fail_prop(expr):
                self._info(
                    "I367",
                    "consider extracting match to a 'matches' verb function for better code flow",
                    expr.span,
                )
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._check_match_in_expr(arg)
        elif isinstance(expr, BinaryExpr):
            self._check_match_in_expr(expr.left)
            self._check_match_in_expr(expr.right)
        elif isinstance(expr, UnaryExpr):
            self._check_match_in_expr(expr.operand)
        elif isinstance(expr, PipeExpr):
            self._check_match_in_expr(expr.left)
            self._check_match_in_expr(expr.right)
        elif isinstance(expr, LambdaExpr):
            self._check_match_in_expr(expr.body)
        elif isinstance(expr, FailPropExpr):
            self._check_match_in_expr(expr.expr)
        elif isinstance(expr, AsyncCallExpr):
            self._check_match_in_expr(expr.expr)

    def _check_unused_pure_result(self, stmt: Stmt | MatchExpr) -> None:
        """Check for unused pure function calls in statement position (W332)."""
        if isinstance(stmt, ExprStmt):
            self._check_expr_unused_pure_result(stmt.expr)
        elif isinstance(stmt, MatchExpr):
            for arm in stmt.arms:
                if arm.body:
                    for i, body_stmt in enumerate(arm.body):
                        if i < len(arm.body) - 1:
                            self._check_unused_pure_result(body_stmt)

    def _check_expr_unused_pure_result(self, expr: Expr) -> None:
        """Check if expression contains unused pure function calls."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                arg_count = len(expr.args)
                sig = self.symbols.resolve_function(None, expr.func.name, arg_count)
                if sig is None:
                    sig = self.symbols.resolve_function_any(expr.func.name, arity=arg_count)
                if sig is not None and sig.verb in _PURE_VERBS:
                    if (
                        not isinstance(sig.return_type, PrimitiveType)
                        or sig.return_type.name != "Unit"
                    ):
                        self.diagnostics.append(
                            Diagnostic(
                                severity=Severity.WARNING,
                                code="W332",
                                message=f"unused result of pure function '{expr.func.name}'. "
                                f"Pure functions have no side effects - result is discarded.",
                                labels=[DiagnosticLabel(span=expr.span, message="")],
                            )
                        )
        elif isinstance(expr, MatchExpr):
            for arm in expr.arms:
                if arm.body:
                    for body_stmt in arm.body[:-1]:
                        self._check_unused_pure_result(body_stmt)

    # ── Statement checking ──────────────────────────────────────

    def _check_stmt(self, stmt: Stmt | MatchExpr) -> Type:
        """Check a statement and return its type (for last-expression semantics)."""
        if isinstance(stmt, VarDecl):
            return self._check_var_decl(stmt)
        if isinstance(stmt, Assignment):
            return self._check_assignment(stmt)
        if isinstance(stmt, FieldAssignment):
            self._infer_expr(stmt.target)
            self._infer_expr(stmt.value)
            return UNIT
        if isinstance(stmt, ExprStmt):
            ty = self._infer_expr(stmt.expr)
            # W372: failable call result silently discarded — no ! and no binding
            if (
                isinstance(stmt.expr, CallExpr)
                and isinstance(ty, GenericInstance)
                and ty.base_name == "Result"
            ):
                # 'streams' verb functions handle errors internally via event loops;
                # discarding their result is intentional.
                _skip = False
                if isinstance(stmt.expr.func, IdentifierExpr):
                    _sig = self.symbols.resolve_function_any(
                        stmt.expr.func.name, arity=len(stmt.expr.args)
                    )
                    if _sig is not None and _sig.verb == "streams":
                        _skip = True
                if not _skip:
                    self._warning(
                        "W372",
                        "failable call result discarded — use ! to propagate or match to handle",
                        stmt.expr.span,
                    )
            return ty
        if isinstance(stmt, MatchExpr):
            return self._infer_match(stmt)
        if isinstance(stmt, TodoStmt):
            return UNIT
        return UNIT

    def _check_var_decl(self, vd: VarDecl) -> Type:
        """Check a variable declaration."""
        expected = None
        if vd.type_expr is not None:
            expected = self._resolve_type_expr(vd.type_expr)
            if isinstance(expected, UnitType):
                self._error(
                    "E326",
                    "cannot use 'Unit' as a variable type",
                    vd.span,
                )

        inferred = self._infer_expr(vd.value, expected_type=expected)

        if isinstance(inferred, UnitType) and not isinstance(expected, UnitType):
            self._error(
                "E326",
                "cannot assign a 'Unit' value to a variable",
                vd.span,
            )

        if expected is not None:
            # Scale:N enforcement: check decimal literal precision
            exp_scale = get_scale(expected)
            if exp_scale is not None and isinstance(vd.value, DecimalLit):
                places = _count_decimal_places(vd.value.value)
                if places > exp_scale:
                    self._error(
                        "E407",
                        f"Scale:{exp_scale} requires at most {exp_scale} decimal "
                        f"place{'s' if exp_scale != 1 else ''}, "
                        f"but literal '{vd.value.value}' has {places}",
                        vd.span,
                    )
            # Scale:N enforcement: check scale mismatch between Decimal types
            act_scale = get_scale(inferred)
            if exp_scale is not None and act_scale is not None and exp_scale != act_scale:
                self._error(
                    "E408",
                    f"cannot assign Decimal:[Scale:{act_scale}] to "
                    f"Decimal:[Scale:{exp_scale}] without explicit rounding",
                    vd.span,
                )
            if not types_compatible(expected, inferred):
                # Allow StoreTable → store-backed lookup type assignment
                expected_name = getattr(expected, "name", "")
                actual_name = getattr(inferred, "name", "")
                if not (expected_name in self._store_lookup_types and actual_name == "StoreTable"):
                    self._error(
                        "E321",
                        f"type mismatch: expected '{type_name(expected)}', got '{type_name(inferred)}'",  # noqa: E501
                        vd.span,
                    )
            # Detect Value → concrete type coercion (runtime-checked)
            if self._is_value_coercion(inferred, expected):
                self._info(
                    "I311",
                    f"Value → '{type_name(expected)}' coercion is checked at runtime",
                    vd.span,
                )
            resolved = expected
        else:
            resolved = inferred
            # Record inferred type for LSP inlay hints (untyped VarDecl only)
            if not isinstance(resolved, ErrorType):
                self.inlay_type_map[(vd.span.start_line, vd.span.start_col)] = type_name(resolved)

        # Static refinement check: reject invalid constants at compile time
        self._static_check_refinement(resolved, vd.value, vd.span)

        existing = self.symbols.define(
            Symbol(
                name=vd.name,
                kind=SymbolKind.VARIABLE,
                resolved_type=resolved,
                span=vd.span,
            )
        )
        if existing is not None:
            self._error("E302", f"variable '{vd.name}' already defined in this scope", vd.span)

        return UNIT

    def _check_assignment(self, assign: Assignment) -> Type:
        """Check an assignment statement."""
        sym = self.symbols.lookup(assign.target)
        expected = sym.resolved_type if sym else None
        value_type = self._infer_expr(assign.value, expected_type=expected)

        if sym is None:
            # Implicit declaration: `x = expr` without `x as Type = expr`
            tn = type_name(value_type)
            self.diagnostics.append(
                Diagnostic(
                    severity=Severity.NOTE,
                    code="I310",
                    message=f"implicitly typed variable '{assign.target}'",
                    labels=[DiagnosticLabel(span=assign.span, message="")],
                    suggestions=[
                        Suggestion(
                            message="add an explicit type annotation",
                            replacement=f"{assign.target} as {tn} = ...",
                        )
                    ],
                )
            )
            self.symbols.define(
                Symbol(
                    name=assign.target,
                    kind=SymbolKind.VARIABLE,
                    resolved_type=value_type,
                    span=assign.span,
                )
            )
            return UNIT

        sym.used = True
        # Track moves for assignment: if assigning an owned variable to another variable,
        # the source is moved
        if isinstance(assign.value, IdentifierExpr):
            value_sym = self.symbols.lookup(assign.value.name)
            if value_sym is not None and has_own_modifier(value_sym.resolved_type):
                self._moved_vars.add(assign.value.name)
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

    def _infer_expr(self, expr: Expr, expected_type: Type | None = None) -> Type:
        """Infer the type of an expression."""
        if expected_type is not None:
            self._expected_type = expected_type
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
            return PrimitiveType("String", ((None, "Reg"),))
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
            return self._infer_list(expr, expected_type=expected_type)
        if isinstance(expr, IdentifierExpr):
            return self._infer_identifier(expr)
        if isinstance(expr, TypeIdentifierExpr):
            return self._infer_type_identifier(expr)
        if isinstance(expr, BinaryExpr):
            return self._infer_binary(expr)
        if isinstance(expr, UnaryExpr):
            return self._infer_unary(expr)
        if isinstance(expr, CallExpr):
            return self._infer_call(expr, expected_type=expected_type)
        if isinstance(expr, FieldExpr):
            return self._infer_field(expr)
        if isinstance(expr, PipeExpr):
            return self._infer_pipe(expr)
        if isinstance(expr, FailPropExpr):
            return self._infer_fail_prop(expr, expected_type=expected_type)
        if isinstance(expr, AsyncCallExpr):
            return self._infer_async_call(expr, expected_type=expected_type)
        if isinstance(expr, MatchExpr):
            return self._infer_match(expr, expected_type=expected_type)
        if isinstance(expr, LambdaExpr):
            return self._infer_lambda(expr)
        if isinstance(expr, IndexExpr):
            return self._infer_index(expr)
        if isinstance(expr, ValidExpr):
            n = len(expr.args) if expr.args is not None else 0
            # Use type-aware resolution among validates overloads
            if expr.args is not None:
                varg_types = [self._infer_expr(a) for a in expr.args]
                sig = self.symbols.resolve_function_by_types(
                    "validates",
                    expr.name,
                    varg_types,
                )
            else:
                sig = None
            if sig is None:
                sig = self.symbols.resolve_function("validates", expr.name, n)
            if sig is None:
                sig = self.symbols.resolve_function_any(expr.name, arity=n)
            if sig and sig.module:
                self._used_imports.add((sig.module, expr.name))
            if expr.args is None:
                # Function reference: valid error → FunctionType([Diagnostic], Boolean)
                if sig is not None and sig.param_types:
                    return FunctionType(list(sig.param_types), BOOLEAN)
            # Check argument types against the validator's parameter types
            if sig is not None and expr.args is not None:
                for i, (param_ty, arg_expr) in enumerate(zip(sig.param_types, expr.args)):
                    # Snapshot diagnostics: _infer_expr may emit E310 for args
                    # that are not yet in scope (e.g. local vars in ensures clauses).
                    # Roll back those side-effect diagnostics if the arg is unresolved.
                    _diag_count = len(self.diagnostics)
                    arg_ty = self._infer_expr(arg_expr)
                    if isinstance(arg_ty, ErrorType):
                        del self.diagnostics[_diag_count:]
                        continue
                    # Allow Option<T>→T coercions: the C emitter generates .value
                    # unwrapping for params narrowed via requires valid
                    if (
                        isinstance(arg_ty, GenericInstance)
                        and arg_ty.base_name == "Option"
                        and arg_ty.args
                        and types_compatible(param_ty, arg_ty.args[0])
                    ):
                        continue
                    if not types_compatible(param_ty, arg_ty):
                        self._error(
                            "E331",
                            f"argument type mismatch: expected "
                            f"'{type_name(param_ty)}', got '{type_name(arg_ty)}'",
                            arg_expr.span if hasattr(arg_expr, "span") else expr.span,
                        )
            return BOOLEAN
        if isinstance(expr, ComptimeExpr):
            return self._infer_comptime(expr)
        if isinstance(expr, LookupAccessExpr):
            return self._check_lookup_access_expr(expr)
        if isinstance(expr, BinaryLookupExpr):
            # Runtime binary lookup — type already resolved by checker
            col = self._resolve_type_expr(SimpleType(expr.column_type, expr.span))
            return col if col else ERROR_TY
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
        if self._match_arm_depth == 0:
            sym.used_outside_match = True
        else:
            sym.match_arm_ids.add(self._match_arm_id)
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
            # Division by zero check (E357)
            if expr.op in ("/", "%") and isinstance(expr.right, IntegerLit):
                if expr.right.value == "0":
                    self._error("E357", "division by zero", expr.span)
                    return ERROR_TY
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

    def _infer_fail_prop(self, expr: FailPropExpr, expected_type: Type | None = None) -> Type:
        """Check fail propagation (!)."""
        inner_expected = None
        if expected_type is not None:
            inner_expected = GenericInstance("Result", [expected_type, ERROR_TY])
        inner = self._infer_expr(expr.expr, expected_type=inner_expected)

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

        # The inner expression must be a failable (Result-returning) call
        if not isinstance(inner, ErrorType) and not (
            isinstance(inner, GenericInstance) and inner.base_name == "Result"
        ):
            self.diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E351",
                    message="! applied to non-failable expression",
                    labels=[
                        DiagnosticLabel(
                            span=expr.span,
                            message="this expression cannot fail; remove the !",
                        )
                    ],
                    suggestions=[
                        Suggestion(
                            message="remove the ! operator",
                            replacement="remove '!'",
                        )
                    ],
                )
            )

        # The inner expression should be Result-like; return its success type
        if isinstance(inner, GenericInstance) and inner.base_name == "Result":
            if inner.args:
                return inner.args[0]
        return ERROR_TY

    def _infer_async_call(self, expr: AsyncCallExpr, expected_type: Type | None = None) -> Type:
        """Type-check async call (&). Same type as the inner expression."""
        # Resolve callee from inner expression (may be CallExpr or FailPropExpr)
        inner = expr.expr
        if isinstance(inner, FailPropExpr):
            inner = inner.expr
        if isinstance(inner, CallExpr) and isinstance(inner.func, IdentifierExpr):
            callee_name = inner.func.name
            callee_sig = self.symbols.resolve_function_any(callee_name)
            if callee_sig:
                if callee_sig.verb not in _ASYNC_VERBS:
                    # I375: & on non-async callee is a no-op
                    self._info(
                        "I375",
                        f"`&` has no effect on non-async function '{callee_name}'; "
                        f"`prove format` will remove it",
                        expr.span,
                    )
                elif callee_sig.verb == "attached":
                    # E398: IO-bearing attached outside async context
                    if callee_name in self._attached_with_io:
                        if (
                            self._current_function
                            and isinstance(self._current_function, FunctionDef)
                            and self._current_function.verb not in ("listens", "attached")
                        ):
                            self._error(
                                "E398",
                                f"IO-bearing `attached` function '{callee_name}' "
                                f"can only be called from a `listens` or `attached` body",
                                expr.span,
                            )
                    # I377: attached& outside listens runs synchronously
                    if (
                        self._current_function
                        and isinstance(self._current_function, FunctionDef)
                        and self._current_function.verb != "listens"
                    ):
                        self._info(
                            "I377",
                            f"`attached` call '{callee_name}' runs synchronously "
                            f"outside a `listens` body",
                            expr.span,
                        )
                # detached with &: no diagnostic (fire-and-forget anywhere)

        # Set flag so _infer_call knows this CallExpr is wrapped in &
        self._inside_async_call = True
        try:
            return self._infer_expr(expr.expr, expected_type=expected_type)
        finally:
            self._inside_async_call = False

    @staticmethod
    def _exprs_equal(a: Expr, b: Expr) -> bool:
        """Structurally compare two expressions ignoring spans."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IdentifierExpr):
            return a.name == b.name
        if isinstance(a, (IntegerLit, DecimalLit, FloatLit, StringLit)):
            return a.value == b.value
        if isinstance(a, BooleanLit):
            return a.value == b.value
        if isinstance(a, BinaryExpr):
            return (
                a.op == b.op
                and Checker._exprs_equal(a.left, b.left)
                and Checker._exprs_equal(a.right, b.right)
            )
        if isinstance(a, UnaryExpr):
            return a.op == b.op and Checker._exprs_equal(a.operand, b.operand)
        if isinstance(a, CallExpr):
            return (
                Checker._exprs_equal(a.func, b.func)
                and len(a.args) == len(b.args)
                and all(Checker._exprs_equal(x, y) for x, y in zip(a.args, b.args))
            )
        if isinstance(a, FieldExpr):
            return a.field == b.field and Checker._exprs_equal(a.obj, b.obj)
        if isinstance(a, TypeIdentifierExpr):
            return a.name == b.name
        return False

    def _infer_match(self, expr: MatchExpr, expected_type: Type | None = None) -> Type:
        subject_type: Type = ERROR_TY
        if expr.subject is not None:
            subject_type = self._infer_expr(expr.subject)
        elif (
            self._current_function
            and isinstance(self._current_function, FunctionDef)
            and self._current_function.verb in ("matches", "listens", "streams", "renders")
        ):
            # Implicit match subject resolution per verb:
            # - matches: first parameter type
            # - listens/renders: event_type annotation (the algebraic dispatch protocol)
            # - streams: return type (the element type being streamed)
            if (
                self._current_function.verb == "streams"
                and self._current_function.return_type is not None
            ):
                subject_type = self._resolve_type_expr(self._current_function.return_type)
            elif (
                self._current_function.verb in ("listens", "renders")
                and self._current_function.event_type is not None
            ):
                subject_type = self._resolve_type_expr(self._current_function.event_type)
            elif self._current_function.params:
                subject_type = self._resolve_type_expr(self._current_function.params[0].type_expr)

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
        # Skip for renders/listens — event dispatch doesn't require exhaustiveness
        _is_event_dispatch = (
            self._current_function is not None
            and isinstance(self._current_function, FunctionDef)
            and self._current_function.verb in ("renders", "listens")
        )
        if not _is_event_dispatch:
            if isinstance(subject_type, AlgebraicType):
                self._check_exhaustiveness(expr, subject_type)
            elif isinstance(subject_type, GenericInstance) and subject_type.base_name in (
                "Result",
                "Option",
            ):
                self._check_generic_exhaustiveness(expr, subject_type)

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

        # Infer arm types — skip ErrorType arms to avoid poison propagation
        result_type: Type = cast(Type, UNIT)
        arm_types: list[tuple[Type, MatchArm]] = []
        for arm in expr.arms:
            self.symbols.push_scope("match_arm")
            self._check_pattern(arm.pattern, subject_type)
            arm_type = UNIT
            self._match_arm_id += 1
            self._match_arm_depth += 1
            for stmt in arm.body:
                arm_type = self._check_stmt(stmt)  # type: ignore[assignment]
            self._match_arm_depth -= 1
            if not isinstance(arm_type, ErrorType):
                result_type = arm_type
            arm_types.append((arm_type, arm))
            self.symbols.pop_scope()

        # E400: check for arms returning Unit when other arms return a value
        # Skip for listens/streams where match arms are loop-body statements
        cur_verb = (
            self._current_function.verb
            if self._current_function and isinstance(self._current_function, FunctionDef)
            else None
        )
        # Find the dominant value type (first non-Unit, non-Error arm type)
        value_type: Type | None = None
        for t, _ in arm_types:
            if not isinstance(t, (UnitType, ErrorType)):
                value_type = t
                break
        if value_type is not None:
            if cur_verb not in ("listens", "streams", "renders"):
                result_type = value_type
                for arm_type, arm in arm_types:  # type: ignore
                    if isinstance(arm_type, UnitType):
                        self._error(
                            "E400",
                            f"match arm returns Unit but other arms return "
                            f"'{type_name(value_type)}'",
                            arm.span,
                        )

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

        # Collect closure captures (stored for emitter ctx struct generation)
        captures: list[str] = []
        self._collect_lambda_captures(expr.body, param_names, captures)
        self._lambda_captures[id(expr)] = captures

        prev = self._inside_lambda
        self._inside_lambda = True
        try:
            body_type = self._infer_expr(expr.body)
        finally:
            self._inside_lambda = prev
        self.symbols.pop_scope()
        return FunctionType(param_types, body_type)

    def _collect_lambda_captures(
        self,
        expr: Expr,
        param_names: set[str],
        captures: list[str],
    ) -> None:
        """Walk lambda body; collect names of captured enclosing-scope locals."""
        if isinstance(expr, IdentifierExpr):
            if expr.name not in param_names and expr.name not in captures:
                sym = self.symbols.lookup(expr.name)
                if sym is not None and sym.kind == SymbolKind.VARIABLE:
                    captures.append(expr.name)
        elif isinstance(expr, BinaryExpr):
            self._collect_lambda_captures(expr.left, param_names, captures)
            self._collect_lambda_captures(expr.right, param_names, captures)
        elif isinstance(expr, UnaryExpr):
            self._collect_lambda_captures(expr.operand, param_names, captures)
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._collect_lambda_captures(arg, param_names, captures)
        elif isinstance(expr, FieldExpr):
            self._collect_lambda_captures(expr.obj, param_names, captures)

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

    def _infer_list(self, expr: ListLiteral, expected_type: Type | None = None) -> Type:
        if not expr.elements:
            # Try to use expected type for empty list
            from prove.types import ListType

            if expected_type is not None:
                if isinstance(expected_type, ListType):
                    return expected_type
                if isinstance(expected_type, GenericInstance) and expected_type.base_name == "List":
                    return expected_type
            return ListType(ERROR_TY)

        # Expected element type
        elem_expected = None
        from prove.types import ListType

        if expected_type is not None:
            if isinstance(expected_type, ListType):
                elem_expected = expected_type.element
            elif (
                isinstance(expected_type, GenericInstance)
                and expected_type.base_name == "List"
                and expected_type.args
            ):
                elem_expected = expected_type.args[0]

        first = self._infer_expr(expr.elements[0], expected_type=elem_expected)
        for elem in expr.elements[1:]:
            self._infer_expr(elem, expected_type=elem_expected)
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
        result: Type = UNIT
        for stmt in expr.body:
            result = self._check_stmt(stmt)
        # Evaluate now to catch runtime errors (e.g. read() on a missing file)
        from prove.errors import CompileError
        from prove.interpreter import ComptimeInterpreter

        source_file = expr.span.file if expr.span and expr.span.file else ""
        if source_file.startswith("file://"):
            from urllib.parse import unquote, urlparse

            source_file = unquote(urlparse(source_file).path)
        source_dir = Path(source_file).parent if source_file else Path(".")
        try:
            ComptimeInterpreter(module_source_dir=source_dir).evaluate(expr)
        except CompileError as exc:
            for diag in exc.diagnostics:
                self._error(diag.code, diag.message, expr.span)
        except Exception as exc:
            self._error(
                "E417", f"comptime evaluation failed: {type(exc).__name__}: {exc}", expr.span
            )
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
            elif isinstance(subject_type, GenericInstance):
                # Handle Result<Value, Error> and Option<Value> variant patterns
                self._check_generic_variant_pattern(pattern, subject_type)
            elif isinstance(subject_type, RecordType) and pattern.name == subject_type.name:
                pass  # Record type match — handled elsewhere
            elif (
                pattern.name in ("Some", "None")
                and isinstance(subject_type, PrimitiveType)
                and subject_type.name
                in (
                    "Integer",
                    "Boolean",
                    "Decimal",
                    "Float",
                    "Byte",
                    "Unit",
                    "Character",
                )
            ):
                self._error(
                    "E371",
                    f"cannot match variant '{pattern.name}' on value type "
                    f"'{type_name(subject_type)}'",
                    pattern.span,
                )
            elif pattern.name not in ("Some", "None"):
                # Non-Option variant on a non-algebraic type
                self._error(
                    "E371",
                    f"cannot match variant '{pattern.name}' on type '{type_name(subject_type)}'",
                    pattern.span,
                )
            else:
                # Some/None on a pointer type (e.g. String) — null check
                if pattern.name == "Some" and pattern.fields:
                    for sub in pattern.fields:
                        self._check_pattern(sub, subject_type)
        elif isinstance(pattern, WildcardPattern):
            pass  # matches everything
        elif isinstance(pattern, LiteralPattern):
            pass  # literal match
        elif isinstance(pattern, LookupPattern):
            # Mark the type name as used (e.g. Key in Key:Escape)
            self._used_types.add(pattern.type_name)
            # Verify the type is defined
            resolved_lt = self.symbols.resolve_type(pattern.type_name)
            if resolved_lt is None:
                self._error(
                    "E300",
                    f"undefined type `{pattern.type_name}`",
                    pattern.span,
                )

    def _check_generic_variant_pattern(
        self, pattern: VariantPattern, subject_type: GenericInstance
    ) -> None:
        """Bind variant sub-patterns for generic types (Result, Option)."""
        base = subject_type.base_name
        args = subject_type.args
        name = pattern.name

        # Map variant name → inner type for builtin generic types
        inner_type: Type | None = None
        valid = False
        if base == "Result" and len(args) >= 2:
            if name == "Ok":
                inner_type = args[0]
                valid = True
            elif name == "Err":
                inner_type = args[1]
                valid = True
            else:
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.ERROR,
                        "E372",
                        f"unknown variant '{name}' for Result type",
                        labels=[DiagnosticLabel(span=pattern.span, message="")],
                        notes=[
                            "Result has variants Ok and Err, e.g. Ok(value) => ... | Err(e) => ..."
                        ],
                    )
                )
        elif base == "Option" and len(args) >= 1:
            if name == "Some":
                inner_type = args[0]
                valid = True
            elif name == "None":
                inner_type = None  # No binding for None
                valid = True
            else:
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.ERROR,
                        "E372",
                        f"unknown variant '{name}' for Option type",
                        labels=[DiagnosticLabel(span=pattern.span, message="")],
                        notes=[
                            "Option has variants Some and None, "
                            "e.g. Some(value) => ... | None => ..."
                        ],
                    )
                )

        if valid and inner_type is not None:
            for sub in pattern.fields:
                self._check_pattern(sub, inner_type)

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
                    if arm.pattern.name in covered and not arm.pattern.fields:
                        self._warning(
                            "W305",
                            f"duplicate match arm for variant '{arm.pattern.name}'",
                            arm.pattern.span,
                        )
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

    def _check_generic_exhaustiveness(self, expr: MatchExpr, subject_type: GenericInstance) -> None:
        """Check match exhaustiveness for Result/Option generic types."""
        base = subject_type.base_name
        if base == "Result":
            required = {"Ok", "Err"}
        elif base == "Option":
            required = {"Some", "None"}
        else:
            return

        covered: set[str] = set()
        has_wildcard = False

        for arm in expr.arms:
            if isinstance(arm.pattern, VariantPattern):
                if arm.pattern.name in required:
                    if arm.pattern.name in covered and not arm.pattern.fields:
                        self._warning(
                            "W305",
                            f"duplicate match arm for variant '{arm.pattern.name}'",
                            arm.pattern.span,
                        )
                    covered.add(arm.pattern.name)
            elif isinstance(arm.pattern, (WildcardPattern, BindingPattern)):
                has_wildcard = True

        if not has_wildcard:
            missing = required - covered
            if missing:
                names = ", ".join(sorted(missing))
                arms_str = " | ".join(
                    f"{v}(x) => ..." if v not in ("None",) else f"{v} => ..."
                    for v in sorted(missing)
                )
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.ERROR,
                        "E373",
                        f"non-exhaustive match on {base}: missing {names}",
                        labels=[DiagnosticLabel(span=expr.span, message="")],
                        notes=[f"add the missing arms: {arms_str}"],
                    )
                )

    # ── Lookup table checking ────────────────────────────────────

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
                # Variant name used as type → resolve to parent algebraic
                vsig = self.symbols.resolve_function_any(type_expr.name)
                if (
                    vsig is not None
                    and vsig.verb is None
                    and isinstance(vsig.return_type, AlgebraicType)
                ):
                    self._used_types.add(vsig.return_type.name)
                    return vsig.return_type
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
                mods = tuple((m.name, m.value) for m in type_expr.modifiers)
                if mods:
                    return ArrayType(args[0], modifiers=mods)
                return ArrayType(args[0])
            # Special-case Verb<P1, ..., Pn, R> → FunctionType
            if type_expr.name == "Verb" and len(args) >= 1:
                return FunctionType(list(args[:-1]), args[-1])
            # Check base type exists
            base = self.symbols.resolve_type(type_expr.name)
            if base is None:
                # Variant name used as generic type → resolve to parent algebraic
                vsig = self.symbols.resolve_function_any(type_expr.name)
                if (
                    vsig is not None
                    and vsig.verb is None
                    and isinstance(vsig.return_type, AlgebraicType)
                ):
                    self._used_types.add(vsig.return_type.name)
                    return vsig.return_type
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
            mods = tuple((m.name, m.value) for m in type_expr.modifiers)
            return PrimitiveType(type_expr.name, mods)

        return ERROR_TY

    # ── Ownership tracking ──────────────────────────────────────

    def _infer_param_borrows(
        self, params: list[Param], param_types: list[Type], body: list[Stmt | MatchExpr]
    ) -> dict[str, Type]:
        """Analyze function body to infer which parameters are used in read-only mode.

        Returns a mapping from parameter name to its borrowed type if the parameter
        is only used in read-only contexts (passed to other functions without mutation).
        """
        from prove.types import BorrowType

        param_readonly_usage: dict[str, bool] = {}
        for p in params:
            param_readonly_usage[p.name] = True
        param_names = {p.name for p in params}

        def check_expr_readonly(expr: Expr) -> bool:
            """Check if an expression involves mutating any parameter."""
            if isinstance(expr, IdentifierExpr):
                if expr.name in param_names:
                    sym = self.symbols.lookup(expr.name)
                    if sym is not None and has_mutable_modifier(sym.resolved_type):
                        return False
                return True
            if isinstance(expr, CallExpr):
                for arg in expr.args:
                    if not check_expr_readonly(arg):
                        return False
                return True
            if isinstance(expr, BinaryExpr):
                return check_expr_readonly(expr.left) and check_expr_readonly(expr.right)
            if isinstance(expr, UnaryExpr):
                return check_expr_readonly(expr.operand)
            if isinstance(expr, FieldExpr):
                return check_expr_readonly(expr.base)
            if isinstance(expr, ListLiteral):
                return all(check_expr_readonly(e) for e in expr.elements)
            return True

        for stmt in body:
            if not self._check_stmt_readonly(stmt, param_names):
                for p in params:
                    param_readonly_usage[p.name] = False

        result: dict[str, Type] = {}
        for p, pty in zip(params, param_types):
            if param_readonly_usage.get(p.name, False):
                result[p.name] = BorrowType(pty)
        return result

    def _check_stmt_readonly(self, stmt: Stmt, param_names: set[str]) -> bool:
        """Check if a statement only uses parameters in read-only mode."""
        from prove.ast_nodes import Assignment, VarDecl

        if isinstance(stmt, Assignment):
            if stmt.target in param_names:
                return False
            return True
        if isinstance(stmt, VarDecl):
            return True
        if isinstance(stmt, ExprStmt):
            return True
        if isinstance(stmt, MatchExpr):
            return True
        return True

    def _check_expr_readonly(self, expr: Expr, param_names: set[str]) -> bool:
        """Check if an expression only uses parameters in read-only mode."""
        if isinstance(expr, IdentifierExpr):
            if expr.name in param_names:
                sym = self.symbols.lookup(expr.name)
                if sym is not None and has_mutable_modifier(sym.resolved_type):
                    return False
            return True
        if isinstance(expr, CallExpr):
            return all(self._check_expr_readonly(arg, param_names) for arg in expr.args)
        if isinstance(expr, BinaryExpr):
            return self._check_expr_readonly(expr.left, param_names) and self._check_expr_readonly(
                expr.right, param_names
            )
        if isinstance(expr, FieldExpr):
            return self._check_expr_readonly(expr.base, param_names)
        return True

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

    # ── Unused checks ───────────────────────────────────────────

    def _check_unused(self) -> None:
        """Warn about unused variables in module scope."""
        for sym in self.symbols.current_scope.all_symbols():
            if sym.kind == SymbolKind.VARIABLE and not sym.used:
                self._info("I300", f"unused variable '{sym.name}'", sym.span)

    def _check_unused_imports(self) -> None:
        """I302: warn about imported names that are never referenced."""
        for (module, name), spans in self._import_spans.items():
            if (module, name) not in self._used_imports:
                # Type imports used in type annotations
                if name in self._used_types:
                    continue
                # Symbol marked used via lookup (e.g. unqualified calls)
                sym = self.symbols.lookup(name)
                if sym is not None and sym.used:
                    continue
                for span in spans:
                    self._info(
                        "I302",
                        f"'{name}' is imported from '{module}' but never used.",
                        span,
                    )

    def _check_unused_types(self) -> None:
        """W303: warn about user-defined types that are never referenced."""
        for name, span in self._user_types.items():
            if name not in self._used_types:
                # Skip stdlib types — they may be unused in the user's module
                if span.file.startswith("<stdlib:"):
                    continue
                self._info(
                    "I303",
                    f"Type '{name}' is defined but never used.",
                    span,
                )

    def _check_unused_constants(self) -> None:
        """I304: warn about user-defined constants that are never referenced."""
        for name, span in self._user_constants.items():
            sym = self.symbols.lookup(name)
            if sym is not None and not sym.used:
                self._info(
                    "I304",
                    f"Constant '{name}' is defined but never used.",
                    span,
                )

    # ── Verification chain analysis ──────────────────────────────

    def _check_verification_chains(self, module: Module) -> None:
        """W370/W371: warn when verification chain is broken.

        An unverified function that calls a verified function breaks the
        verification chain — the callee's guarantees don't propagate.
        """
        _IO_VERBS = frozenset({"inputs", "outputs", "streams"})

        # Collect all function definitions
        all_fns: list[FunctionDef] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                all_fns.append(decl)
            elif isinstance(decl, ModuleDecl):
                for item in decl.body:
                    if isinstance(item, FunctionDef):
                        all_fns.append(item)

        # Build verification status for imported functions (from FunctionSignature)
        imported_verified: set[str] = set()
        for (_verb_key, _name_key), sigs in self.symbols.all_functions().items():
            for sig in sigs:
                if sig.module and sig.ensures:
                    imported_verified.add(sig.name)

        for fd in all_fns:
            status = self._verification_status.get(fd.name, "unverified")
            if status != "unverified":
                continue  # verified or trusted — no warning

            # Skip exceptions: main-like, IO verbs
            if fd.verb in _IO_VERBS:
                continue

            # Walk body to find calls to verified functions
            call_targets = _extract_call_targets(fd.body)
            for callee_name, call_span in call_targets:
                callee_status = self._verification_status.get(callee_name)
                callee_is_verified = callee_status == "verified" or (
                    callee_status is None and callee_name in imported_verified
                )
                if not callee_is_verified:
                    continue

                # Choose warning level
                is_public = not fd.name.startswith("_")
                if is_public:
                    self._warning(
                        "W370",
                        f"function '{fd.name}' calls verified function "
                        f"'{callee_name}' but has no `ensures` clause "
                        f"— verification chain broken",
                        call_span,
                    )
                elif self._strict:
                    self._warning(
                        "W371",
                        f"internal function '{fd.name}' calls verified "
                        f"function '{callee_name}' but has no `ensures` "
                        f"clause — verification chain broken",
                        call_span,
                    )
                # Only warn once per function (first chain break found)
                break

    # ── Domain profile enforcement ─────────────────────────────

    def _check_domain_profiles(self, module: Module) -> None:
        """Apply domain-specific warnings based on the module's domain: tag."""
        from prove.domains import get_domain_profile

        mod_decl: ModuleDecl | None = None
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                mod_decl = decl
                break
        if mod_decl is None or mod_decl.domain is None:
            return

        profile = get_domain_profile(mod_decl.domain)
        if profile is None:
            self._warning(
                "W340",
                f"unknown domain '{mod_decl.domain}'; known domains: finance, safety, general",
                mod_decl.span,
            )
            return

        # Check functions for domain requirements
        for decl in module.declarations:
            if not isinstance(decl, FunctionDef):
                continue
            if decl.trusted is not None:
                continue  # trusted functions opt out

            # Check preferred types (e.g. Float → Decimal in finance)
            for param in decl.params:
                if param.type_expr is not None:
                    self._check_domain_type(param.type_expr, profile, decl.span)

            # Check required contracts
            if "ensures" in profile.required_contracts and not decl.ensures:
                self._warning(
                    "W341",
                    f"domain '{profile.name}' requires ensures contract on '{decl.name}'",
                    decl.span,
                )
            if "requires" in profile.required_contracts and not decl.requires:
                self._warning(
                    "W341",
                    f"domain '{profile.name}' requires requires contract on '{decl.name}'",
                    decl.span,
                )

            # Check required annotations
            if "near_miss" in profile.required_annotations and not decl.near_misses:
                self._warning(
                    "W342",
                    f"domain '{profile.name}' requires near_miss examples on '{decl.name}'",
                    decl.span,
                )
            if "terminates" in profile.required_annotations and decl.terminates is None:
                # Only warn for recursive functions (non-recursive don't need terminates)
                pass
            if "explain" in profile.required_annotations and decl.explain is None:
                self._warning(
                    "W342",
                    f"domain '{profile.name}' requires explain block on '{decl.name}'",
                    decl.span,
                )

    def _check_domain_type(self, type_expr: object, profile: object, span: Span) -> None:
        """Warn if a type is not preferred in the domain profile."""
        from prove.ast_nodes import SimpleType
        from prove.domains import DomainProfile

        assert isinstance(profile, DomainProfile)
        if isinstance(type_expr, SimpleType):
            alt = profile.preferred_types.get(type_expr.name)
            if alt:
                self._warning(
                    "W340",
                    f"domain '{profile.name}' prefers {alt} over {type_expr.name}",
                    span,
                )

    # ── Coherence checking ────────────────────────────────────

    def _check_coherence(self, module: Module) -> None:
        """Check vocabulary consistency between narrative and code names."""
        mod_decl: ModuleDecl | None = None
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                mod_decl = decl
                break

        # Extract vocabulary from narrative (words >= 3 chars, lowercased)
        if mod_decl is not None and mod_decl.narrative is not None:
            narrative_words = set()
            for word in mod_decl.narrative.split():
                clean = word.strip(".,;:!?()[]{}\"'").lower()
                if len(clean) >= 3:
                    narrative_words.add(clean)

            if narrative_words:
                # I340: function names against narrative vocabulary
                for decl in module.declarations:
                    if not isinstance(decl, FunctionDef):
                        continue
                    name_parts = set(decl.name.lower().split("_"))
                    name_parts.discard("")
                    if not name_parts or all(len(p) < 3 for p in name_parts):
                        continue
                    if not name_parts & narrative_words:
                        self._info(
                            "I340",
                            f"function '{decl.name}' uses vocabulary not found in module narrative",
                            decl.span,
                        )

        # W501-W502: prose coherence checks (coherence-flag only)
        fns = [d for d in module.declarations if isinstance(d, FunctionDef)]

        # W343: narrative flow step verification
        if mod_decl is not None and mod_decl.narrative is not None:
            self._check_narrative_flow_steps(mod_decl, fns)
        if mod_decl is not None:
            self._check_narrative_verb_coherence(mod_decl, fns)
        for fd in fns:
            self._check_explain_body_coherence(fd)
        # W503-W506 are always active — already fired per-function in _check_function
