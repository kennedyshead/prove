"""Generate .prv files from an IntentProject AST.

Takes the parsed .intent AST and produces Prove source files with
module declarations, type stubs, and function stubs/bodies.
"""

from __future__ import annotations

from pathlib import Path

from prove._body_gen import generate_function_source
from prove._generate import generate_module
from prove._nl_intent import FunctionStub
from prove.intent_ast import ConstraintDecl, IntentModule, IntentProject, VocabularyEntry


def generate_module_source(
    module: IntentModule,
    project: IntentProject,
) -> str:
    """Generate .prv module source from an IntentModule.

    Produces a module declaration with narrative derived from verb phrases,
    type imports from vocabulary, and function stubs/bodies.
    """
    lines: list[str] = []

    # Module declaration
    lines.append(f"module {module.name}")
    if project.domain:
        lines.append(f"  domain: {project.domain}")

    # Build narrative from verb phrases
    narrative_parts = []
    for intent in module.intents:
        narrative_parts.append(f"{intent.verb} {intent.noun} {intent.context}".strip())
    narrative = ". ".join(narrative_parts)
    if narrative:
        lines.append(f'  narrative: """{narrative.capitalize()}"""')
    lines.append("")

    # Vocabulary types used by this module
    vocab_types = _find_vocab_references(module, project.vocabulary)
    if vocab_types:
        for vt in vocab_types:
            lines.append(f"  /// {vt.description}")
            lines.append(f"  type {vt.name}")
        lines.append("")

    # Constraints that apply to this module
    module_constraints = _find_module_constraints(module, project.constraints)

    # Generate functions from verb phrases
    for intent in module.intents:
        # Determine if failable from constraints
        failable = any(
            "failable" in c.text.lower()
            for c in module_constraints
        )

        # Build the function
        declaration_text = f"{intent.verb} {intent.noun} {intent.context}".strip()
        source = generate_function_source(
            verb=intent.verb,
            name=intent.noun,
            param_names=["value"],
            param_types=["String"],
            return_type="String",
            declaration_text=declaration_text,
            can_fail=failable,
        )
        lines.append(source)
        lines.append("")

    return "\n".join(lines) + "\n"


def generate_project(
    project: IntentProject,
    output_dir: Path,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Generate all .prv files for an IntentProject.

    Returns list of (filename, source) tuples.
    If dry_run is False, writes files to output_dir.
    """
    results: list[tuple[str, str]] = []

    for module in project.modules:
        filename = f"{module.name.lower()}.prv"
        source = generate_module_source(module, project)
        results.append((filename, source))

        if not dry_run:
            out_path = output_dir / filename
            out_path.write_text(source, encoding="utf-8")

    return results


def check_intent_coverage(
    project: IntentProject,
    project_dir: Path,
) -> list[dict]:
    """Check which intent declarations have matching implementations.

    Returns a list of status entries, one per verb phrase.
    """
    from prove.ast_nodes import FunctionDef, ModuleDecl, TodoStmt
    from prove.lexer import Lexer
    from prove.parser import Parser

    statuses: list[dict] = []

    for module in project.modules:
        # Try to find the corresponding .prv file
        prv_path = project_dir / f"{module.name.lower()}.prv"
        existing_fns: dict[str, FunctionDef] = {}

        if prv_path.exists():
            try:
                source = prv_path.read_text(encoding="utf-8")
                tokens = Lexer(source, str(prv_path)).lex()
                parsed = Parser(tokens, str(prv_path)).parse()
                for decl in parsed.declarations:
                    if isinstance(decl, FunctionDef):
                        existing_fns[decl.name] = decl
                    elif isinstance(decl, ModuleDecl):
                        for inner in decl.body:
                            if isinstance(inner, FunctionDef):
                                existing_fns[inner.name] = inner
            except Exception:
                pass

        for intent in module.intents:
            fn = existing_fns.get(intent.noun)
            if fn is None:
                status = "missing"
            elif any(isinstance(s, TodoStmt) for s in fn.body):
                status = "todo"
            else:
                status = "implemented"

            statuses.append({
                "module": module.name,
                "verb": intent.verb,
                "noun": intent.noun,
                "status": status,
                "raw_line": intent.raw_line,
            })

    return statuses


def _find_vocab_references(
    module: IntentModule,
    vocabulary: list[VocabularyEntry],
) -> list[VocabularyEntry]:
    """Find vocabulary entries referenced by a module's verb phrases."""
    module_text = " ".join(
        f"{i.verb} {i.noun} {i.context}" for i in module.intents
    ).lower()
    return [
        v for v in vocabulary
        if v.name.lower() in module_text
    ]


def _find_module_constraints(
    module: IntentModule,
    constraints: list[ConstraintDecl],
) -> list[ConstraintDecl]:
    """Find constraints that reference vocabulary terms used by this module."""
    module_nouns = {i.noun.lower() for i in module.intents}
    return [
        c for c in constraints
        if any(a.lower() in module_nouns or module_nouns & {w.lower() for w in c.text.split()}
               for a in c.anchors) or not c.anchors
    ]
