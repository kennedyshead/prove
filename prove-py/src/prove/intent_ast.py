"""AST nodes for .intent file declarations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VocabularyEntry:
    """A vocabulary type definition: Name is description."""

    name: str  # PascalCase type name
    description: str  # "is ..." text


@dataclass
class VerbPhrase:
    """A single verb phrase in a module block."""

    verb: str  # Prove verb keyword
    noun: str  # function name (derived from second word)
    context: str  # rest of the phrase (informs generation)
    raw_line: str  # original text for error messages


@dataclass
class IntentModule:
    """A module declaration with verb phrases."""

    name: str
    intents: list[VerbPhrase] = field(default_factory=list)


@dataclass
class FlowStep:
    """A single step in a flow declaration."""

    module: str
    verb_phrase: VerbPhrase


@dataclass
class FlowDecl:
    """A flow pipeline declaration."""

    steps: list[FlowStep] = field(default_factory=list)


@dataclass
class ConstraintDecl:
    """A cross-cutting constraint."""

    text: str
    anchors: list[str] = field(default_factory=list)  # vocabulary terms found


@dataclass
class IntentProject:
    """Top-level .intent file AST."""

    name: str
    purpose: str
    domain: str | None = None
    vocabulary: list[VocabularyEntry] = field(default_factory=list)
    modules: list[IntentModule] = field(default_factory=list)
    flows: list[FlowDecl] = field(default_factory=list)
    constraints: list[ConstraintDecl] = field(default_factory=list)
