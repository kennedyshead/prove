"""Parser for .intent files.

Parses the human-readable project declaration format into an IntentProject AST.
The parser is lenient — unrecognized verbs produce warnings, not errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prove._nl_intent import normalize_verb
from prove.intent_ast import (
    ConstraintDecl,
    FlowDecl,
    FlowStep,
    IntentModule,
    IntentProject,
    VerbPhrase,
    VocabularyEntry,
)


@dataclass
class IntentDiagnostic:
    """A diagnostic from intent parsing."""

    line: int
    message: str
    severity: str = "warning"  # "warning", "error", "info"
    code: str = ""


@dataclass
class ParseResult:
    """Result of parsing an .intent file."""

    project: IntentProject | None = None
    diagnostics: list[IntentDiagnostic] = field(default_factory=list)


def parse_intent(source: str, filename: str = "<intent>") -> ParseResult:
    """Parse an .intent file into an IntentProject AST.

    Returns a ParseResult with the project AST and any diagnostics.
    """
    lines = source.splitlines()
    result = ParseResult()
    diags = result.diagnostics

    # State
    project_name: str | None = None
    purpose: str | None = None
    domain: str | None = None
    vocabulary: list[VocabularyEntry] = []
    modules: list[IntentModule] = []
    flows: list[FlowDecl] = []
    constraints: list[ConstraintDecl] = []

    section: str | None = None  # current section: vocabulary, module, flow, constraints
    current_module: IntentModule | None = None
    current_flow: FlowDecl | None = None
    vocab_names: set[str] = set()

    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue

        # Detect indentation level
        indent = len(raw) - len(raw.lstrip())

        # Top-level keywords
        if stripped.startswith("project "):
            project_name = stripped[len("project "):].strip()
            section = "project"
            continue

        if stripped.startswith("purpose:"):
            purpose = stripped[len("purpose:"):].strip()
            continue

        if stripped.startswith("domain:"):
            domain = stripped[len("domain:"):].strip()
            continue

        if stripped == "vocabulary":
            section = "vocabulary"
            # Finalize previous module
            if current_module is not None:
                modules.append(current_module)
                current_module = None
            if current_flow is not None:
                flows.append(current_flow)
                current_flow = None
            continue

        if stripped.startswith("module "):
            # Finalize previous module
            if current_module is not None:
                modules.append(current_module)
            if current_flow is not None:
                flows.append(current_flow)
                current_flow = None
            mod_name = stripped[len("module "):].strip()
            current_module = IntentModule(name=mod_name)
            section = "module"
            continue

        if stripped == "flow":
            if current_module is not None:
                modules.append(current_module)
                current_module = None
            if current_flow is not None:
                flows.append(current_flow)
            current_flow = FlowDecl()
            section = "flow"
            continue

        if stripped == "constraints":
            if current_module is not None:
                modules.append(current_module)
                current_module = None
            if current_flow is not None:
                flows.append(current_flow)
                current_flow = None
            section = "constraints"
            continue

        # Section content
        if section == "vocabulary" and indent >= 2:
            # Parse: Name is description
            if " is " in stripped:
                parts = stripped.split(" is ", 1)
                name = parts[0].strip()
                desc = parts[1].strip()
                vocabulary.append(VocabularyEntry(name=name, description=desc))
                vocab_names.add(name)
            else:
                diags.append(IntentDiagnostic(
                    line=lineno,
                    message=f"vocabulary entry should use 'Name is description' format",
                    code="W601",
                ))
            continue

        if section == "module" and current_module is not None and indent >= 2:
            vp = _parse_verb_phrase(stripped, lineno, diags)
            if vp is not None:
                current_module.intents.append(vp)
            continue

        if section == "flow" and indent >= 2:
            # Parse flow lines: Module verb phrase [-> Module verb phrase]
            if current_flow is None:
                current_flow = FlowDecl()

            if "->" in stripped:
                parts = stripped.split("->")
                for part in parts:
                    step = _parse_flow_step(part.strip(), lineno, diags)
                    if step is not None:
                        current_flow.steps.append(step)
            else:
                step = _parse_flow_step(stripped, lineno, diags)
                if step is not None:
                    current_flow.steps.append(step)
            continue

        if section == "constraints" and indent >= 2:
            # Find vocabulary anchors in the constraint text
            anchors = [v for v in vocab_names if v.lower() in stripped.lower()]
            constraints.append(ConstraintDecl(text=stripped, anchors=anchors))
            continue

    # Finalize
    if current_module is not None:
        modules.append(current_module)
    if current_flow is not None and current_flow.steps:
        flows.append(current_flow)

    if project_name is None:
        diags.append(IntentDiagnostic(
            line=1, message="missing 'project' declaration", severity="error",
        ))
        return result

    if purpose is None:
        diags.append(IntentDiagnostic(
            line=1, message="missing 'purpose:' declaration", severity="error",
        ))
        return result

    result.project = IntentProject(
        name=project_name,
        purpose=purpose,
        domain=domain,
        vocabulary=vocabulary,
        modules=modules,
        flows=flows,
        constraints=constraints,
    )
    return result


def _parse_verb_phrase(
    text: str, lineno: int, diags: list[IntentDiagnostic],
) -> VerbPhrase | None:
    """Parse a verb phrase line into a VerbPhrase node."""
    words = text.split()
    if not words:
        return None

    canonical = normalize_verb(words[0])
    if canonical is None:
        diags.append(IntentDiagnostic(
            line=lineno,
            message=f"unrecognized verb '{words[0]}' in intent",
            code="W601",
        ))
        return None

    noun = words[1] if len(words) > 1 else canonical
    context = " ".join(words[2:]) if len(words) > 2 else ""

    return VerbPhrase(verb=canonical, noun=noun, context=context, raw_line=text)


def _parse_flow_step(
    text: str, lineno: int, diags: list[IntentDiagnostic],
) -> FlowStep | None:
    """Parse a flow step: Module verb phrase."""
    words = text.split()
    if len(words) < 2:
        return None

    module = words[0]
    rest = " ".join(words[1:])
    vp = _parse_verb_phrase(rest, lineno, diags)
    if vp is None:
        return None

    return FlowStep(module=module, verb_phrase=vp)
