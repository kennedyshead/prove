"""Two-pass semantic analyzer for the Prove language.

Pass 1: Register all top-level declarations (types, functions, constants, imports).
Pass 2: Check each declaration body (type inference, verb enforcement, exhaustiveness).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from prove._check_calls import CallCheckMixin
from prove._check_contracts import ContractCheckMixin, _match_arms_have_fail_prop
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
    EffectType,
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
    find_recursive_fields,
    get_scale,
    has_mutable_modifier,
    has_own_modifier,
    numeric_widen,
    type_name,
    types_compatible,
)
from prove.verb_defs import (
    ASYNC_VERBS,
    BLOCKING_VERBS,
    FAILABLE_PURE_VERBS,
    NON_ALLOCATING_VERBS,
    PURE_VERBS,
    VERBS_NEED_OWNERSHIP,
)


def _count_decimal_places(literal: str) -> int:
    """Count decimal places in a numeric literal string like '3.14159'."""
    if "." in literal:
        return len(literal.split(".")[1].rstrip("0") or "0")
    return 0


# Verb classification sets are imported from prove.verb_defs.
# Local aliases with leading underscores for backward compat within this file.
_PURE_VERBS = PURE_VERBS
_FAILABLE_PURE_VERBS = FAILABLE_PURE_VERBS
_NON_ALLOCATING_VERBS = NON_ALLOCATING_VERBS
_ASYNC_VERBS = ASYNC_VERBS
_BLOCKING_VERBS = BLOCKING_VERBS
_VERBS_NEED_OWNERSHIP = VERBS_NEED_OWNERSHIP

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


class Checker(TypeCheckMixin, CallCheckMixin, ContractCheckMixin):
    """Semantic analyzer for a single module."""

    def __init__(
        self,
        local_modules: dict[str, object] | None = None,
        project_dir: Path | None = None,
        package_modules: dict[str, object] | None = None,
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
        # Types forward-declared for recursive resolution (skip E301 duplicate check)
        self._forward_declared_types: set[str] = set()
        # Track user-defined constant names and their spans for I304
        self._user_constants: dict[str, Span] = {}
        self._verb_list_arities: dict[str, int] = {}  # List<Verb> constant → expected arity
        # Requires-based narrowing: list of (module, args)
        self._requires_narrowings: list[tuple[str, list[Expr]]] = []
        # Parameters guaranteed non-empty via requires length(x) > 0
        self._nonempty_lists: set[str] = set()
        # Inferred types for untyped VarDecl nodes: (start_line, start_col) -> type_name
        self.inlay_type_map: dict[tuple[int, int], str] = {}
        # Mutation survivors from previous --mutate runs
        self._survivors: list[dict] = []
        if project_dir:
            from prove.mutator import load_survivors

            self._survivors = load_survivors(project_dir)
        # Local (sibling) module info for cross-file imports
        self._local_modules = local_modules
        # Package module info for package imports
        self._package_modules = package_modules
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
        # HOF param types: set before inferring a lambda in a HOF call so
        # _infer_lambda can assign concrete types instead of TypeVariable.
        self._hof_param_types: list[Type] | None = None
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
            elif not mod_decls[0].name or not mod_decls[0].name[0].isupper():
                self._error(
                    "E210",
                    "module declaration requires a name (e.g. `module MyModule`)",
                    mod_decls[0].span,
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
                # Forward-declare all type names (enables self/mutual recursion)
                for td in decl.types:
                    self._forward_declare_type(td)
                for td in decl.types:
                    self._register_type(td)
                # Validate recursive types have base cases
                self._validate_recursive_base_cases(decl.types)
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
        _cursor_ty = PrimitiveType("Cursor")
        self._builtin_extra_types: dict[tuple[str, int], frozenset[Type]] = {
            ("len", 0): frozenset({STRING}),
            ("map", 0): frozenset({_cursor_ty}),
            ("each", 0): frozenset({_cursor_ty}),
            ("filter", 0): frozenset({_cursor_ty}),
            ("reduce", 0): frozenset({_cursor_ty}),
            ("all", 0): frozenset({_cursor_ty}),
            ("any", 0): frozenset({_cursor_ty}),
            ("find", 0): frozenset({_cursor_ty}),
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
                "all",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], BOOLEAN),
                ],
                BOOLEAN,
            ),
            (
                "any",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], BOOLEAN),
                ],
                BOOLEAN,
            ),
            (
                "find",
                [
                    ListType(TypeVariable("Value")),
                    FunctionType([TypeVariable("Value")], BOOLEAN),
                ],
                GenericInstance("Option", [TypeVariable("Value")]),
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

    def _forward_declare_type(self, td: TypeDef) -> None:
        """Forward-declare a type name so self/mutual recursion can resolve."""
        if td.name in _BUILTIN_TYPE_NAMES:
            return  # will be caught by _register_type
        existing = self.symbols.resolve_type(td.name)
        if existing is not None and not isinstance(existing, TypeVariable):
            return  # will be caught by _register_type
        body = td.body
        type_params = tuple(td.type_params)
        if isinstance(body, AlgebraicTypeDef):
            self.symbols.define_type(td.name, AlgebraicType(td.name, [], type_params))
            self._forward_declared_types.add(td.name)
        elif isinstance(body, RecordTypeDef):
            self.symbols.define_type(td.name, RecordType(td.name, {}, type_params))
            self._forward_declared_types.add(td.name)

    def _validate_recursive_base_cases(self, type_defs: list[TypeDef]) -> None:
        """E423: recursive types must have at least one non-recursive variant."""
        # Build the set of all user-defined algebraic type names for mutual recursion detection
        all_type_names = {
            td.name
            for td in type_defs
            if isinstance(self.symbols.resolve_type(td.name), AlgebraicType)
        }
        # Build a dependency graph: type_name → set of type_names it references
        type_refs: dict[str, set[str]] = {}
        for td in type_defs:
            resolved = self.symbols.resolve_type(td.name)
            if not isinstance(resolved, AlgebraicType):
                continue
            rec_fields = find_recursive_fields(resolved, all_type_names - {td.name})
            refs = {td.name}  # self-reference counts
            for rf in rec_fields:
                if rf.direct:
                    # Find which type this field references
                    variant = next(
                        (v for v in resolved.variants if v.name == rf.variant_name), None
                    )
                    if variant and rf.field_name in variant.fields:
                        ft = variant.fields[rf.field_name]
                        if isinstance(ft, AlgebraicType) and ft.name in all_type_names:
                            refs.add(ft.name)
            type_refs[td.name] = refs

        # Find mutual recursion groups (SCCs) and check base cases
        # Simple approach: for each type, find its reachable group
        checked: set[str] = set()
        td_map = {td.name: td for td in type_defs}
        for td in type_defs:
            if td.name in checked:
                continue
            resolved = self.symbols.resolve_type(td.name)
            if not isinstance(resolved, AlgebraicType):
                continue
            rec_fields = find_recursive_fields(resolved, all_type_names - {td.name})
            if not rec_fields:
                continue

            # Compute reachable recursive group from this type
            group = self._compute_recursive_group(td.name, type_refs)
            checked |= group

            # Check: at least one type in the group has a non-recursive base case
            group_has_base = False
            for gname in group:
                gtype = self.symbols.resolve_type(gname)
                if not isinstance(gtype, AlgebraicType):
                    continue
                grecs = find_recursive_fields(gtype, group - {gname})
                rec_variants = {rf.variant_name for rf in grecs if rf.direct}
                if {v.name for v in gtype.variants} - rec_variants:
                    group_has_base = True
                    break
            if not group_has_base:
                for gname in group:
                    if gname in td_map:
                        self._error(
                            "E423",
                            f"recursive type '{gname}' has no base case — "
                            f"at least one variant must not reference '{gname}'",
                            td_map[gname].span,
                        )

    @staticmethod
    def _compute_recursive_group(start: str, refs: dict[str, set[str]]) -> set[str]:
        """Compute the set of types reachable from *start* through recursive refs."""
        group: set[str] = set()
        stack = [start]
        while stack:
            name = stack.pop()
            if name in group:
                continue
            group.add(name)
            for ref in refs.get(name, set()):
                if ref not in group:
                    stack.append(ref)
        return group

    def _register_record_type(self, td: TypeDef, body: RecordTypeDef) -> Type:
        """Register a record type and return the resolved type."""
        type_params = tuple(td.type_params)
        fields: dict[str, Type] = {}
        for f in body.fields:
            ft = self._resolve_type_expr(f.type_expr)
            fields[f.name] = ft
        return RecordType(td.name, fields, type_params)

    def _register_algebraic_type(self, td: TypeDef, body: AlgebraicTypeDef) -> Type:
        """Register an algebraic type with optional inheritance and return the resolved type."""
        type_params = tuple(td.type_params)
        variants: list[VariantInfo] = []
        # Check if first variant is actually a base algebraic type (inheritance)
        inherited_variants: list[VariantInfo] = []
        own_variants_start = 0
        parents: tuple[str, ...] = ()
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
                    parents = (base_type.name,) + base_type.parents
        variants.extend(inherited_variants)
        for v in body.variants[own_variants_start:]:
            vfields: dict[str, Type] = {}
            for f in v.fields:
                vfields[f.name] = self._resolve_type_expr(f.type_expr)
            variants.append(VariantInfo(v.name, vfields))
        resolved = AlgebraicType(td.name, variants, type_params, parents)
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
        return resolved

    def _register_lookup_type(self, td: TypeDef, body: LookupTypeDef) -> Type:
        """Register a lookup type (store-backed or static) and return the resolved type."""
        type_params = tuple(td.type_params)
        if body.is_store_backed:
            # Store-backed lookup: zero variants (dynamic), register schema
            resolved: Type = AlgebraicType(td.name, [], type_params)
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
        return resolved

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
        if (
            existing is not None
            and not isinstance(existing, TypeVariable)
            and td.name not in self._forward_declared_types
        ):
            self._error("E301", f"duplicate definition of '{td.name}'", td.span)
            return

        body = td.body

        if isinstance(body, RecordTypeDef):
            resolved: Type = self._register_record_type(td, body)

        elif isinstance(body, AlgebraicTypeDef):
            resolved = self._register_algebraic_type(td, body)

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
            resolved = self._register_lookup_type(td, body)

        else:
            resolved = ERROR_TY

        self.symbols.define_type(td.name, resolved)
        self._forward_declared_types.discard(td.name)
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

        # I318: module importing from itself (auto-fixed by formatter)
        if self._module_name and imp.module.lower() == self._module_name:
            self._info(
                "I318",
                f"module '{imp.module}' cannot import from itself",
                imp.span,
            )
            return

        # .ModuleName prefix forces local-only resolution
        if getattr(imp, "local", False):
            if self._local_modules and imp.module in self._local_modules:
                self._register_local_import(imp)
            else:
                self._module_imports.setdefault(imp.module, set())
                self._error(
                    "E314",
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
            # Check installed packages
            if self._package_modules and imp.module in self._package_modules:
                self._register_package_import(imp)
                return
            # Register the module name so we know it was declared,
            # but don't add function names — call sites will flag them.
            self._module_imports.setdefault(imp.module, set())
            self._error(
                "E314",
                f"unknown module '{imp.module}'",
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

        # Ambiguity check: local module shadows stdlib module
        if self._local_modules and imp.module in self._local_modules:
            self._error(
                "E316",
                f"module '{imp.module}' is ambiguous: a local module and a stdlib module share "
                f"this name. Use '.{imp.module}' to import the local module.",
                imp.span,
            )

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
                    self._info(
                        "I315",
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
                # Register lookup table definitions for imported lookup types
                from prove.stdlib_loader import load_stdlib_lookup_defs

                lookup_defs = load_stdlib_lookup_defs(imp.module)
                if item.name in lookup_defs:
                    self._lookup_tables[item.name] = lookup_defs[item.name]
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
                # Known stdlib module but function not found — info (auto-removed on format)
                self._info(
                    "I315",
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
                    self._info(
                        "I315",
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
                    # Register lookup tables for imported lookup types
                    if item.name in local_info.lookup_tables:
                        self._lookup_tables[item.name] = local_info.lookup_tables[item.name]
                    # Register variant constructors for algebraic types
                    if isinstance(resolved, AlgebraicType):
                        for vsig in local_info.functions:
                            if vsig.verb is None and any(
                                v.name == vsig.name for v in resolved.variants
                            ):
                                self.symbols.define_function(vsig)
                else:
                    self._info(
                        "I315",
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
                self._info(
                    "I315",
                    f"function '{item.name}' not found in module '{imp.module}'",
                    item.span,
                )

    def _register_package_import(self, imp: ImportDecl) -> None:
        """Register imports from an installed package module."""
        pkg_info = self._package_modules[imp.module]  # type: ignore[index]

        names = self._module_imports.setdefault(imp.module, set())
        for item in imp.items:
            names.add(item.name)
            self._import_spans.setdefault(
                (imp.module.lower(), item.name),
                [],
            ).append(item.span)

        # Build lookup dicts
        pkg_funcs_by_name: dict[str, list[FunctionSignature]] = {}
        for sig in pkg_info.functions:
            pkg_funcs_by_name.setdefault(sig.name, []).append(sig)

        for item in imp.items:
            # Constant imports
            is_const_name = item.verb == "constants" or (
                len(item.name) >= 2
                and all(c.isupper() or c.isdigit() or c == "_" for c in item.name)
            )
            if is_const_name:
                if item.name in pkg_info.constants:
                    resolved = pkg_info.constants[item.name]
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
                    self._info(
                        "I315",
                        f"constant '{item.name}' not found in package module '{imp.module}'",
                        item.span,
                    )
                continue

            # Type imports
            is_type_import = item.verb == "types" or (item.verb is None and item.name[:1].isupper())
            if is_type_import:
                resolved_type = pkg_info.types.get(item.name)
                if resolved_type is not None:
                    self.symbols.define_type(item.name, resolved_type)
                    self.symbols.define(
                        Symbol(
                            name=item.name,
                            kind=SymbolKind.TYPE,
                            resolved_type=resolved_type,
                            span=item.span,
                            verb=item.verb,
                            is_imported=True,
                        )
                    )
                    # Register variant constructors for algebraic types
                    if isinstance(resolved_type, AlgebraicType):
                        for vi in resolved_type.variants:
                            vsig = FunctionSignature(
                                verb=None,
                                name=vi.name,
                                param_names=list(vi.fields.keys()),
                                param_types=list(vi.fields.values()),
                                return_type=resolved_type,
                                can_fail=False,
                                span=item.span,
                                requires=[],
                            )
                            self.symbols.define_function(vsig)
                else:
                    self._info(
                        "I315",
                        f"type '{item.name}' not found in package module '{imp.module}'",
                        item.span,
                    )
                continue

            # Function imports — register all verb overloads
            sigs = pkg_funcs_by_name.get(item.name, [])
            if sigs:
                for sig in sigs:
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
            else:
                self._info(
                    "I315",
                    f"function '{item.name}' not found in package module '{imp.module}'",
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

    # ── _check_function helpers ─────────────────────────────────

    def _setup_function_params(self, fd: FunctionDef) -> list:
        """Register parameters, infer borrows, apply With constraints."""
        param_types = [self._resolve_type_expr(p.type_expr) for p in fd.params]

        # Infer borrows for non-pure verbs that don't need ownership (e.g. renders).
        # Pure verbs are implicitly borrowing — the emitter handles this via
        # the verb classification, no BorrowType wrapper needed.
        if fd.verb not in _VERBS_NEED_OWNERSHIP and fd.verb not in _PURE_VERBS:
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

        return param_types

    def _setup_function_scope(self, fd: FunctionDef) -> bool:
        """Set up requires narrowings, implicit variables for renders/listens.

        Returns True if function is binary (caller should early-exit).
        """
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

        # Narrow Option<T> → T for requires unit(x) == false
        for req_expr in fd.requires:
            self._narrow_unit_false(req_expr)

        # Track non-empty list params via requires length(x) > 0
        self._nonempty_lists = self._collect_nonempty_lists(fd)

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
            return True

        return False

    def _check_function_annotations(
        self, fd: FunctionDef, return_type: "Type", param_types: list, body_type: "Type"
    ) -> None:
        """Check contracts, intent prose, explain conditions, recursion, proof verification."""
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

    def _finalize_function_check(self, fd: FunctionDef) -> None:
        """Mutation testing, survivor warnings, unused vars, scope cleanup."""
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
        self._nonempty_lists = set()

    # ── _check_function (dispatcher) ─────────────────────────────

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

        # Phase 1: Register parameters, infer borrows, apply With constraints
        param_types = self._setup_function_params(fd)

        # Phase 2: Set up scope (requires narrowings, implicit vars, verb rules)
        if self._setup_function_scope(fd):
            return  # binary function — early exit

        # I210: listens/streams/renders body must be a single match expression
        if fd.verb in ("listens", "streams", "renders") and fd.body:
            is_single_match = (
                len(fd.body) == 1
                and isinstance(fd.body[0], (ExprStmt, MatchExpr))
                and (
                    isinstance(fd.body[0], MatchExpr)
                    or (isinstance(fd.body[0], ExprStmt) and isinstance(fd.body[0].expr, MatchExpr))
                )
            )
            if not is_single_match:
                self._info(
                    "I210",
                    f"`{fd.verb}` body should be a single match expression",
                    fd.span,
                )

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
            # Body must return Boolean (or compatible)
            if not isinstance(body_type, ErrorType) and not types_compatible(BOOLEAN, body_type):
                self._error(
                    "E322",
                    f"validates body must return Boolean, got '{type_name(body_type)}'",
                    fd.span,
                )
        elif (
            fd.verb not in ("renders", "listens")
            and not isinstance(body_type, ErrorType)
            and not types_compatible(return_type, body_type)
        ):
            # For failable functions, body can return the success type
            # or the error type (via Error("message") constructor)
            # e.g. Result<Integer, Error>! function body can return Integer or Error
            success_compatible = False
            if fd.can_fail and isinstance(return_type, GenericInstance):
                if return_type.base_name == "Result" and return_type.args:
                    success_compatible = types_compatible(return_type.args[0], body_type) or (
                        len(return_type.args) > 1
                        and types_compatible(return_type.args[1], body_type)
                    )
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

        # Phase 3: Check annotations (contracts, intent, explain, recursion, proofs)
        self._check_function_annotations(fd, return_type, param_types, body_type)

        # Phase 4: Finalize (mutation testing, survivors, unused vars, scope cleanup)
        self._finalize_function_check(fd)

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
            # E402: List<Verb> constants — check all functions have consistent
            # arity AND parameter types (mismatched types cause SIGSEGV at runtime).
            if (
                isinstance(expected, ListType)
                and isinstance(expected.element, PrimitiveType)
                and expected.element.name == "Verb"
                and isinstance(cd.value, ListLiteral)
            ):
                verb_sigs: list[tuple[str, FunctionSignature]] = []
                for elem in cd.value.elements:
                    if isinstance(elem, IdentifierExpr):
                        sig = self.symbols.resolve_function_any(elem.name)
                        if sig:
                            verb_sigs.append((elem.name, sig))
                if len(verb_sigs) >= 2:
                    ref_name, ref_sig = verb_sigs[0]
                    ref_arity = len(ref_sig.param_types)
                    for fn_name, fn_sig in verb_sigs[1:]:
                        fn_arity = len(fn_sig.param_types)
                        if fn_arity != ref_arity:
                            self._error(
                                "E402",
                                f"List<Verb> arity mismatch: '{ref_name}' has "
                                f"{ref_arity} params but '{fn_name}' has {fn_arity}",
                                cd.span,
                            )
                        else:
                            for i, (pt_ref, pt_fn) in enumerate(
                                zip(ref_sig.param_types, fn_sig.param_types)
                            ):
                                if not types_compatible(pt_ref, pt_fn):
                                    pos = {0: "1st", 1: "2nd", 2: "3rd"}.get(i, f"{i + 1}th")
                                    self._error(
                                        "E402",
                                        f"List<Verb> param type mismatch: "
                                        f"{pos} param is '{type_name(pt_ref)}' in "
                                        f"'{ref_name}' but '{type_name(pt_fn)}' in "
                                        f"'{fn_name}'",
                                        cd.span,
                                    )
                # Store verb arity for call-site checking
                if verb_sigs:
                    self._verb_list_arities[cd.name] = len(verb_sigs[0][1].param_types)

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

    def _narrow_unit_false(self, expr: Expr) -> None:
        """Narrow Option<T> → T when requires contains unit(x) == false.

        Also handles &&-conjunctions so that
        ``requires unit(a) == false && unit(b) == false``
        narrows both *a* and *b*.
        """
        if isinstance(expr, BinaryExpr) and expr.op == "&&":
            self._narrow_unit_false(expr.left)
            self._narrow_unit_false(expr.right)
            return
        if not (isinstance(expr, BinaryExpr) and expr.op == "=="):
            return
        # unit(x) == false  OR  false == unit(x)
        call, lit = expr.left, expr.right
        if isinstance(lit, CallExpr) and isinstance(call, BooleanLit):
            call, lit = lit, call
        if not (
            isinstance(call, CallExpr)
            and isinstance(call.func, IdentifierExpr)
            and call.func.name == "unit"
            and len(call.args) == 1
            and isinstance(lit, BooleanLit)
            and lit.value is False
        ):
            return
        arg = call.args[0]
        if not isinstance(arg, IdentifierExpr):
            return
        sym = self.symbols.lookup(arg.name)
        if (
            sym is not None
            and isinstance(sym.resolved_type, GenericInstance)
            and sym.resolved_type.base_name == "Option"
            and sym.resolved_type.args
        ):
            sym.resolved_type = sym.resolved_type.args[0]

    def _collect_nonempty_lists(self, fd: FunctionDef) -> set[str]:
        """Scan requires for length(x) > 0 patterns.

        Returns the set of parameter names guaranteed to be non-empty,
        so that first(x)/last(x) can narrow Option<T> → T.
        """
        result: set[str] = set()
        exprs: list[Expr] = []
        for req_expr in fd.requires:
            stack = [req_expr]
            while stack:
                e = stack.pop()
                if isinstance(e, BinaryExpr) and e.op == "&&":
                    stack.append(e.left)
                    stack.append(e.right)
                else:
                    exprs.append(e)
        for expr in exprs:
            if not isinstance(expr, BinaryExpr):
                continue
            # length(x) > 0  or  length(x) >= 1
            call, lit, op = None, None, expr.op
            if op in (">", ">="):
                call, lit = expr.left, expr.right
            elif op in ("<", "<="):
                call, lit = expr.right, expr.left
                op = ">" if op == "<" else ">="
            else:
                continue
            if not (
                isinstance(call, CallExpr)
                and isinstance(call.func, IdentifierExpr)
                and call.func.name == "length"
                and len(call.args) == 1
                and isinstance(call.args[0], IdentifierExpr)
                and isinstance(lit, IntegerLit)
            ):
                continue
            threshold = int(lit.value)
            if (op == ">" and threshold >= 0) or (op == ">=" and threshold >= 1):
                result.add(call.args[0].name)
        return result

    # ── Verb enforcement ────────────────────────────────────────

    def _check_verb_rules(self, fd: FunctionDef) -> None:
        """Enforce verb purity constraints."""
        verb = fd.verb
        if verb in _PURE_VERBS:
            # Pure functions cannot be failable (except transforms which can fail)
            if fd.can_fail and verb not in _FAILABLE_PURE_VERBS:
                self._error("E361", "pure function cannot be failable", fd.span)
            # Non-allocating pure verbs cannot take Mutable params —
            # Mutable allows in-place mutation which violates purity.
            if verb in _NON_ALLOCATING_VERBS:
                for p in fd.params:
                    pt = self._resolve_type_expr(p.type_expr)
                    if has_mutable_modifier(pt):
                        self._error(
                            "E437",
                            f"`{verb}` verb cannot accept Mutable parameters "
                            f"— pure verbs must not mutate their inputs",
                            p.span,
                        )
            # derives returning a heap type (String, List, Record, etc.)
            # that calls creates/transforms is misclassified — the
            # function allocates from the caller's perspective.
            # Skip for validates (always returns Boolean) and matches.
            if verb == "derives" and fd.return_type is not None:
                ret_ty = self._resolve_type_expr(fd.return_type)
                if self._is_heap_type(ret_ty) and self._body_allocates(fd.body):
                    self._info(
                        "I438",
                        f"`derives` function '{fd.name}' returns heap type "
                        f"'{type_name(ret_ty)}' and allocates "
                        f"— use `creates` instead",
                        fd.span,
                    )
            # Check body for IO calls
            self._check_pure_body(fd.body, fd.span)

        # Verb precision suggestions for pure verbs
        if verb == "creates" and not fd.binary:
            if not self._body_allocates(fd.body):
                self._info(
                    "I439",
                    f"`creates` function '{fd.name}' does not allocate — use `derives` instead",
                    fd.span,
                )
        if verb == "transforms" and not fd.binary:
            if not fd.can_fail and not self._body_calls_failable(fd.body):
                if self._body_allocates(fd.body):
                    self._info(
                        "I440",
                        f"`transforms` function '{fd.name}' is not failable "
                        f"— use `creates` instead",
                        fd.span,
                    )
                else:
                    self._info(
                        "I440",
                        f"`transforms` function '{fd.name}' is not failable "
                        f"and does not allocate — use `derives` instead",
                        fd.span,
                    )

        # matches/dispatches verb: first parameter must be a matchable type
        if verb in ("matches", "dispatches"):
            if fd.params:
                first_type = self._resolve_type_expr(fd.params[0].type_expr)
                is_matchable = (
                    isinstance(first_type, (AlgebraicType, ErrorType))
                    or (
                        isinstance(first_type, PrimitiveType)
                        and first_type.name in ("String", "Integer", "Boolean")
                    )
                    or (
                        isinstance(first_type, GenericInstance)
                        and first_type.base_name in ("Result", "Option")
                    )
                )
                if not is_matchable:
                    self._error(
                        "E365",
                        f"{verb} verb requires first parameter to be "
                        f"a matchable type (algebraic, String, Integer, "
                        f"or Boolean), got '{type_name(first_type)}'",
                        fd.params[0].span,
                    )
            else:
                self._error(
                    "E365",
                    f"{verb} verb requires at least one parameter",
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
        # IO verbs with requires must be failable or return Option
        if fd.requires and verb in ("inputs", "outputs", "dispatches"):
            ret = self._resolve_type_expr(fd.return_type) if fd.return_type else None
            is_option = isinstance(ret, GenericInstance) and ret.base_name == "Option"
            if not fd.can_fail and not is_option:
                self._error(
                    "E436",
                    f"`{verb}` with `requires` must be failable (!) or "
                    f"return Option<T> so the contract can be enforced at runtime",
                    fd.span,
                )

        # I367: suggest extracting match to a matches verb function
        # listens/streams/renders bodies are inherently match-based, so exempt
        if verb not in ("matches", "dispatches", "listens", "streams", "renders"):
            self._check_match_restriction(fd.body, fd.span, verb)

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

    # ── Verb precision helpers ──────────────────────────────────

    _STACK_PRIMITIVES = frozenset(
        {
            "Integer",
            "Float",
            "Decimal",
            "Boolean",
            "Character",
            "Byte",
        }
    )

    def _is_heap_type(self, ty: Type) -> bool:
        """True if the type is heap-allocated (pointer in C)."""
        if isinstance(ty, PrimitiveType):
            return ty.name not in self._STACK_PRIMITIVES
        # Records, generics (List, Option, Result), etc. are all heap
        return True

    # AST nodes that allocate heap memory (strings, lists, records).
    _HEAP_LITERAL_TYPES = (
        StringLit,
        TripleStringLit,
        RawStringLit,
        PathLit,
        RegexLit,
        StringInterp,
        ListLiteral,
    )

    def _body_allocates(self, body: list[Stmt | MatchExpr]) -> bool:
        """Conservative check: does the body contain allocating expressions?"""
        return any(self._stmt_allocates(s) for s in body)

    def _stmt_allocates(self, stmt: Stmt | MatchExpr) -> bool:
        if isinstance(stmt, VarDecl):
            return self._expr_allocates(stmt.value)
        if isinstance(stmt, Assignment):
            return self._expr_allocates(stmt.value)
        if isinstance(stmt, ExprStmt):
            return self._expr_allocates(stmt.expr)
        if isinstance(stmt, MatchExpr):
            if stmt.subject and self._expr_allocates(stmt.subject):
                return True
            return any(self._stmt_allocates(s) for arm in stmt.arms for s in arm.body)
        return False

    def _expr_allocates(self, expr: Expr) -> bool:
        if isinstance(expr, self._HEAP_LITERAL_TYPES):
            return True
        if isinstance(expr, TypeIdentifierExpr):
            # Record constructor — allocates a new record
            return True
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, TypeIdentifierExpr):
                return True  # Record/variant constructor call
            if isinstance(expr.func, IdentifierExpr):
                sig = self.symbols.resolve_function_any(expr.func.name)
                if sig and sig.verb in ("creates", "transforms"):
                    return True
            return any(self._expr_allocates(a) for a in expr.args)
        if isinstance(expr, BinaryExpr):
            # String concatenation allocates — conservatively flag + with
            # string literal operands (full type inference not available here).
            if expr.op == "+" and (
                isinstance(expr.left, (StringLit, StringInterp, TripleStringLit))
                or isinstance(expr.right, (StringLit, StringInterp, TripleStringLit))
            ):
                return True
            return self._expr_allocates(expr.left) or self._expr_allocates(expr.right)
        if isinstance(expr, UnaryExpr):
            return self._expr_allocates(expr.operand)
        if isinstance(expr, PipeExpr):
            return self._expr_allocates(expr.left) or self._expr_allocates(expr.right)
        if isinstance(expr, FailPropExpr):
            return self._expr_allocates(expr.expr)
        if isinstance(expr, MatchExpr):
            if expr.subject and self._expr_allocates(expr.subject):
                return True
            return any(self._stmt_allocates(s) for arm in expr.arms for s in arm.body)
        return False

    def _body_calls_failable(self, body: list[Stmt | MatchExpr]) -> bool:
        """Check if any call in the body targets a failable function."""
        return any(self._stmt_calls_failable(s) for s in body)

    def _stmt_calls_failable(self, stmt: Stmt | MatchExpr) -> bool:
        if isinstance(stmt, VarDecl):
            return self._expr_calls_failable(stmt.value)
        if isinstance(stmt, Assignment):
            return self._expr_calls_failable(stmt.value)
        if isinstance(stmt, ExprStmt):
            return self._expr_calls_failable(stmt.expr)
        if isinstance(stmt, MatchExpr):
            if stmt.subject and self._expr_calls_failable(stmt.subject):
                return True
            return any(self._stmt_calls_failable(s) for arm in stmt.arms for s in arm.body)
        return False

    def _expr_calls_failable(self, expr: Expr) -> bool:
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                sig = self.symbols.resolve_function_any(expr.func.name)
                if sig and sig.can_fail:
                    return True
            return any(self._expr_calls_failable(a) for a in expr.args)
        if isinstance(expr, FailPropExpr):
            return True  # ! operator implies failable context
        if isinstance(expr, BinaryExpr):
            return self._expr_calls_failable(expr.left) or self._expr_calls_failable(expr.right)
        if isinstance(expr, UnaryExpr):
            return self._expr_calls_failable(expr.operand)
        if isinstance(expr, PipeExpr):
            return self._expr_calls_failable(expr.left) or self._expr_calls_failable(expr.right)
        if isinstance(expr, MatchExpr):
            if expr.subject and self._expr_calls_failable(expr.subject):
                return True
            return any(self._stmt_calls_failable(s) for arm in expr.arms for s in arm.body)
        return False

    # ── Match restriction (I367) ────────────────────────────────

    def _check_match_restriction(
        self,
        body: list[Stmt | MatchExpr],
        span: Span,
        verb: str,
    ) -> None:
        """I367: suggest extracting match to a 'matches'/'dispatches' verb function."""
        target = "matches" if verb in _PURE_VERBS else "dispatches"
        for stmt in body:
            if isinstance(stmt, MatchExpr):
                if len(stmt.arms) >= 3 and not _match_arms_have_fail_prop(stmt):
                    self._info(
                        "I367",
                        f"consider extracting match to a '{target}' verb function for better code flow",  # noqa: E501
                        stmt.span,
                    )
            elif isinstance(stmt, VarDecl):
                self._check_match_in_expr(stmt.value, target)
            elif isinstance(stmt, Assignment):
                self._check_match_in_expr(stmt.value, target)
            elif isinstance(stmt, FieldAssignment):
                self._check_match_in_expr(stmt.value, target)
            elif isinstance(stmt, ExprStmt):
                self._check_match_in_expr(stmt.expr, target)

    def _check_match_in_expr(self, expr: Expr, target: str) -> None:
        """Walk an expression looking for MatchExpr nodes."""
        if isinstance(expr, MatchExpr):
            if len(expr.arms) >= 3 and not _match_arms_have_fail_prop(expr):
                self._info(
                    "I367",
                    f"consider extracting match to a '{target}' verb function for better code flow",
                    expr.span,
                )
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._check_match_in_expr(arg, target)
        elif isinstance(expr, BinaryExpr):
            self._check_match_in_expr(expr.left, target)
            self._check_match_in_expr(expr.right, target)
        elif isinstance(expr, UnaryExpr):
            self._check_match_in_expr(expr.operand, target)
        elif isinstance(expr, PipeExpr):
            self._check_match_in_expr(expr.left, target)
            self._check_match_in_expr(expr.right, target)
        elif isinstance(expr, LambdaExpr):
            self._check_match_in_expr(expr.body, target)
        elif isinstance(expr, FailPropExpr):
            self._check_match_in_expr(expr.expr, target)
        elif isinstance(expr, AsyncCallExpr):
            self._check_match_in_expr(expr.expr, target)

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
                    # Diagnostic creates functions (exxx, ixxx, wxxx) have
                    # side effects despite being declared as pure 'creates'.
                    if sig.module == "diagnostic":
                        return
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
                # Auto-unwrap: Option<T> → T when the function has requires
                # contracts. The contracts are the proof that the Option is
                # always Some (compiler-first principle: requires are proofs).
                has_requires = (
                    self._current_function
                    and isinstance(self._current_function, FunctionDef)
                    and self._current_function.requires
                )
                if (
                    has_requires
                    and isinstance(inferred, GenericInstance)
                    and inferred.base_name == "Option"
                    and inferred.args
                    and types_compatible(expected, inferred.args[0])
                ):
                    pass  # auto-unwrap — requires contract is the proof
                # Allow StoreTable → store-backed lookup type assignment
                elif not (
                    getattr(expected, "name", "") in self._store_lookup_types
                    and getattr(inferred, "name", "") == "StoreTable"
                ):
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
            old_expected = self._expected_type
            self._expected_type = expected_type
            try:
                return self._infer_expr_inner(expr)
            finally:
                self._expected_type = old_expected
        return self._infer_expr_inner(expr)

    def _infer_expr_inner(self, expr: Expr) -> Type:
        """Inner expression type inference dispatch."""
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
            return self._infer_list(expr, expected_type=self._expected_type)
        if isinstance(expr, IdentifierExpr):
            return self._infer_identifier(expr)
        if isinstance(expr, TypeIdentifierExpr):
            return self._infer_type_identifier(expr)
        if isinstance(expr, BinaryExpr):
            return self._infer_binary(expr)
        if isinstance(expr, UnaryExpr):
            return self._infer_unary(expr)
        if isinstance(expr, CallExpr):
            return self._infer_call(expr, expected_type=self._expected_type)
        if isinstance(expr, FieldExpr):
            return self._infer_field(expr)
        if isinstance(expr, PipeExpr):
            return self._infer_pipe(expr)
        if isinstance(expr, FailPropExpr):
            return self._infer_fail_prop(expr, expected_type=self._expected_type)
        if isinstance(expr, AsyncCallExpr):
            return self._infer_async_call(expr, expected_type=self._expected_type)
        if isinstance(expr, MatchExpr):
            return self._infer_match(expr, expected_type=self._expected_type)
        if isinstance(expr, LambdaExpr):
            return self._infer_lambda(expr)
        if isinstance(expr, IndexExpr):
            return self._infer_index(expr)
        if isinstance(expr, ValidExpr):
            # valid all/any(list, pred) → HOF builtin, not a validates function
            if expr.name in ("all", "any") and expr.args is not None and len(expr.args) == 2:
                # Infer args to check types but return Boolean directly
                for a in expr.args:
                    self._infer_expr(a)
                return BOOLEAN
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
                if sig is not None and sig.verb != "validates":
                    self._error(
                        "E321",
                        f"'{'invalid' if expr.negated else 'valid'}' requires a validates"
                        f" function, but '{expr.name}' is declared as '{sig.verb}'",
                        expr.span,
                    )
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
            # E403: fail propagation inside coroutine body generates invalid
            # C (return in void function). Use match Ok/Err instead.
            if isinstance(self._current_function, FunctionDef) and self._current_function.verb in (
                "attached",
                "listens",
                "renders",
            ):
                self._error(
                    "E403",
                    f"fail propagation `!` not allowed in '{self._current_function.verb}' "
                    f"function — use `match Ok/Err` to handle errors explicitly",
                    expr.span,
                )

        # The inner expression must be a failable (Result-returning or Fail-effected) call
        if (
            not isinstance(inner, ErrorType)
            and not (isinstance(inner, GenericInstance) and inner.base_name == "Result")
            and not (isinstance(inner, EffectType) and "Fail" in inner.effects)
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

        # The inner expression should be Result-like or Fail-effected; return its success type
        if isinstance(inner, GenericInstance) and inner.base_name == "Result":
            if inner.args:
                return inner.args[0]
        if isinstance(inner, EffectType) and "Fail" in inner.effects:
            return inner.base
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
            and self._current_function.verb
            in ("matches", "dispatches", "listens", "streams", "renders")
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
            elif isinstance(subject_type, PrimitiveType) and subject_type.name in (
                "String",
                "Integer",
                "Float",
                "Decimal",
            ):
                # Infinite-domain types require a default arm to be exhaustive.
                # Boolean is excluded (true/false covers all cases).
                # Skip if arms use Option patterns (Some/None) — the subject
                # may be auto-wrapped or the function may return Option<T>.
                has_default = any(
                    isinstance(arm.pattern, (WildcardPattern, BindingPattern)) for arm in expr.arms
                )
                has_option_patterns = any(
                    isinstance(arm.pattern, VariantPattern) and arm.pattern.name in ("Some", "None")
                    for arm in expr.arms
                )
                if not has_default and not has_option_patterns:
                    self._error(
                        "E401",
                        f"non-exhaustive match on '{subject_type.name}': add a default `_ =>` arm",
                        expr.span,
                    )

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
        # Boolean matches (true/false) are effectively if/else — don't count
        # them for I305 single-arm usage tracking.
        is_bool_match = subject_type is BOOLEAN
        for arm in expr.arms:
            self.symbols.push_scope("match_arm")
            self._check_pattern(arm.pattern, subject_type)
            arm_type = UNIT
            self._match_arm_id += 1
            if not is_bool_match:
                self._match_arm_depth += 1
            for stmt in arm.body:
                arm_type = self._check_stmt(stmt)  # type: ignore[assignment]
            if not is_bool_match:
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
                # Check if function return is Option<T> — mixed T/Unit arms
                # are valid (T auto-wraps to Some, Unit becomes None).
                fn_ret: Type | None = None
                if (
                    self._current_function
                    and isinstance(self._current_function, FunctionDef)
                    and self._current_function.return_type
                ):
                    fn_ret = self._resolve_type_expr(self._current_function.return_type)
                is_option_ret = (
                    isinstance(fn_ret, GenericInstance)
                    and fn_ret.base_name == "Option"
                    and fn_ret.args
                    and types_compatible(fn_ret.args[0], value_type)
                )
                if is_option_ret:
                    result_type = fn_ret  # type: ignore[assignment]
                else:
                    result_type = value_type
                    for arm_type, arm in arm_types:  # type: ignore
                        # Skip error/absent path arms — Err and None arms
                        # in Result/Option matches naturally return different types.
                        if isinstance(arm.pattern, VariantPattern) and arm.pattern.name in (
                            "Err",
                            "None",
                        ):
                            continue
                        if isinstance(arm_type, UnitType):
                            self._error(
                                "E400",
                                f"match arm returns Unit but other arms return "
                                f"'{type_name(value_type)}'",
                                arm.span,
                            )
                        elif not isinstance(arm_type, ErrorType) and not types_compatible(
                            value_type, arm_type
                        ):
                            self._error(
                                "E400",
                                f"match arm returns '{type_name(arm_type)}' "
                                f"but other arms return '{type_name(value_type)}'",
                                arm.span,
                            )

        return result_type

    def _infer_lambda(self, expr: LambdaExpr) -> Type:
        self.symbols.push_scope("lambda")
        param_types: list[Type] = []
        param_names = set(expr.params)
        for pname in expr.params:
            # Use concrete HOF param types when available (set by _infer_call
            # for HOF builtins) so the body is type-checked against the real
            # collection element type instead of a wildcard TypeVariable.
            if self._hof_param_types:
                pt = self._hof_param_types.pop(0)
            else:
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
        # W373: failable call in lambda body without ! — result is
        # Result<T, Error> instead of T, which likely causes a type mismatch.
        if (
            isinstance(expr.body, CallExpr)
            and isinstance(body_type, GenericInstance)
            and body_type.base_name == "Result"
        ):
            self._warning(
                "W373",
                "failable call in lambda without ! — returns Result instead of unwrapped value",
                expr.body.span,
            )
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
        elif isinstance(expr, MatchExpr):
            if expr.subject is not None:
                self._collect_lambda_captures(expr.subject, param_names, captures)
            for arm in expr.arms:
                # Exclude bindings introduced by the arm's pattern
                arm_names = set(param_names)
                pat = arm.pattern
                if isinstance(pat, BindingPattern):
                    arm_names.add(pat.name)
                elif isinstance(pat, VariantPattern):
                    for f in pat.fields:
                        if isinstance(f, BindingPattern):
                            arm_names.add(f.name)
                for stmt in arm.body:
                    e = stmt.expr if isinstance(stmt, ExprStmt) else stmt
                    if isinstance(e, Expr):
                        self._collect_lambda_captures(e, arm_names, captures)
        elif isinstance(expr, LambdaExpr):
            inner_params = set(expr.params) if expr.params else set()
            self._collect_lambda_captures(expr.body, param_names | inner_params, captures)
        elif isinstance(expr, StringInterp):
            for part in expr.parts:
                if not isinstance(part, str):
                    self._collect_lambda_captures(part, param_names, captures)
        elif isinstance(expr, IndexExpr):
            self._collect_lambda_captures(expr.obj, param_names, captures)
            self._collect_lambda_captures(expr.index, param_names, captures)
        elif isinstance(expr, ValidExpr):
            if expr.args:
                for arg in expr.args:
                    self._collect_lambda_captures(arg, param_names, captures)
        elif isinstance(expr, FailPropExpr):
            self._collect_lambda_captures(expr.expr, param_names, captures)

    def _infer_index(self, expr: IndexExpr) -> Type:
        obj_type = self._infer_expr(expr.obj)
        self._infer_expr(expr.index)  # check index expression

        if isinstance(obj_type, ListType):
            return obj_type.element
        if isinstance(obj_type, ErrorType):
            return ERROR_TY
        return ERROR_TY

    _STRINGABLE_TIME_TYPES = frozenset({"Time", "Date", "DateTime", "Clock", "Duration"})

    def _is_stringable(self, ty: Type) -> bool:
        """Return True if the type can be interpolated into an f-string."""
        if isinstance(ty, BorrowType):
            ty = ty.inner
        if ty in (STRING, INTEGER, DECIMAL, FLOAT, BOOLEAN, CHARACTER):
            return True
        if isinstance(ty, PrimitiveType) and ty.name in ("Error", *self._STRINGABLE_TIME_TYPES):
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
            elif pattern.name in ("Some", "None"):
                # Some/None on a non-Option type
                _is_nullable = isinstance(subject_type, PrimitiveType) and subject_type.name in (
                    "String",
                    "Value",
                )
                if _is_nullable:
                    # String/Value null check via Some/None is allowed
                    if pattern.name == "Some" and pattern.fields:
                        for sub in pattern.fields:
                            self._check_pattern(sub, subject_type)
                else:
                    self._error(
                        "E371",
                        f"cannot match variant '{pattern.name}' on type "
                        f"'{type_name(subject_type)}'; "
                        f"did you mean Option<{type_name(subject_type)}>?",
                        pattern.span,
                    )
            else:
                # Non-Option variant on a non-algebraic type
                self._error(
                    "E371",
                    f"cannot match variant '{pattern.name}' on type '{type_name(subject_type)}'",
                    pattern.span,
                )
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
                        suggestions=[
                            Suggestion(
                                message="add the missing arms",
                                replacement=arms_str,
                            )
                        ],
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
        _IO_VERBS = _BLOCKING_VERBS

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
