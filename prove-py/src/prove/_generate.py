"""Generate .prv skeleton source from function stubs and module metadata."""

from __future__ import annotations

from prove._nl_intent import FunctionStub


def generate_module(
    name: str,
    narrative: str,
    stubs: list[FunctionStub],
    domain: str | None = None,
    imports: list[str] | None = None,
    min_confidence: float = 0.3,
) -> str:
    """Generate a complete .prv module skeleton.

    Functions below min_confidence are emitted as comments.
    All from-blocks are empty (contain `todo` placeholder).
    """
    lines: list[str] = []

    lines.append(f"module {name}")
    if domain:
        lines.append(f"  domain: {domain}")
    lines.append(f'  narrative: """{narrative}"""')
    lines.append("")

    if imports:
        for imp in imports:
            lines.append(f"  use {imp}")
        lines.append("")

    for stub in stubs:
        if stub.confidence < min_confidence:
            lines.append(f"// Possible: {stub.verb} {stub.name}(...)")
            continue

        lines.append(f"/// TODO: document {stub.name}")

        params_str = ", ".join(f"{pname} {ptype}" for pname, ptype in stub.params)
        ret = f" {stub.return_type}" if stub.return_type != "Unit" else ""
        lines.append(f"{stub.verb} {stub.name}({params_str}){ret}")

        lines.append("from")
        lines.append("  todo")
        lines.append("")

    return "\n".join(lines) + "\n"


def generate_stub_function(stub: FunctionStub) -> str:
    """Generate a single function stub (for incremental addition)."""
    lines: list[str] = []
    lines.append(f"/// TODO: document {stub.name}")
    params_str = ", ".join(f"{pname} {ptype}" for pname, ptype in stub.params)
    ret = f" {stub.return_type}" if stub.return_type != "Unit" else ""
    lines.append(f"{stub.verb} {stub.name}({params_str}){ret}")
    lines.append("from")
    lines.append("  todo")
    return "\n".join(lines)
