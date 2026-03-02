"""Symbol table with lexical scoping for the Prove semantic analyzer."""

from __future__ import annotations

from dataclasses import dataclass
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

    def lookup_local(self, name: str) -> Symbol | None:
        """Look up a name in this scope only (not parents)."""
        return self._symbols.get(name)

    def all_symbols(self) -> list[Symbol]:
        """Return all symbols defined in this scope."""
        return list(self._symbols.values())


class SymbolTable:
    """Manages scoping, function signatures, and type registry."""

    def __init__(self) -> None:
        self._scope_stack: list[Scope] = [Scope(name="module")]
        self._functions: dict[tuple[str | None, str], list[FunctionSignature]] = {}
        self._types: dict[str, Type] = {}

    @property
    def current_scope(self) -> Scope:
        return self._scope_stack[-1]

    def push_scope(self, name: str = "") -> None:
        self._scope_stack.append(Scope(parent=self.current_scope, name=name))

    def pop_scope(self) -> Scope:
        if len(self._scope_stack) <= 1:
            raise RuntimeError("cannot pop module scope")
        return self._scope_stack.pop()

    def define(self, symbol: Symbol) -> Symbol | None:
        """Define a symbol in the current scope. Returns existing if duplicate."""
        return self.current_scope.define(symbol)

    def lookup(self, name: str) -> Symbol | None:
        """Look up a name in the current scope chain."""
        return self.current_scope.lookup(name)

    def define_function(self, sig: FunctionSignature) -> None:
        """Register a function signature."""
        key = (sig.verb, sig.name)
        self._functions.setdefault(key, []).append(sig)

    def resolve_function(
        self, verb: str | None, name: str, arg_count: int
    ) -> FunctionSignature | None:
        """Look up a function by verb + name + arity.

        Tries (verb, name) first, then (None, name) as fallback for builtins.
        """
        for key in [(verb, name), (None, name)]:
            sigs = self._functions.get(key, [])
            for sig in sigs:
                if len(sig.param_types) == arg_count:
                    return sig
            # If we found sigs but none matched arity, still return
            # first match so caller can report arity mismatch
            if sigs:
                return sigs[0]
        return None

    def resolve_function_any(
        self,
        name: str,
        arg_types: list[Type] | None = None,
        *,
        arity: int | None = None,
    ) -> FunctionSignature | None:
        """Look up a function by name alone (any verb).

        Disambiguation order:
        1. Arity match (from *arity* or len(*arg_types*))
        2. First-argument type match (when *arg_types* given)
        3. First candidate
        """
        candidates: list[FunctionSignature] = []
        for (_, fname), sigs in self._functions.items():
            if fname == name:
                candidates.extend(sigs)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # Narrow by arity
        n = arity if arity is not None else (
            len(arg_types) if arg_types is not None else None
        )
        if n is not None:
            by_arity = [
                s for s in candidates
                if len(s.param_types) == n
            ]
            if len(by_arity) == 1:
                return by_arity[0]
            if by_arity:
                candidates = by_arity
        # Disambiguate by first-argument type name
        if arg_types:
            first = getattr(arg_types[0], "name", None)
            if first is not None:
                for sig in candidates:
                    if sig.param_types:
                        pname = getattr(
                            sig.param_types[0], "name", None,
                        )
                        if pname == first:
                            return sig
        return candidates[0]

    def define_type(self, name: str, resolved: Type) -> None:
        """Register a resolved type in the type registry."""
        self._types[name] = resolved

    def resolve_type(self, name: str) -> Type | None:
        """Look up a type by name."""
        return self._types.get(name)

    def all_functions(self) -> dict[tuple[str | None, str], list[FunctionSignature]]:
        return dict(self._functions)

    def all_known_names(self) -> set[str]:
        """Return all names visible in current scope + types + functions."""
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
        for (_verb, fname) in self._functions:
            names.add(fname)
        return names
