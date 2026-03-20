"""View the AST of a Prove source file.

This script is embedded as a comptime string in view.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from typing import cast

# pylint: disable=invalid-name

file: str = cast(str, globals().get("file", ""))

if __name__ == "__main__":
    from pathlib import Path

    from prove.errors import CompileError, DiagnosticRenderer
    from prove.lexer import Lexer
    from prove.parser import Parser

    source = Path(file).read_text()
    filename = str(file)

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError as e:
        renderer = DiagnosticRenderer(color=True)
        for diag in e.diagnostics:
            print(renderer.render(diag))
        raise SystemExit(1)

    def _dump_ast(node: object, depth: int) -> None:
        indent = "  " * depth
        name = type(node).__name__
        if hasattr(node, "__dataclass_fields__"):
            fields = node.__dataclass_fields__
            print(f"{indent}{name}")
            for field_name in fields:
                if field_name == "span":
                    continue
                value = getattr(node, field_name)
                if isinstance(value, list):
                    if value:
                        print(f"{indent}  {field_name}:")
                        for item in value:
                            _dump_ast(item, depth + 2)
                    else:
                        print(f"{indent}  {field_name}: []")
                elif hasattr(value, "__dataclass_fields__"):
                    print(f"{indent}  {field_name}:")
                    _dump_ast(value, depth + 2)
                elif value is not None:
                    print(f"{indent}  {field_name}: {value!r}")
        else:
            print(f"{indent}{name}: {node!r}")

    _dump_ast(module, 0)
    raise SystemExit(0)
