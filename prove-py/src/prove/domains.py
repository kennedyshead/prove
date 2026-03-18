"""Domain profiles for context-dependent syntax enforcement.

A module's ``domain:`` tag selects a profile that adds domain-specific
warnings. Profile violations are emitted as W-level diagnostics so
they guide but never block compilation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DomainProfile:
    """Rules enforced when a module declares a specific domain."""

    name: str
    # Types that should be preferred (using alternatives emits a warning)
    preferred_types: dict[str, str] = field(default_factory=dict)
    # Contracts required on public (non-trusted) functions
    required_contracts: frozenset[str] = frozenset()
    # Annotations required on public functions
    required_annotations: frozenset[str] = frozenset()
    # Description shown in diagnostics
    description: str = ""


DOMAIN_PROFILES: dict[str, DomainProfile] = {
    "finance": DomainProfile(
        name="finance",
        preferred_types={"Float": "Decimal"},
        required_contracts=frozenset({"ensures"}),
        required_annotations=frozenset({"near_miss"}),
        description="Financial domain: prefer Decimal over Float, require contracts and boundary cases",  # noqa: E501
    ),
    "safety": DomainProfile(
        name="safety",
        preferred_types={},
        required_contracts=frozenset({"ensures", "requires"}),
        required_annotations=frozenset({"terminates", "explain"}),
        description="Safety-critical domain: require full contracts and termination proofs",
    ),
    "general": DomainProfile(
        name="general",
        preferred_types={},
        required_contracts=frozenset(),
        required_annotations=frozenset(),
        description="General domain: no additional requirements",
    ),
}


def get_domain_profile(domain: str | None) -> DomainProfile | None:
    """Look up a domain profile by name (case-insensitive)."""
    if domain is None:
        return None
    return DOMAIN_PROFILES.get(domain.lower())
