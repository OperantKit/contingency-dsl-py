"""Error types for contingency-dsl parser."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    """Source location for error reporting."""

    line: int
    col: int
    length: int = 1


class DslError(Exception):
    """Base class for all contingency-dsl errors."""

    def __init__(self, message: str, span: SourceSpan | None = None) -> None:
        self.span = span
        if span:
            super().__init__(f"line {span.line}, col {span.col}: {message}")
        else:
            super().__init__(message)


class LexError(DslError):
    """Lexer-level error (invalid characters, unterminated constructs)."""


class ParseError(DslError):
    """Parser-level error (unexpected tokens, missing components)."""


class SemanticError(DslError):
    """Semantic analysis error (undefined identifiers, shadowing, etc.)."""
