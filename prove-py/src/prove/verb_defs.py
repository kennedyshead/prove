"""Centralized verb classification for the Prove compiler.

Every verb property is declared once in ``VERB_PROPERTIES``.  Derived
frozensets (``PURE_VERBS``, ``ASYNC_VERBS``, etc.) are computed at import
time so the rest of the compiler can import exactly the set it needs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerbProps:
    """Semantic properties of a Prove verb keyword."""

    pure: bool = False
    """No IO side effects allowed."""

    failable: bool = False
    """Pure verb that may still be declared with ``!``."""

    non_allocating: bool = False
    """Guaranteed to never allocate new values."""

    async_: bool = False
    """Runs as a coroutine (detached/attached/listens/renders)."""

    blocking: bool = False
    """IO verb forbidden inside async bodies."""

    needs_ownership: bool = True
    """Whether the verb may consume (take ownership of) its parameters.

    Pure verbs only read their inputs — ownership is never transferred,
    so the caller's reference is guaranteed to stay alive.  IO and most
    async verbs may consume parameters (send over channel, write to file),
    so they need ownership.
    """


# ── Canonical verb table ────────────────────────────────────────────
# Add new verbs here.  All derived sets update automatically.

VERB_PROPERTIES: dict[str, VerbProps] = {
    # Pure verbs — never consume inputs, only read them.
    "transforms": VerbProps(pure=True, failable=True, needs_ownership=False),
    "validates": VerbProps(pure=True, non_allocating=True, needs_ownership=False),
    "derives": VerbProps(pure=True, non_allocating=True, needs_ownership=False),
    "creates": VerbProps(pure=True, needs_ownership=False),
    "matches": VerbProps(pure=True, non_allocating=True, needs_ownership=False),
    # IO / blocking verbs — may consume parameters.
    "inputs": VerbProps(blocking=True),
    "outputs": VerbProps(blocking=True),
    "streams": VerbProps(blocking=True),
    "dispatches": VerbProps(blocking=True),
    # Async verbs
    "detached": VerbProps(async_=True),
    "attached": VerbProps(async_=True),
    "listens": VerbProps(async_=True),
    "renders": VerbProps(async_=True, needs_ownership=False),
}


# ── Derived sets ────────────────────────────────────────────────────

PURE_VERBS: frozenset[str] = frozenset(v for v, p in VERB_PROPERTIES.items() if p.pure)

FAILABLE_PURE_VERBS: frozenset[str] = frozenset(
    v for v, p in VERB_PROPERTIES.items() if p.pure and p.failable
)

NON_ALLOCATING_VERBS: frozenset[str] = frozenset(
    v for v, p in VERB_PROPERTIES.items() if p.non_allocating
)

ASYNC_VERBS: frozenset[str] = frozenset(v for v, p in VERB_PROPERTIES.items() if p.async_)

BLOCKING_VERBS: frozenset[str] = frozenset(v for v, p in VERB_PROPERTIES.items() if p.blocking)

VERBS_NEED_OWNERSHIP: frozenset[str] = frozenset(
    v for v, p in VERB_PROPERTIES.items() if p.needs_ownership
)

# Union of all non-pure verbs (IO + async).  Used by the emitter to
# decide whether a function body may perform side effects.
ALL_IO_VERBS: frozenset[str] = BLOCKING_VERBS | ASYNC_VERBS
