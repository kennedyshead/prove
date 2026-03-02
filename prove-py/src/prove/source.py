"""Source file representation and span tracking for diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Span:
    """A range within a source file."""

    file: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def __str__(self) -> str:
        return f"{self.file}:{self.start_line}:{self.start_col}"


class SourceFile:
    """A loaded source file with line access for diagnostics."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.content = path.read_text()
        self.lines = self.content.splitlines()

    def line_at(self, n: int) -> str:
        """Return the 1-indexed line, or empty string if out of range."""
        if 1 <= n <= len(self.lines):
            return self.lines[n - 1]
        return ""

    def span_text(self, span: Span) -> str:
        """Extract the text covered by a span."""
        if span.start_line == span.end_line:
            line = self.line_at(span.start_line)
            return line[span.start_col - 1 : span.end_col]
        parts = []
        for ln in range(span.start_line, span.end_line + 1):
            line = self.line_at(ln)
            if ln == span.start_line:
                parts.append(line[span.start_col - 1 :])
            elif ln == span.end_line:
                parts.append(line[: span.end_col])
            else:
                parts.append(line)
        return "\n".join(parts)
