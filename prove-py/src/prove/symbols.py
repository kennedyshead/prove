"""Symbol table with lexical scoping for the Prove semantic analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from prove.source import Span
from prove.types import Type


class SymbolKind(Enum):
    FUNCTION = auto()
    TYPE = auto()
    CONSTANT = auto()
    VARIABLE = auto()
    PARAMETER = auto()


@dataclass
class Symbol:
    name: str
    kind: SymbolKind
    resolved_type: Type
    span: Span
    verb: str | None = None
    mutable: bool = False
    used: bool = False
    is_imported: bool = False
    used_outside_match: bool = False  # True if referenced outside any match arm
    match_arm_ids: set[int] = field(default_factory=set)  # unique arm IDs where used


@dataclass
class FunctionSignature:
    verb: str | None
    name: str
    param_names: list[str]
    param_types: list[Type]
    return_type: Type
    can_fail: bool
    span: Span
    module: str | None = None
    requires: list[Type] = field(default_factory=list)
    doc_comment: str | None = None
    event_type: Type | None = None
    ensures: list = field(default_factory=list)


class Scope:
    """A single lexical scope level."""

    def __init__(self, parent: Scope | None = None, name: str = "") -> None:
        self.parent = parent
        self.name = name
        self._symbols: dict[str, Symbol] = {}

    def define(self, symbol: Symbol) -> Symbol | None:
        """Define a symbol in this scope. Returns existing symbol if duplicate."""
        existing = self._symbols.get(symbol.name)
        if existing is not None:
            return existing
        self._symbols[symbol.name] = symbol
        return None

    def lookup(self, name: str) -> Symbol | None:
        """Look up a name in this scope and all parent scopes."""
        sym = self._symbols.get(name)
        if sym is not None:
            return sym
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def all_symbols(self) -> list[Symbol]:
        """Return all symbols defined in this scope."""
        return list(self._symbols.values())


def _types_structurally_equal(a: Type, b: Type) -> bool:
    """Strict structural equality for duplicate detection.

    Unlike ``types_compatible``, this does NOT treat TypeVariable as a wildcard.
    Two types are equal only when they have the same structure and names.
    """
    from prove.types import (
        AlgebraicType,
        FunctionType,
        GenericInstance,
        PrimitiveType,
        RecordType,
        RefinementType,
        TypeVariable,
        UnitType,
    )

    if type(a) is not type(b):
        return False
    if isinstance(a, TypeVariable):
        return a.name == b.name
    if isinstance(a, PrimitiveType):
        return a.name == b.name
    if isinstance(a, UnitType):
        return True
    if isinstance(a, GenericInstance):
        b_gi: GenericInstance = b  # type: ignore[assignment]
        return (
            a.base_name == b_gi.base_name
            and len(a.args) == len(b_gi.args)
            and all(_types_structurally_equal(x, y) for x, y in zip(a.args, b_gi.args))
        )
    if isinstance(a, (RecordType, AlgebraicType, RefinementType)):
        return a.name == b.name
    if isinstance(a, FunctionType):
        b_fn: FunctionType = b  # type: ignore[assignment]
        return (
            len(a.param_types) == len(b_fn.param_types)
            and all(
                _types_structurally_equal(x, y) for x, y in zip(a.param_types, b_fn.param_types)
            )
            and _types_structurally_equal(a.return_type, b_fn.return_type)
        )
    # Fallback: identity
    return a is b


class SymbolTable:
    """Manages scoping, function signatures, and type registry."""

    def __init__(self) -> None:
        self._scope_stack: list[Scope] = [Scope(name="module")]
        self._functions: dict[tuple[str | None, str], list[FunctionSignature]] = {}
        self._types: dict[str, Type] = {}
        self._known_names_cache: set[str] | None = None

    @property
    def current_scope(self) -> Scope:
        return self._scope_stack[-1]

    def push_scope(self, name: str = "") -> None:
        self._scope_stack.append(Scope(parent=self.current_scope, name=name))
        self._known_names_cache = None

    def pop_scope(self) -> Scope:
        if len(self._scope_stack) <= 1:
            raise RuntimeError("cannot pop module scope")
        scope = self._scope_stack.pop()
        self._known_names_cache = None
        return scope

    def define(self, symbol: Symbol) -> Symbol | None:
        """Define a symbol in the current scope. Returns existing if duplicate."""
        self._known_names_cache = None
        return self.current_scope.define(symbol)

    def lookup(self, name: str) -> Symbol | None:
        """Look up a name in the current scope chain."""
        return self.current_scope.lookup(name)

    def define_function(self, sig: FunctionSignature) -> None:
        """Register a function signature."""
        key = (sig.verb, sig.name)
        self._functions.setdefault(key, []).append(sig)
        self._known_names_cache = None

    def find_exact_duplicate(self, sig: FunctionSignature) -> FunctionSignature | None:
        """Find a previously registered function with the same verb, name, and param types."""
        key = (sig.verb, sig.name)
        for existing in self._functions.get(key, []):
            if len(existing.param_types) != len(sig.param_types):
                continue
            if all(
                _types_structurally_equal(a, b)
                for a, b in zip(existing.param_types, sig.param_types)
            ):
                return existing
        return None

    def resolve_function_by_types(
        self,
        verb: str | None,
        name: str,
        arg_types: list[Type],
    ) -> FunctionSignature | None:
        """Resolve overload by parameter type matching.

        Priority:
        1. Exact type match (all params compatible)
        2. Arity match (fallback)
        """
        from prove.types import TypeVariable, types_compatible

        for key in [(verb, name), (None, name)]:
            sigs = self._functions.get(key, [])
            if not sigs:
                continue

            # Priority 1: Exact type match
            for sig in sigs:
                if len(sig.param_types) == len(arg_types) and all(
                    isinstance(p, TypeVariable) or types_compatible(p, a)
                    for p, a in zip(sig.param_types, arg_types)
                ):
                    return sig

            # Priority 2: Arity match
            for sig in sigs:
                if len(sig.param_types) == len(arg_types):
                    return sig

        return None

    def resolve_function(
        self, verb: str | None, name: str, arg_count: int
    ) -> FunctionSignature | None:
        """Look up a function by verb + name + arity.

        Tries (verb, name) first, then (None, name) as fallback for builtins.
        """
        best = None
        for key in [(verb, name), (None, name)]:
            sigs = self._functions.get(key, [])
            for sig in sigs:
                if len(sig.param_types) == arg_count:
                    return sig
            if sigs and best is None:
                best = sigs[0]
        return best

    def resolve_function_any(
        self,
        name: str,
        arg_types: list[Type] | None = None,
        *,
        arity: int | None = None,
        expected_return: Type | None = None,
    ) -> FunctionSignature | None:
        """Look up a function by name alone (any verb).

        Disambiguation order:
        1. Arity match (from *arity* or len(*arg_types*))
        2. Expected return type match (if given)
        3. First-argument type match (when *arg_types* given)
        4. First candidate
        """
        from prove.types import GenericInstance, TypeVariable, types_compatible

        def _ret_matches(expected: Type, actual_ret: Type) -> bool:
            """Match expected return type, unwrapping Result<T, E> → T."""
            if types_compatible(expected, actual_ret):
                return True
            if (
                isinstance(actual_ret, GenericInstance)
                and actual_ret.base_name == "Result"
                and actual_ret.args
            ):
                return types_compatible(expected, actual_ret.args[0])
            return False

        candidates: list[FunctionSignature] = []
        for (_, fname), sigs in self._functions.items():
            if fname == name:
                candidates.extend(sigs)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Narrow by arity
        n = arity if arity is not None else (len(arg_types) if arg_types is not None else None)
        if n is not None:
            by_arity = [s for s in candidates if len(s.param_types) == n]
            if len(by_arity) == 1:
                return by_arity[0]
            if by_arity:
                candidates = by_arity

        # Disambiguate by expected return type.
        # When arg_types are available, don't let a TypeVariable return type
        # be the sole winner — it matches everything and would shadow concrete
        # overloads from other modules (e.g. Sequence.get(List<Value>,Integer)
        # ->Value beating Table.get(String,Table<Value>)->Option<Value>).
        # Instead, narrow candidates but defer the final pick to structural
        # matching below.
        if expected_return is not None:
            matches = [s for s in candidates if _ret_matches(expected_return, s.return_type)]
            if len(matches) == 1:
                # If the sole match is only via TypeVariable return and we have
                # arg_types to do structural disambiguation, don't commit yet —
                # TypeVariable matches everything so it's not a real signal.
                if not (arg_types and isinstance(matches[0].return_type, TypeVariable)):
                    return matches[0]
            # Only narrow candidates if we have concrete (non-TypeVariable)
            # return matches.  If ALL matches are TypeVariable returns, keep
            # the full candidate list so structural matching can disambiguate
            # by parameter types instead.
            if matches:
                concrete_ret = [s for s in matches if not isinstance(s.return_type, TypeVariable)]
                if concrete_ret:
                    candidates = matches
                # else: all matches have TypeVariable returns — don't narrow

        # Disambiguate by structural match (best for generics)
        if arg_types:
            structural_matches = []
            for sig in candidates:
                if len(sig.param_types) == len(arg_types):
                    if all(
                        isinstance(p, TypeVariable) or types_compatible(p, a)
                        for p, a in zip(sig.param_types, arg_types)
                    ):
                        # If all params are concrete matches (no TypeVariable),
                        # the actual args are also concrete (not TypeVariable),
                        # and the return type matches, this is an exact hit — return early.
                        all_concrete = all(not isinstance(p, TypeVariable) for p in sig.param_types)
                        args_concrete = all(not isinstance(a, TypeVariable) for a in arg_types)
                        if (
                            all_concrete
                            and args_concrete
                            and expected_return is not None
                            and _ret_matches(expected_return, sig.return_type)
                        ):
                            return sig
                        structural_matches.append(sig)
            if len(structural_matches) == 1:
                return structural_matches[0]
            if structural_matches:
                # Among multiple structural matches, prefer those whose return
                # type matches the expected return (when available).  This
                # prevents e.g. validates float(Float)->Boolean from winning
                # over creates float(Value)->Float when Float is expected.
                if expected_return is not None:
                    ret_matches = [
                        s
                        for s in structural_matches
                        if _ret_matches(expected_return, s.return_type)
                    ]
                    if len(ret_matches) == 1:
                        return ret_matches[0]
                    if ret_matches:
                        structural_matches = ret_matches

                # Prefer overloads with concrete (non-TypeVariable) params over
                # generic ones.  e.g. string(Value<Csv>) over string(Value).
                # But when the actual arg is a simple type (not GenericInstance),
                # prefer the TypeVariable catch-all over GenericInstance overloads.
                from prove.types import GenericInstance as GI

                any_generic_arg = arg_types and any(isinstance(a, GI) for a in arg_types)

                def _specificity(sig: "FunctionSignature") -> int:
                    return sum(0 if isinstance(p, TypeVariable) else 1 for p in sig.param_types)

                if any_generic_arg:
                    # Arg is generic (e.g. Value<Csv>) — prefer most specific overload
                    structural_matches.sort(key=_specificity, reverse=True)
                    best = _specificity(structural_matches[0])
                    top = [s for s in structural_matches if _specificity(s) == best]
                else:
                    # Arg is simple (e.g. plain Value) — prefer name-matching
                    # TypeVariable overload over more-specific GenericInstance ones
                    name_matches = [
                        s
                        for s in structural_matches
                        if all(
                            isinstance(p, TypeVariable)
                            and getattr(p, "name", "") == getattr(a, "name", "")
                            for p, a in zip(s.param_types, arg_types)
                        )
                    ]
                    if len(name_matches) == 1:
                        return name_matches[0]
                    if name_matches:
                        top = name_matches
                    else:
                        structural_matches.sort(key=_specificity, reverse=True)
                        best = _specificity(structural_matches[0])
                        top = [s for s in structural_matches if _specificity(s) == best]

                if len(top) == 1:
                    return top[0]
                # Prefer exact type-name match before falling back to
                # compatibility — avoids e.g. String overload winning when
                # the actual argument is Value (both are compatible via
                # Value's JSON-serializable rule).
                if arg_types:
                    exact = [
                        s
                        for s in top
                        if all(
                            getattr(p, "name", None) == getattr(a, "name", None)
                            or getattr(p, "base_name", None) == getattr(a, "base_name", None)
                            for p, a in zip(s.param_types, arg_types)
                        )
                    ]
                    if len(exact) == 1:
                        return exact[0]
                    if exact:
                        top = exact
                # Among equally specific overloads, prefer exact generic match
                # e.g. Value<Tree> param for Value<Tree> arg over Value<Csv> param
                if arg_types:
                    for sig in top:
                        if all(
                            types_compatible(p, a) and not isinstance(p, TypeVariable)
                            for p, a in zip(sig.param_types, arg_types)
                        ):
                            return sig
                candidates = top

        # Disambiguate by first-argument type name
        if arg_types:
            first = getattr(arg_types[0], "name", None) or getattr(
                arg_types[0],
                "base_name",
                None,
            )
            if first is not None:
                for sig in candidates:
                    if sig.param_types:
                        pname = getattr(
                            sig.param_types[0],
                            "name",
                            None,
                        ) or getattr(
                            sig.param_types[0],
                            "base_name",
                            None,
                        )
                        if pname == first:
                            return sig

        # Prefer creates/reads over validates when arg is dynamic (Value) —
        # validates returns Boolean which is rarely the intended conversion.
        if len(candidates) > 1:
            non_validates = [s for s in candidates if s.verb != "validates"]
            if non_validates:
                candidates = non_validates
            if len(candidates) == 1:
                return candidates[0]

        # Fall back to first candidate
        return candidates[0]

    def define_type(self, name: str, resolved: Type) -> None:
        """Register a resolved type in the type registry."""
        self._types[name] = resolved
        self._known_names_cache = None

    def resolve_type(self, name: str) -> Type | None:
        """Look up a type by name."""
        return self._types.get(name)

    def all_functions(self) -> dict[tuple[str | None, str], list[FunctionSignature]]:
        return dict(self._functions)

    def all_types(self) -> dict[str, Type]:
        """Return all registered types."""
        return dict(self._types)

    def all_known_names(self) -> set[str]:
        """Return all names visible in current scope + types + functions."""
        if self._known_names_cache is not None:
            return self._known_names_cache
        names: set[str] = set()
        # Walk scope chain
        scope: Scope | None = self.current_scope
        while scope is not None:
            for sym in scope.all_symbols():
                names.add(sym.name)
            scope = scope.parent
        # Types
        names.update(self._types.keys())
        # Function names
        for _verb, fname in self._functions:
            names.add(fname)
        self._known_names_cache = names
        return names
