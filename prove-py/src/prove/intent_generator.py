"""Generate .prv files from an IntentProject AST.

Takes the parsed .intent AST and produces Prove source files with
module declarations, type stubs, and function stubs/bodies.
"""

from __future__ import annotations

import re
from pathlib import Path

from prove._body_gen import (
    _format_type,
    find_stdlib_matches,
    generate_comptime_source,
    generate_constant_source,
    generate_function_source,
    generate_import_source,
    generate_type_source,
)
from prove._nl_intent import (
    _VERB_PARAM_HINTS,
    _VERB_RETURN_DEFAULTS,
    extract_nouns,
    infer_comptime,
    infer_constants,
    infer_stdlib_imports,
    infer_type_body,
    normalize_noun,
)
from prove.intent_ast import (
    ConstraintDecl,
    FlowDecl,
    IntentModule,
    IntentProject,
    VerbPhrase,
    VocabularyEntry,
)


def _infer_params_from_vocab(
    intent: VerbPhrase,
    vocabulary: list[VocabularyEntry],
) -> tuple[list[str], list[str], str]:
    """Infer parameter names, types, and return type from vocabulary and stdlib.

    Strategy:
    1. Try stdlib match — use its parameter signature
    2. Check if vocabulary type names appear in context — use as param type
    3. Fall back to verb-based defaults
    """
    declaration_text = f"{intent.verb} {intent.noun} {intent.context}".strip()
    nouns = extract_nouns(declaration_text)

    # 1. Try stdlib match
    matches = find_stdlib_matches(intent.verb, nouns)
    if matches:
        best = matches[0]
        fn = best.function
        if fn.param_names and fn.param_types:
            return (
                list(fn.param_names),
                [_format_type(t) for t in fn.param_types],
                _format_type(fn.return_type),
            )

    # 2. Check vocabulary names in context — NLP-enhanced matching
    from prove.nlp import has_nlp_backend

    context_lower = f"{intent.noun} {intent.context}".lower()
    if has_nlp_backend():
        from prove.nlp import text_similarity

        best_score = 0.0
        best_vocab: VocabularyEntry | None = None
        for v in vocabulary:
            score = text_similarity(v.name.lower(), context_lower)
            if score > best_score and score > 0.3:
                best_score = score
                best_vocab = v
        if best_vocab:
            param_name = best_vocab.name[0].lower() + best_vocab.name[1:]
            return_type = _VERB_RETURN_DEFAULTS.get(intent.verb, "String")
            return [param_name], [best_vocab.name], return_type
    else:
        for v in vocabulary:
            if v.name.lower() in context_lower:
                param_name = v.name[0].lower() + v.name[1:]
                return_type = _VERB_RETURN_DEFAULTS.get(intent.verb, "String")
                return [param_name], [v.name], return_type

    # 3. Fall back to verb defaults
    hints = _VERB_PARAM_HINTS.get(intent.verb, [("value", "String")])
    param_names = [h[0] for h in hints] if hints else ["value"]
    param_types = [h[1] for h in hints] if hints else ["String"]
    return_type = _VERB_RETURN_DEFAULTS.get(intent.verb, "String")
    return param_names, param_types, return_type


def _map_constraint(
    constraint: ConstraintDecl,
) -> dict[str, str | bool]:
    """Map constraint text to code features.

    Returns a dict with recognized features:
    - can_fail: bool — failable constraint
    - chosen: str — "must use X" pattern
    - ensures: str — bounded/negative constraint
    - requires: str — "all ... must" pattern
    """
    result: dict[str, str | bool] = {}
    text = constraint.text
    text_lower = text.lower()

    if "failable" in text_lower:
        result["can_fail"] = True

    m = re.search(r"must use (\w+)", text, re.IGNORECASE)
    if m:
        result["chosen"] = m.group(1)

    if "bounded" in text_lower:
        result["ensures"] = "value is within bounds"

    if re.search(r"no\b.+\bappears? in\b", text, re.IGNORECASE):
        result["ensures"] = "excluded values are absent"

    if re.search(r"all\b.+\bmust\b", text, re.IGNORECASE):
        result["requires"] = "all elements satisfy constraint"

    return result


