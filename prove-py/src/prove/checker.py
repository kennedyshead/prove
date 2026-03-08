"""Two-pass semantic analyzer for the Prove language.

Pass 1: Register all top-level declarations (types, functions, constants, imports).
Pass 2: Check each declaration body (type inference, verb enforcement, exhaustiveness).
"""

from __future__ import annotations

from pathlib import Path

from prove._check_calls import CallCheckMixin
from prove._check_contracts import ContractCheckMixin
from prove._check_types import TypeCheckMixin
from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
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
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupTypeDef,
    MainDef,
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
    STRING,
    UNIT,
    AlgebraicType,
    BorrowType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    TypeVariable,
    UnitType,
    VariantInfo,
    has_mutable_modifier,
    has_own_modifier,
    is_json_serializable,
    numeric_widen,
    resolve_type_vars,
    substitute_type_vars,
    type_name,
    types_compatible,
)

# Verbs considered pure (no IO side effects allowed)
_PURE_VERBS = frozenset({"transforms", "validates", "reads", "creates", "matches"})

# Verbs that need ownership of their parameters (skip borrow inference)
_VERBS_NEED_OWNERSHIP = frozenset(
    {"outputs", "matches", "creates", "validates", "inputs", "transforms", "reads"}
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
        # Requires-based narrowing: list of (module, args)
        self._requires_narrowings: list[tuple[str, list[Expr]]] = []
        # Mutation survivors from previous --mutate runs
        self._survivors: list[dict] = []
        if project_dir:
            from prove.mutator import load_survivors

            self._survivors = load_survivors(project_dir)
        # Local (sibling) module info for cross-file imports
        self._local_modules = local_modules
        # Lookup tables per type name for TypeName: resolution
        self._lookup_tables: dict[str, LookupTypeDef] = {}
        # Expected type context for bidirectional type inference (e.g. binary lookups)
        self._expected_type: Type | None = None
        # Ownership tracking: variables that have been moved (passed to Own parameters)
        self._moved_vars: set[str] = set()
        # Track scope depth for ownership - reset on function entry
        self._ownership_scope_stack: list[set[str]] = []
        # Track invariant network names for satisfies validation
        self._invariant_networks: set[str] = set()

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
                for item in decl.body:
                    if isinstance(item, FunctionDef):
                        self._register_function(item)
                    elif isinstance(item, MainDef):
                        self._register_main(item)

        # Collect user-defined IO function names (inputs/outputs verbs)
        for decl in module.declarations:
            if isinstance(decl, FunctionDef) and decl.verb in ("inputs", "outputs"):
                self._io_function_names.add(decl.name)

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
                    verb=None,
                    name=v.name,
                    param_names=[f.name for f in v.fields],
                    param_types=vfield_types,
                    return_type=resolved,
                    can_fail=False,
                    span=v.span,
                    requires=[],
                )
                self.symbols.define_function(vsig)

        elif isinstance(body, RefinementTypeDef):
            base = self._resolve_type_expr(body.base_type)
            resolved = RefinementType(td.name, base, body.constraint)

        elif isinstance(body, BinaryDef):
            # Binary types are opaque C-backed types — no fields visible to Prove
            resolved = PrimitiveType(td.name)

        elif isinstance(body, LookupTypeDef):
            # Lookup types: build AlgebraicType from entries
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
        # E316: function name shadows builtin
        if fd.name in _BUILTIN_FUNCTIONS:
            self._error(
                "E316",
                f"'{fd.name}' shadows the built-in function '{fd.name}'. Choose a different name.",
                fd.span,
            )
        param_types = [self._resolve_type_expr(p.type_expr) for p in fd.params]
        return_type = self._resolve_type_expr(fd.return_type) if fd.return_type else UNIT
        sig = FunctionSignature(
            verb=fd.verb,
            name=fd.name,
            param_names=[p.name for p in fd.params],
            param_types=param_types,
            return_type=return_type,
            can_fail=fd.can_fail,
            span=fd.span,
            requires=fd.requires,
            doc_comment=fd.doc_comment,
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
        from prove.stdlib_loader import is_stdlib_module, load_stdlib

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

        for item in imp.items:
            # Type imports (verb="types" or bare CamelCase with no verb)
            is_type_import = item.verb == "types" or (item.verb is None and item.name[:1].isupper())
            if is_type_import:
                resolved = PrimitiveType(item.name)
                self.symbols.define(
                    Symbol(
                        name=item.name,
                        kind=SymbolKind.TYPE,
                        resolved_type=resolved,
                        span=item.span,
                        verb=item.verb,
                    )
                )
                self.symbols.define_type(item.name, resolved)
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

    # ── Pass 2: Checking ────────────────────────────────────────

    def _check_function(self, fd: FunctionDef) -> None:
        """Check a function body."""
        self._current_function = fd
        self._is_recursive = False
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

        # Check verb rules
        self._check_verb_rules(fd)

        # Binary functions have no Prove body — skip body and return checks
        if fd.binary:
            self.symbols.pop_scope()
            self._current_function = None
            return

        # Check body
        body_type = UNIT
        for i, stmt in enumerate(fd.body):
            # W332: warn on unused pure function result (except for last statement)
            if i < len(fd.body) - 1:
                self._check_unused_pure_result(stmt)
            body_type = self._check_stmt(stmt)

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
        if body_len > 1 and no_contracts and not is_inputs_no_args:
            self._info(
                "I320",
                f"Function '{fd.name}' has {body_len} statements but no contracts. "
                "Consider adding requires/ensures for mutation testing.",
                fd.span,
            )
        elif body_len > 1 and fd.verb in ("transforms", "matches") and no_contracts:
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
                            f"Function '{fd.name}' had a surviving mutant: {survivor.get('description', 'unknown')}. "
                            "Add contracts to catch this mutation.",
                            fd.span,
                        )
                except (ValueError, IndexError):
                    pass

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
        """Validate a binary lookup table (E379, E387)."""
        num_columns = len(body.value_types)
        _ALLOWED_BINARY_TYPES = {"String", "Integer", "Decimal", "Boolean"}
        for vt in body.value_types:
            tname = vt.name if hasattr(vt, "name") else str(vt)
            if tname not in _ALLOWED_BINARY_TYPES:
                self._error(
                    "E387",
                    f"unsupported type '{tname}' in binary lookup column "
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

    def _check_type_def(self, td: TypeDef) -> None:
        """Validate field types and where constraints."""
        body = td.body
        if isinstance(body, RecordTypeDef):
            for f in body.fields:
                self._resolve_type_expr(f.type_expr)
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
                    return lo <= value <= hi
                return None

            left = self._eval_refinement_constraint_expr(constraint.left, value)
            right = self._eval_refinement_constraint_expr(constraint.right, value)
            if left is None or right is None:
                return None

            op = constraint.op
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == "<":
                return left < right
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

                pattern = constraint.pattern if isinstance(constraint, RegexLit) else constraint.value
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
                    return left + right
                if op == "-":
                    return left - right
                if op == "*":
                    return left * right
                if op == "%":
                    return left % right
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
        for req_expr in fd.requires:
            # valid file(path) → ValidExpr
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                func_name = req_expr.name
                args = req_expr.args
                n_args = len(args)
                sig = self.symbols.resolve_function(
                    "validates",
                    func_name,
                    n_args,
                )
                if sig is None:
                    sig = self.symbols.resolve_function_any(
                        func_name,
                        arity=n_args,
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
            sig = self.symbols.resolve_function(
                "validates",
                func_name_,
                n_args,
            )
            if sig is None:
                sig = self.symbols.resolve_function_any(
                    func_name_,
                    arity=n_args,
                )
            if sig is not None and sig.verb == "validates":
                mod = module_name or sig.module
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
                is_matchable = isinstance(first_type, (AlgebraicType, ErrorType)) or (
                    isinstance(first_type, PrimitiveType)
                    and first_type.name in ("String", "Integer")
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

        # E367: match expression only allowed in matches verb
        if verb != "matches":
            self._check_match_restriction(fd.body, fd.span)

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
        elif isinstance(expr, LambdaExpr):
            self._check_pure_expr(expr.body)
        elif isinstance(expr, MatchExpr):
            if expr.subject:
                self._check_pure_expr(expr.subject)
            for arm in expr.arms:
                for s in arm.body:
                    self._check_pure_stmt(s)

    # ── Match restriction (E367) ────────────────────────────────

    def _check_match_restriction(
        self,
        body: list[Stmt | MatchExpr],
        span: Span,
    ) -> None:
        """E367: match expression only allowed in matches verb."""
        for stmt in body:
            if isinstance(stmt, MatchExpr):
                self._error(
                    "E367",
                    "match expression is only allowed in `matches` verb functions",
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
            self._error(
                "E367",
                "match expression is only allowed in `matches` verb functions",
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
            return self._infer_expr(stmt.expr)
        if isinstance(stmt, MatchExpr):
            return self._infer_match(stmt)
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
            if not types_compatible(expected, inferred):
                self._error(
                    "E321",
                    f"type mismatch: expected '{type_name(expected)}', got '{type_name(inferred)}'",
                    vd.span,
                )
            resolved = expected
        else:
            resolved = inferred

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
        if isinstance(expr, MatchExpr):
            return self._infer_match(expr, expected_type=expected_type)
        if isinstance(expr, LambdaExpr):
            return self._infer_lambda(expr)
        if isinstance(expr, IndexExpr):
            return self._infer_index(expr)
        if isinstance(expr, ValidExpr):
            n = len(expr.args) if expr.args is not None else 0
            sig = self.symbols.resolve_function("validates", expr.name, n)
            if sig is None:
                sig = self.symbols.resolve_function_any(expr.name, arity=n)
            if sig and sig.module:
                self._used_imports.add((sig.module, expr.name))
            if expr.args is None:
                # Function reference: valid error → FunctionType([Diagnostic], Boolean)
                if sig is not None and sig.param_types:
                    return FunctionType(list(sig.param_types), BOOLEAN)
            return BOOLEAN
        if isinstance(expr, ComptimeExpr):
            return self._infer_comptime(expr)
        if isinstance(expr, LookupAccessExpr):
            return self._check_lookup_access_expr(expr)
        if isinstance(expr, BinaryLookupExpr):
            # Runtime binary lookup — type already resolved by checker
            col = self._resolve_type_expr(SimpleType(expr.column_type, expr.span))
            return col if col else ERROR_TY
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

    def _infer_list(self, expr: ListLiteral, expected_type: Type | None = None) -> Type:
        if not expr.elements:
            # Try to use expected type for empty list
            if expected_type is not None:
                from prove.types import ListType

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
            elif isinstance(subject_type, GenericInstance):
                # Handle Result<Value, Error> and Option<Value> variant patterns
                self._check_generic_variant_pattern(pattern, subject_type)
        elif isinstance(pattern, WildcardPattern):
            pass  # matches everything
        elif isinstance(pattern, LiteralPattern):
            pass  # literal match

    def _check_generic_variant_pattern(
        self, pattern: VariantPattern, subject_type: GenericInstance
    ) -> None:
        """Bind variant sub-patterns for generic types (Result, Option)."""
        base = subject_type.base_name
        args = subject_type.args
        name = pattern.name

        # Map variant name → inner type for builtin generic types
        inner_type: Type | None = None
        if base == "Result" and len(args) >= 2:
            if name == "Ok":
                inner_type = args[0]
            elif name == "Err":
                inner_type = args[1]
        elif base == "Option" and len(args) >= 1:
            if name == "Some":
                inner_type = args[0]
            elif name == "None":
                inner_type = None  # No binding for None

        if inner_type is not None:
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
        """Check if a variable has been moved and report error if so."""
        if name in self._moved_vars:
            self._error(
                "E340",
                f"use of moved value '{name}'",
                span,
            )

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
                self._info(
                    "I303",
                    f"Type '{name}' is defined but never used.",
                    span,
                )
