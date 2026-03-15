"""Phase 2 — Body generation engine.

Generates function bodies from declared intent using the standard library
and project symbols as the knowledge base. Produces GeneratedStmt lists
that form valid from-blocks, with explain/chosen/why_not prose annotations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from prove._nl_intent import extract_nouns, implied_functions, implied_verbs
from prove.stdlib_loader import _STDLIB_MODULES, load_stdlib
from prove.symbols import FunctionSignature


# ── Data types ────────────────────────────────────────────────────


@dataclass
class StdlibMatch:
    """A stdlib function that matches a verb+noun query."""

    module: str
    function: FunctionSignature
    overlap: set[str]
    score: float


@dataclass
class GeneratedStmt:
    """A single statement in a generated from-block."""

    code: str
    is_todo: bool = False
    stdlib_call: StdlibMatch | None = None
    explanation: str | None = None


@dataclass
class GeneratedBody:
    """A complete generated function body with prose annotations."""

    stmts: list[GeneratedStmt] = field(default_factory=list)
    explain: list[str] = field(default_factory=list)
    chosen: str | None = None
    why_not: list[str] = field(default_factory=list)


# ── Stdlib signature index ────────────────────────────────────────


def _build_stdlib_index() -> dict[str, list[FunctionSignature]]:
    """Load all stdlib modules and index by module name."""
    index: dict[str, list[FunctionSignature]] = {}
    for module_key in _STDLIB_MODULES:
        sigs = load_stdlib(module_key)
        if sigs:
            index[module_key] = sigs
    return index


_nlp_active: bool = False


def find_stdlib_matches(
    verb: str,
    nouns: list[str],
    stdlib_index: dict[str, list[FunctionSignature]] | None = None,
    docstring_index: dict[str, list[dict]] | None = None,
) -> list[StdlibMatch]:
    """Search stdlib for functions matching verb and domain nouns.

    Uses both signature matching (verb + name overlap) and the docstring
    index (if available) for higher-quality matches.  When an NLP backend
    is available, delegates to ``nlp.match_stdlib_function`` for improved
    semantic matching.
    """
    global _nlp_active

    if not _nlp_active:
        from prove.nlp import has_nlp_backend

        if has_nlp_backend():
            from prove.nlp import match_stdlib_function

            _nlp_active = True
            try:
                intent = f"{verb} {' '.join(nouns)}"
                return match_stdlib_function(intent, verb=verb, stdlib_index=stdlib_index)
            finally:
                _nlp_active = False

    if stdlib_index is None:
        stdlib_index = _build_stdlib_index()

    noun_set = {n.lower() for n in nouns}
    matches: list[StdlibMatch] = []

    # Direct signature matching: verb + noun overlap
    for module_name, sigs in stdlib_index.items():
        for fn in sigs:
            if fn.verb != verb:
                continue
            fn_words = {fn.name.lower()}
            if fn.doc_comment:
                fn_words |= set(re.findall(r"[a-z]{3,}", fn.doc_comment.lower()))
            overlap = fn_words & noun_set
            if overlap:
                matches.append(StdlibMatch(
                    module=module_name,
                    function=fn,
                    overlap=overlap,
                    score=len(overlap) / max(len(noun_set), 1),
                ))

    # Docstring index matching (if available)
    if docstring_index is not None:
        text = " ".join(nouns)
        doc_matches = implied_functions(text, docstring_index)
        for dm in doc_matches:
            if dm["verb"] != verb:
                continue
            # Check if already matched by signature
            already = any(
                m.module == dm["module"] and m.function.name == dm["name"]
                for m in matches
            )
            if already:
                continue
            # Look up the actual FunctionSignature
            mod_sigs = stdlib_index.get(dm["module"].lower(), [])
            for fn in mod_sigs:
                if fn.name == dm["name"] and fn.verb == verb:
                    matches.append(StdlibMatch(
                        module=dm["module"].lower(),
                        function=fn,
                        overlap=set(),
                        score=dm["score"],
                    ))
                    break

    return sorted(matches, key=lambda m: -m.score)


# ── Body generation ──────────────────────────────────────────────


def _format_type(t: object) -> str:
    """Format a Type object to its Prove source representation."""
    return str(t) if t is not None else "Value"


def _generate_call(match: StdlibMatch, param_names: list[str]) -> str:
    """Generate a stdlib call expression with parameter threading."""
    fn = match.function
    module_display = match.module.capitalize()
    args = ", ".join(param_names[:len(fn.param_names)])
    fail_suffix = "!" if fn.can_fail else ""
    return f"{module_display}.{fn.name}({args}){fail_suffix}"


def generate_body(
    verb: str,
    name: str,
    nouns: list[str],
    param_names: list[str],
    declaration_text: str | None = None,
    stdlib_index: dict[str, list[FunctionSignature]] | None = None,
    docstring_index: dict[str, list[dict]] | None = None,
) -> GeneratedBody:
    """Generate a function body from verb, nouns, and available knowledge.

    Returns a GeneratedBody with statements, prose annotations, and
    completeness information.
    """
    if stdlib_index is None:
        stdlib_index = _build_stdlib_index()

    matches = find_stdlib_matches(verb, nouns, stdlib_index, docstring_index)

    body = GeneratedBody()

    if not matches:
        # No stdlib match — produce todo stub
        msg = declaration_text or f"{verb} {name}"
        body.stmts.append(GeneratedStmt(
            code=f'todo "{msg}"',
            is_todo=True,
        ))
        return body

    # Use the best match for the primary call
    best = matches[0]
    call_code = _generate_call(best, param_names)

    # Generate the statement
    fn = best.function
    ret_str = _format_type(fn.return_type)
    if ret_str not in ("Unit", "()",):
        body.stmts.append(GeneratedStmt(
            code=f"result as {ret_str} = {call_code}",
            stdlib_call=best,
            explanation=_simplify_doc(fn.doc_comment) if fn.doc_comment else None,
        ))
        body.stmts.append(GeneratedStmt(code="result"))
    else:
        body.stmts.append(GeneratedStmt(
            code=call_code,
            stdlib_call=best,
            explanation=_simplify_doc(fn.doc_comment) if fn.doc_comment else None,
        ))

    # Generate explain entries
    for stmt in body.stmts:
        if stmt.explanation:
            body.explain.append(stmt.explanation)
        elif not stmt.is_todo and stmt.code != "result":
            body.explain.append(f"Calls {best.module.capitalize()}.{best.function.name}")

    # Generate chosen
    module_display = best.module.capitalize()
    doc_summary = _simplify_doc(best.function.doc_comment) if best.function.doc_comment else best.function.name
    body.chosen = f"{module_display}.{best.function.name} for {doc_summary}"

    # Generate why_not for alternatives
    for alt in matches[1:4]:  # limit to top 3 alternatives
        if alt.function.name == best.function.name:
            continue
        alt_module = alt.module.capitalize()
        reason = _compare_functions(best, alt)
        body.why_not.append(f"{alt_module}.{alt.function.name} because {reason}")

    return body


def _simplify_doc(doc: str | None) -> str:
    """Simplify a doc comment to a short explanation."""
    if not doc:
        return ""
    # Strip leading verb for explain-style phrasing
    text = doc.strip()
    # Lowercase first letter for explain context
    if text and text[0].isupper():
        text = text[0].lower() + text[1:]
    return text


def _compare_functions(selected: StdlibMatch, alt: StdlibMatch) -> str:
    """Generate a reason why alt was not selected over selected."""
    if selected.score > alt.score:
        return "lower relevance to declared intent"
    if selected.function.can_fail != alt.function.can_fail:
        if alt.function.can_fail:
            return "introduces failure mode not required by intent"
        return "does not handle failure cases"
    return "less specific match for the declared operation"


# ── Provenance markers ────────────────────────────────────────────


def has_generated_marker(doc_comment: str | None) -> bool:
    """Check if a doc comment contains the @generated provenance marker."""
    if doc_comment is None:
        return False
    return "@generated" in doc_comment


def add_generated_marker(doc_comment: str, source_line: int | None = None) -> str:
    """Add @generated marker to a doc comment."""
    suffix = f" from declaration line {source_line}" if source_line else ""
    return f"{doc_comment}\n@generated{suffix}"


# ── Full function generation ──────────────────────────────────────


def generate_function_source(
    verb: str,
    name: str,
    param_names: list[str],
    param_types: list[str],
    return_type: str,
    declaration_text: str | None = None,
    stdlib_index: dict[str, list[FunctionSignature]] | None = None,
    docstring_index: dict[str, list[dict]] | None = None,
    can_fail: bool = False,
) -> str:
    """Generate complete Prove function source from intent.

    Returns formatted Prove source with doc comment, signature,
    optional prose annotations, and from-block.
    """
    nouns = extract_nouns(declaration_text or f"{verb} {name}")

    body = generate_body(
        verb=verb,
        name=name,
        nouns=nouns,
        param_names=param_names,
        declaration_text=declaration_text,
        stdlib_index=stdlib_index,
        docstring_index=docstring_index,
    )

    lines: list[str] = []

    # Doc comment
    doc = declaration_text or f"{verb.capitalize()} {name}"
    lines.append(f"/// {doc}")
    lines.append(f"/// @generated")

    # Signature
    params_str = ", ".join(
        f"{pn} {pt}" for pn, pt in zip(param_names, param_types)
    )
    fail_suffix = "!" if can_fail else ""
    ret = f" {return_type}{fail_suffix}" if return_type != "Unit" else ""
    lines.append(f"{verb} {name}({params_str}){ret}")

    # Prose annotations
    if body.explain:
        lines.append("  explain")
        for entry in body.explain:
            lines.append(f"    {entry}")

    if body.chosen:
        lines.append(f'  chosen: "{body.chosen}"')

    for wn in body.why_not:
        lines.append(f'  why_not: "{wn}"')

    # From block
    lines.append("from")
    for stmt in body.stmts:
        lines.append(f"  {stmt.code}")

    return "\n".join(lines)
