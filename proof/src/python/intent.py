"""Work with .intent project declaration files.

This script is embedded as a comptime string in intent.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from typing import cast

# pylint: disable=invalid-name

path: str = cast(str, globals().get("path", "project.intent"))
status: bool = cast(bool, globals().get("status", False))
drift: bool = cast(bool, globals().get("drift", False))
gen: bool = cast(bool, globals().get("gen", False))
dry_run: bool = cast(bool, globals().get("dry_run", False))

if __name__ == "__main__":
    from pathlib import Path

    from prove.intent_generator import check_intent_coverage, generate_project
    from prove.intent_parser import parse_intent

    target = Path(path)
    source = target.read_text(encoding="utf-8")
    result = parse_intent(source, str(target))

    for diag in result.diagnostics:
        severity = diag.severity.upper()
        code = f" {diag.code}" if diag.code else ""
        print(f"{target}:{diag.line}: {severity}{code}: {diag.message}")

    if result.project is None:
        print("error: failed to parse intent file")
        raise SystemExit(1)

    project = result.project
    project_dir = target.parent
    src_dir = project_dir / "src"
    source_dir = src_dir if src_dir.is_dir() else project_dir

    if gen:
        generated = generate_project(project, source_dir, dry_run=dry_run)
        for filename, src in generated:
            if dry_run:
                print(f"--- {filename} ---")
                print(src)
            else:
                print(f"generated {filename}")
        raise SystemExit(0)

    statuses = check_intent_coverage(project, source_dir)

    if drift:
        statuses = [s for s in statuses if s["status"] != "implemented"]

    if not statuses:
        print("all intent declarations have matching implementations")
        raise SystemExit(0)

    for s in statuses:
        icon = {"implemented": "+", "todo": "~", "missing": "-"}.get(s["status"], "?")
        print(f"  [{icon}] {s['module']}.{s['noun']} ({s['verb']}) — {s['status']}")

    impl = sum(1 for s in statuses if s["status"] == "implemented")
    total = len(statuses)
    print(f"\n  {impl}/{total} declarations implemented")
    raise SystemExit(0)