def _collect_flow_imports(
    module: IntentModule,
    flows: list[FlowDecl],
) -> list[str]:
    """Collect module names that this module should import based on flows."""
    imports: set[str] = set()
    for flow in flows:
        module_steps = [s for s in flow.steps if s.module == module.name]
        if module_steps:
            for step in flow.steps:
                if step.module != module.name:
                    imports.add(step.module)
    return sorted(imports)


def generate_module_source(
    module: IntentModule,
    project: IntentProject,
) -> str:
    """Generate .prv module source from an IntentModule.

    Produces a module declaration with narrative derived from verb phrases,
    imports (inside the module block), type definitions (rich bodies from
    vocabulary), constants (inferred from constraints), comptime hints,
    and function stubs/bodies.
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

    # Collect all stdlib matches for the module's intents (used for imports)
    all_stdlib_matches: list[object] = []
    for intent in module.intents:
        declaration_text = f"{intent.verb} {intent.noun} {intent.context}".strip()
        nouns = extract_nouns(declaration_text)
        matches = find_stdlib_matches(intent.verb, nouns)
        all_stdlib_matches.extend(matches)

    # Imports — flow-based + stdlib-inferred, inside the module block
    flow_imports = _collect_flow_imports(module, project.flows)
    stdlib_import_groups = infer_stdlib_imports(all_stdlib_matches)

    # Emit flow imports (bare use, inside module block)
    for imp in flow_imports:
        lines.append(f"  use {imp}")

    # Emit stdlib imports with verb groups (inside module block)
    for mod_name, verb_groups in sorted(stdlib_import_groups.items()):
        # Skip if already covered by flow imports
        if mod_name in flow_imports:
            continue
        lines.append(generate_import_source(mod_name, verb_groups))

    if flow_imports or stdlib_import_groups:
        lines.append("")

    # Vocabulary types used by this module — rich bodies from description
    vocab_types = _find_vocab_references(module, project.vocabulary)
    if vocab_types:
        for vt in vocab_types:
            hint = infer_type_body(vt.description)
            lines.append(generate_type_source(vt.name, vt.description, hint))
        lines.append("")

    # Constraints that apply to this module
    module_constraints = _find_module_constraints(module, project.constraints)

    # Constants inferred from constraints
    constants = infer_constants(module_constraints)
    if constants:
        for const_name, const_type, const_value, const_doc in constants:
            lines.append(generate_constant_source(const_name, const_type, const_value, const_doc))
        lines.append("")

    # Comptime hints inferred from constraints
    comptime_hints = infer_comptime(module_constraints)
    if comptime_hints:
        for ct_name, ct_type, ct_expr, ct_doc in comptime_hints:
            lines.append(generate_comptime_source(ct_name, ct_type, ct_expr, ct_doc))
        lines.append("")

    # Map all constraints to code features
    constraint_features: dict[str, str | bool] = {}
    for c in module_constraints:
        constraint_features.update(_map_constraint(c))

    failable = bool(constraint_features.get("can_fail"))
    chosen = constraint_features.get("chosen")

    # Generate functions from verb phrases
    for intent in module.intents:
        # Infer parameters from vocabulary and stdlib
        param_names, param_types, return_type = _infer_params_from_vocab(
            intent, project.vocabulary,
        )

        # Build the function
        declaration_text = f"{intent.verb} {intent.noun} {intent.context}".strip()
        source = generate_function_source(
            verb=intent.verb,
            name=intent.noun,
            param_names=param_names,
            param_types=param_types,
            return_type=return_type,
            declaration_text=declaration_text,
            can_fail=failable,
        )

        # Inject constraint annotations into generated source
        if chosen and isinstance(chosen, str):
            # Insert chosen annotation before the from block
            source_lines = source.split("\n")
            for i, line in enumerate(source_lines):
                if line.strip() == "from":
                    source_lines.insert(i, f'  chosen: "{chosen}"')
                    break
            source = "\n".join(source_lines)

        if "ensures" in constraint_features:
            ensures_text = constraint_features["ensures"]
            source_lines = source.split("\n")
            for i, line in enumerate(source_lines):
                if line.strip() == "from":
                    source_lines.insert(i, f"  ensures: {ensures_text}")
                    break
            source = "\n".join(source_lines)

        if "requires" in constraint_features:
            requires_text = constraint_features["requires"]
            source_lines = source.split("\n")
            for i, line in enumerate(source_lines):
                if line.strip() == "from":
                    source_lines.insert(i, f"  requires: {requires_text}")
                    break
            source = "\n".join(source_lines)

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

    Returns a list of status entries for verb phrases, vocabulary types,
    and inferred constants.
    """
    from prove.ast_nodes import (
        ConstantDef,
        FunctionDef,
        ModuleDecl,
        TodoStmt,
        TypeDef,
    )
    from prove.lexer import Lexer
    from prove.parser import Parser

    statuses: list[dict] = []

    for module in project.modules:
        # Try to find the corresponding .prv file
        prv_path = project_dir / f"{module.name.lower()}.prv"
        existing_fns: dict[str, FunctionDef] = {}
        existing_types: set[str] = set()
        existing_constants: set[str] = set()

        if prv_path.exists():
            try:
                source = prv_path.read_text(encoding="utf-8")
                tokens = Lexer(source, str(prv_path)).lex()
                parsed = Parser(tokens, str(prv_path)).parse()
                for decl in parsed.declarations:
                    if isinstance(decl, FunctionDef):
                        existing_fns[decl.name] = decl
                    elif isinstance(decl, TypeDef):
                        existing_types.add(decl.name)
                    elif isinstance(decl, ConstantDef):
                        existing_constants.add(decl.name)
                    elif isinstance(decl, ModuleDecl):
                        for inner in decl.body:
                            if isinstance(inner, FunctionDef):
                                existing_fns[inner.name] = inner
                            elif isinstance(inner, TypeDef):
                                existing_types.add(inner.name)
                            elif isinstance(inner, ConstantDef):
                                existing_constants.add(inner.name)
            except Exception:
                pass

        # Build a normalized lookup for fuzzy matching
        normalized_fns = {normalize_noun(n): fd for n, fd in existing_fns.items()}

        # Check function coverage
        for intent in module.intents:
            fn = existing_fns.get(intent.noun) or normalized_fns.get(
                normalize_noun(intent.noun)
            )
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
                "kind": "function",
            })

        # Check vocabulary type coverage
        vocab_types = _find_vocab_references(module, project.vocabulary)
        for vt in vocab_types:
            type_status = "implemented" if vt.name in existing_types else "missing"
            statuses.append({
                "module": module.name,
                "verb": "",
                "noun": vt.name,
                "status": type_status,
                "raw_line": f"{vt.name} is {vt.description}",
                "kind": "type",
            })

        # Check inferred constant coverage
        module_constraints = _find_module_constraints(module, project.constraints)
        constants = infer_constants(module_constraints)
        for const_name, const_type, const_value, const_doc in constants:
            const_status = "implemented" if const_name in existing_constants else "missing"
            statuses.append({
                "module": module.name,
                "verb": "",
                "noun": const_name,
                "status": const_status,
                "raw_line": f"{const_name} as {const_type} = {const_value}",
                "kind": "constant",
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

    def _matches(word: str) -> bool:
        w = word.lower()
        # Prefix match handles singular/plural (e.g. "Credential" matches "credentials")
        return w in module_nouns or any(n.startswith(w) or w.startswith(n) for n in module_nouns)

    return [
        c for c in constraints
        if any(_matches(a) for a in c.anchors)
        or any(_matches(w) for w in c.text.split())
        or not c.anchors
    ]
