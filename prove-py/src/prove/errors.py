"""Rust-style colored diagnostic rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.source import Span


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


# ANSI color codes
_COLORS = {
    Severity.ERROR: "\033[1;31m",    # bold red
    Severity.WARNING: "\033[1;33m",  # bold yellow
    Severity.NOTE: "\033[1;36m",     # bold cyan
}
_BOLD = "\033[1m"
_BLUE = "\033[1;34m"
_RESET = "\033[0m"


@dataclass(frozen=True)
class DiagnosticLabel:
    """Points to a specific source location."""

    span: Span
    message: str
    style: str = "primary"  # "primary" or "secondary"


@dataclass(frozen=True)
class Suggestion:
    """A suggested fix."""

    message: str
    replacement: str


@dataclass
class Diagnostic:
    """A single diagnostic message with optional labels and suggestions."""

    severity: Severity
    code: str
    message: str
    labels: list[DiagnosticLabel] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class DiagnosticRenderer:
    """Renders diagnostics in Rust-style format with colors."""

    def __init__(self, *, color: bool = True) -> None:
        self.color = color
        self._file_cache: dict[str, list[str]] = {}

    def _c(self, code: str) -> str:
        return code if self.color else ""

    def _get_source_line(self, filename: str, line_num: int) -> str | None:
        """Load and cache source file, return the 1-indexed line."""
        if filename not in self._file_cache:
            try:
                path = Path(filename)
                if path.is_file():
                    self._file_cache[filename] = path.read_text().splitlines()
                else:
                    self._file_cache[filename] = []
            except OSError:
                self._file_cache[filename] = []
        lines = self._file_cache[filename]
        if 1 <= line_num <= len(lines):
            return lines[line_num - 1]
        return None

    def render(self, diag: Diagnostic) -> str:
        lines: list[str] = []
        sev = diag.severity
        color = _COLORS[sev]

        # Header: error[E042]: message
        lines.append(
            f"{self._c(color)}{sev.value}[{diag.code}]{self._c(_RESET)}"
            f"{self._c(_BOLD)}: {diag.message}{self._c(_RESET)}"
        )

        # Labels
        for label in diag.labels:
            span = label.span
            loc = f"{span.file}:{span.start_line}:{span.start_col}"
            lines.append(
                f"  {self._c(_BLUE)}-->{self._c(_RESET)} {loc}"
            )
            gutter = f"{span.start_line:>4}"
            lines.append(f"  {self._c(_BLUE)}   |{self._c(_RESET)}")

            # Show the source line if available
            source_line = self._get_source_line(span.file, span.start_line)
            if source_line is not None:
                lines.append(
                    f"  {self._c(_BLUE)}{gutter} |{self._c(_RESET)} {source_line}"
                )

            # Show carets underneath
            if span.start_line == span.end_line:
                caret_len = max(1, span.end_col - span.start_col + 1)
                padding = " " * (span.start_col - 1)
                carets = "^" * caret_len
                lines.append(
                    f"  {self._c(_BLUE)}   |{self._c(_RESET)} "
                    f"{padding}{self._c(color)}{carets}{self._c(_RESET)}"
                )
            else:
                if source_line is None:
                    lines.append(
                        f"  {self._c(_BLUE)}{gutter} |{self._c(_RESET)}"
                    )

            if label.message:
                lines.append(
                    f"  {self._c(_BLUE)}   |{self._c(_RESET)}   "
                    f"{self._c(color)}{label.message}{self._c(_RESET)}"
                )

        # Notes
        for note in diag.notes:
            lines.append(f"  {self._c(_BLUE)}={self._c(_RESET)} note: {note}")

        # Suggestions
        for suggestion in diag.suggestions:
            lines.append(
                f"  {self._c(_BLUE)}try:{self._c(_RESET)} {suggestion.replacement}"
            )

        return "\n".join(lines)


class CompileError(Exception):
    """Batch compilation error carrying multiple diagnostics."""

    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        messages = [d.message for d in diagnostics]
        super().__init__(f"{len(diagnostics)} error(s): {'; '.join(messages)}")
