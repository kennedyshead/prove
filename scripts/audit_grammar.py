#!/usr/bin/env python3
"""Audit: compare tree-sitter-prove grammar.js against Python parser.py.

Parses every .prv file in the repo with both parsers and reports:
- Files where tree-sitter has ERROR/MISSING nodes but Python parser succeeds
- Files where Python parser fails but tree-sitter succeeds
- Files where both fail
- Summary statistics

Also extracts a method-to-rule mapping table from parser.py → grammar.js.

Usage:
    python scripts/audit_grammar.py [--verbose] [--mapping-only]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Ensure prove-py is importable
WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "prove-py" / "src"))

from prove.parse import parse  # noqa: E402

# Directories to scan for .prv files
PRV_DIRS = [
    "prove-py/src/prove/stdlib",
    "examples",
    "proof/src",
    "benchmarks",
    "prove-py/tests/fixtures",
]

# Files/dirs to skip (auto-generated data, not real Prove source)
SKIP_PATTERNS = [
    "prove-py/src/prove/data/",
    "node_modules/",
    "tree-sitter-prove/test.prv",  # scratch file
]

TREE_SITTER_DIR = WORKSPACE / "tree-sitter-prove"


def collect_prv_files() -> list[Path]:
    """Collect all .prv files from the designated directories."""
    files = []
    for d in PRV_DIRS:
        dirpath = WORKSPACE / d
        if not dirpath.exists():
            continue
        for root, _, fnames in os.walk(dirpath):
            for f in fnames:
                if f.endswith(".prv"):
                    full = Path(root) / f
                    rel = full.relative_to(WORKSPACE)
                    if any(skip in str(rel) for skip in SKIP_PATTERNS):
                        continue
                    files.append(full)
    return sorted(files)


def parse_with_treesitter(filepath: Path) -> tuple[bool, int, str]:
    """Parse a file with tree-sitter CLI.

    Returns (success, error_count, raw_output).
    success = no ERROR or MISSING nodes in output.
    """
    try:
        result = subprocess.run(
            ["tree-sitter", "parse", str(filepath)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(TREE_SITTER_DIR),
        )
        output = result.stdout + result.stderr
        error_count = output.count("(ERROR ") + output.count("(MISSING ")
        return (error_count == 0, error_count, output)
    except subprocess.TimeoutExpired:
        return (False, -1, "TIMEOUT")
    except FileNotFoundError:
        return (False, -1, "tree-sitter CLI not found")


def parse_with_python(filepath: Path) -> tuple[bool, str]:
    """Parse a file with the Python parser.

    Returns (success, error_message_or_empty).
    """
    try:
        source = filepath.read_text()
        parse(source, filename=str(filepath))
        return (True, "")
    except Exception as e:
        return (False, str(e))


def extract_parser_methods() -> list[str]:
    """Extract all _parse_* method names from parser.py."""
    parser_py = WORKSPACE / "prove-py" / "src" / "prove" / "parser.py"
    content = parser_py.read_text()
    return sorted(re.findall(r"def (_parse_\w+)", content))


def extract_grammar_rules() -> list[str]:
    """Extract all rule names from grammar.js."""
    grammar_js = TREE_SITTER_DIR / "grammar.js"
    content = grammar_js.read_text()
    # Match rule definitions like "    rule_name: $ => ..."
    return sorted(re.findall(r"^\s+(\w+):\s*\$\s*=>", content, re.MULTILINE))


# Manual mapping of parser.py methods to grammar.js rules
PARSE_METHOD_TO_GRAMMAR_RULE: dict[str, list[str]] = {
    "_parse_assignment": ["assignment"],
    "_parse_binary_csv_path": ["runtime_lookup_type_body"],
    "_parse_binary_lookup_def": ["named_lookup_type_body"],
    "_parse_binary_lookup_entries": ["named_lookup_type_body"],
    "_parse_binary_entry_row": ["lookup_variant"],
    "_parse_body": ["_body_content"],
    "_parse_call_expr": ["call_expression"],
    "_parse_comptime_expr": ["comptime_block"],
    "_parse_constant_def": ["constant_definition"],
    "_parse_declaration": ["_top_level"],
    "_parse_explain_block": ["explain_annotation"],
    "_parse_explain_entry": ["explain_line"],
    "_parse_expression": ["expression", "binary_expression", "unary_expression"],
    "_parse_field_def": ["field_declaration"],
    "_parse_foreign_block": ["foreign_block"],
    "_parse_foreign_function": ["foreign_function"],
    "_parse_function_def": ["function_definition"],
    "_parse_implicit_match_arms": ["match_expression", "match_arm"],
    "_parse_import": ["import_declaration"],
    "_parse_import_group": ["import_group"],
    "_parse_indented_type_body": ["_type_body", "algebraic_type_body"],
    "_parse_inline_type_body": ["_type_body"],
    "_parse_invariant_network": ["invariant_network"],
    "_parse_lambda": ["lambda_expression"],
    "_parse_list_literal": ["list_literal"],
    "_parse_lookup_access_expr": ["lookup_access_expression"],
    "_parse_lookup_entry": ["lookup_variant"],
    "_parse_lookup_type_body": ["lookup_type_body"],
    "_parse_lookup_value": ["_lookup_value"],
    "_parse_main_def": ["main_definition"],
    "_parse_match_arm": ["match_arm"],
    "_parse_match_expr": ["match_expression"],
    "_parse_module_decl": ["module_declaration"],
    "_parse_multiline_algebraic": ["algebraic_type_body"],
    "_parse_named_explain_entry": ["explain_line"],
    "_parse_param": ["parameter"],
    "_parse_param_list": ["parameter_list"],
    "_parse_pattern": ["pattern"],
    "_parse_pipe_lookup_entries": ["dispatch_lookup_type_body"],
    "_parse_prefix": ["unary_expression"],
    "_parse_refinement_constraint": ["refinement_type_body"],
    "_parse_statement": ["_statement"],
    "_parse_store_lookup_expr": ["lookup_access_expression"],
    "_parse_string_or_interp": ["string_literal", "format_string"],
    "_parse_todo_stmt": [],  # No grammar.js equivalent (TodoStmt is compiler-internal)
    "_parse_type_body": ["_type_body"],
    "_parse_type_def": ["type_definition"],
    "_parse_type_expr": ["type_expression"],
    "_parse_type_modifier": ["type_modifier_bracket", "_type_modifier"],
    "_parse_valid_expr": ["valid_expression"],
    "_parse_var_decl": ["variable_declaration"],
    "_parse_variant": ["algebraic_variant"],
    "_parse_variant_pattern": ["variant_pattern"],
}


def build_mapping_table(methods: list[str], rules: list[str]) -> str:
    """Build a markdown table mapping parser methods to grammar rules."""
    lines = [
        "| Parser Method | Grammar Rule(s) | Status |",
        "|---|---|---|",
    ]
    rule_set = set(rules)
    for method in methods:
        mapped = PARSE_METHOD_TO_GRAMMAR_RULE.get(method)
        if mapped is None:
            lines.append(f"| `{method}` | ??? | **UNMAPPED** |")
        elif not mapped:
            lines.append(f"| `{method}` | (internal) | OK |")
        else:
            missing = [r for r in mapped if r not in rule_set and not r.startswith("_")]
            rule_str = ", ".join(f"`{r}`" for r in mapped)
            status = "OK" if not missing else f"**MISSING RULES:** {', '.join(missing)}"
            lines.append(f"| `{method}` | {rule_str} | {status} |")

    # Grammar rules not mapped from any parser method
    mapped_rules = set()
    for rules_list in PARSE_METHOD_TO_GRAMMAR_RULE.values():
        mapped_rules.update(rules_list)

    unmapped_rules = [
        r for r in rules if r not in mapped_rules and not r.startswith("_")
    ]
    if unmapped_rules:
        lines.append("")
        lines.append("### Grammar rules with no parser method mapping")
        lines.append("")
        lines.append(
            "These rules exist in grammar.js but have no direct `_parse_*` counterpart:"
        )
        lines.append("")
        for r in unmapped_rules:
            lines.append(f"- `{r}`")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Audit grammar.js vs parser.py")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--mapping-only",
        action="store_true",
        help="Only output the method-to-rule mapping table",
    )
    args = parser.parse_args()

    methods = extract_parser_methods()
    rules = extract_grammar_rules()

    if args.mapping_only:
        print(build_mapping_table(methods, rules))
        return

    files = collect_prv_files()
    print(f"Collected {len(files)} .prv files to audit\n")

    results: dict[str, list[Path]] = {
        "both_ok": [],
        "ts_fail_py_ok": [],
        "ts_ok_py_fail": [],
        "both_fail": [],
        "ts_timeout": [],
    }
    ts_error_details: dict[Path, tuple[int, str]] = {}
    py_error_details: dict[Path, str] = {}

    for filepath in files:
        rel = filepath.relative_to(WORKSPACE)
        ts_ok, ts_errors, ts_output = parse_with_treesitter(filepath)
        py_ok, py_err = parse_with_python(filepath)

        if ts_errors == -1:
            results["ts_timeout"].append(filepath)
            status = "TS-TIMEOUT"
        elif ts_ok and py_ok:
            results["both_ok"].append(filepath)
            status = "OK"
        elif not ts_ok and py_ok:
            results["ts_fail_py_ok"].append(filepath)
            ts_error_details[filepath] = (ts_errors, ts_output)
            status = f"TS-FAIL({ts_errors} errors)"
        elif ts_ok and not py_ok:
            results["ts_ok_py_fail"].append(filepath)
            py_error_details[filepath] = py_err
            status = "PY-FAIL"
        else:
            results["both_fail"].append(filepath)
            ts_error_details[filepath] = (ts_errors, ts_output)
            py_error_details[filepath] = py_err
            status = "BOTH-FAIL"

        if args.verbose or status != "OK":
            print(f"  [{status:20s}] {rel}")

    # Summary
    print(f"\n{'=' * 60}")
    print("AUDIT SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total files:                    {len(files)}")
    print(f"Both parsers OK:                {len(results['both_ok'])}")
    print(f"Tree-sitter FAIL, Python OK:    {len(results['ts_fail_py_ok'])}")
    print(f"Tree-sitter OK, Python FAIL:    {len(results['ts_ok_py_fail'])}")
    print(f"Both FAIL:                      {len(results['both_fail'])}")
    print(f"Tree-sitter timeout:            {len(results['ts_timeout'])}")

    if results["ts_fail_py_ok"]:
        print("\n--- Grammar gaps (tree-sitter fails, Python succeeds) ---")
        for fp in results["ts_fail_py_ok"]:
            rel = fp.relative_to(WORKSPACE)
            count, output = ts_error_details[fp]
            print(f"\n  {rel} ({count} ERROR nodes)")
            # Extract ERROR lines
            for line in output.splitlines():
                if "ERROR" in line or "MISSING" in line:
                    print(f"    {line.strip()}")

    if results["ts_ok_py_fail"]:
        print("\n--- Python parser gaps (Python fails, tree-sitter succeeds) ---")
        for fp in results["ts_ok_py_fail"]:
            rel = fp.relative_to(WORKSPACE)
            err = py_error_details[fp]
            print(f"\n  {rel}")
            print(f"    {err[:200]}")

    if results["both_fail"]:
        print("\n--- Both parsers fail ---")
        for fp in results["both_fail"]:
            rel = fp.relative_to(WORKSPACE)
            count, _ = ts_error_details[fp]
            err = py_error_details[fp]
            print(f"\n  {rel} (TS: {count} errors)")
            print(f"    Python: {err[:200]}")

    # Mapping table
    print(f"\n{'=' * 60}")
    print("PARSER METHOD → GRAMMAR RULE MAPPING")
    print(f"{'=' * 60}\n")
    print(build_mapping_table(methods, rules))

    # Exit code
    gap_count = len(results["ts_fail_py_ok"])
    if gap_count > 0:
        print(
            f"\n⚠ {gap_count} grammar gap(s) found — grammar.js needs fixes before Phase 2"
        )
        sys.exit(1)
    else:
        print(
            "\n✓ No grammar gaps — tree-sitter parses everything Python parser accepts"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
