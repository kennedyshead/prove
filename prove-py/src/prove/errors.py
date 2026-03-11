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
    NOTE = "info"


# ANSI color codes
_COLORS = {
    Severity.ERROR: "\033[1;31m",  # bold red
    Severity.WARNING: "\033[1;33m",  # bold yellow
    Severity.NOTE: "\033[1;36m",  # bold cyan
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
    doc_url: str | None = None


# ── Diagnostic documentation registry ─────────────────────────────

_DOCS_BASE = "https://prove.botwork.se/diagnostics/"

DIAGNOSTIC_DOCS: dict[str, str] = {}


def _register_doc_range(prefix: str, start: int, end: int) -> None:
    for i in range(start, end + 1):
        code = f"{prefix}{i}"
        DIAGNOSTIC_DOCS[code] = f"{_DOCS_BASE}#{code}"


# Lexer E101-E109
_register_doc_range("E", 101, 109)
# Parser E151
DIAGNOSTIC_DOCS["E151"] = f"{_DOCS_BASE}#E151"
# Parser
for _c in ("E200", "E210", "E211", "E212", "E213", "E214", "E215"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Definition E300-E302
_register_doc_range("E", 300, 302)
# Name resolution E310-E317 (E314 moved to I314)
for _c in ("E310", "E311", "E312", "E313", "E315", "E316", "E317"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Type checking
for _c in ("E320", "E321", "E322", "E325", "E326", "E330", "E331"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Field access E340-E341
for _c in ("E340", "E341"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Control flow E350, E352, E355-E356
for _c in ("E350", "E352", "E355", "E356"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Verb enforcement E361-E366 (E360 moved to I360, E367 moved to I367)
_register_doc_range("E", 361, 367)
# Pattern matching E370-E374
_register_doc_range("E", 370, 374)
# Lookup tables E375-E379
_register_doc_range("E", 375, 379)
# Contract checking
for _c in ("E331", "E380", "E381", "E382", "E383", "E384", "E385", "E386"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Binary lookup tables E387-E389
_register_doc_range("E", 387, 389)
# Explain verification E391-E396 (E390 replaced by W323)
_register_doc_range("E", 391, 396)
# Reserved keyword E397
DIAGNOSTIC_DOCS["E397"] = f"{_DOCS_BASE}#E397"
# Attached IO context E398
DIAGNOSTIC_DOCS["E398"] = f"{_DOCS_BASE}#E398"
# Comptime execution E410-E422
_register_doc_range("E", 410, 422)
# Warnings
for _c in ("W304", "W311", "W312"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
# Warnings — contracts W321-W328
_register_doc_range("W", 321, 328)
# Warning — mutation testing W330
DIAGNOSTIC_DOCS["W330"] = f"{_DOCS_BASE}#W330"
# Warning — unused pure result W332
DIAGNOSTIC_DOCS["W332"] = f"{_DOCS_BASE}#W332"
# Warning — domain profile W340-W342
_register_doc_range("W", 340, 342)
# Warning — temporal/satisfies W390-W391
_register_doc_range("W", 390, 391)
# Warning — prose coherence W501-W505
_register_doc_range("W", 501, 505)
# Info
for _c in (
    "I201", "I300", "I301", "I302", "I303", "I310", "I311",
    "I314", "I320", "I340", "I360", "I367", "I375", "I376", "I377", "I378",
):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"


def make_diagnostic(
    severity: Severity,
    code: str,
    message: str,
    labels: list[DiagnosticLabel] | None = None,
    suggestions: list[Suggestion] | None = None,
    notes: list[str] | None = None,
) -> Diagnostic:
    """Create a Diagnostic with auto-populated doc_url from registry."""
    return Diagnostic(
        severity=severity,
        code=code,
        message=message,
        labels=labels or [],
        suggestions=suggestions or [],
        notes=notes or [],
        doc_url=DIAGNOSTIC_DOCS.get(code),
    )


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
            lines.append(f"  {self._c(_BLUE)}-->{self._c(_RESET)} {loc}")
            gutter = f"{span.start_line:>4}"
            lines.append(f"  {self._c(_BLUE)}   |{self._c(_RESET)}")

            # Show the source line if available
            source_line = self._get_source_line(span.file, span.start_line)
            if source_line is not None:
                lines.append(f"  {self._c(_BLUE)}{gutter} |{self._c(_RESET)} {source_line}")

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
                    lines.append(f"  {self._c(_BLUE)}{gutter} |{self._c(_RESET)}")

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
            lines.append(f"  {self._c(_BLUE)}try:{self._c(_RESET)} {suggestion.replacement}")

        # Doc link
        if diag.doc_url:
            lines.append(f"  {self._c(_BLUE)}={self._c(_RESET)} help: {diag.doc_url}")

        return "\n".join(lines)


class CompileError(Exception):
    """Batch compilation error carrying multiple diagnostics."""

    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        messages = [d.message for d in diagnostics]
        super().__init__(f"{len(diagnostics)} error(s): {'; '.join(messages)}")
