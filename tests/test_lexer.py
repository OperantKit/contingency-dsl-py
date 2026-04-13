"""Unit tests for the contingency-dsl lexer."""

from __future__ import annotations

import pytest

from contingency_dsl.lexer import tokenize
from contingency_dsl.tokens import TokenType


def _token_types(source: str) -> list[TokenType]:
    """Return just the token types (excluding EOF) for quick assertions."""
    return [t.type for t in tokenize(source) if t.type != TokenType.EOF]


def _token_pairs(source: str) -> list[tuple[TokenType, str]]:
    """Return (type, value) pairs (excluding EOF)."""
    return [(t.type, t.value) for t in tokenize(source) if t.type != TokenType.EOF]


class TestLimitedHoldAlias:
    """LimitedHold is a full-name alias for LH (grammar §param_name)."""

    def test_limitedhold_bare_is_lh_token(self) -> None:
        """'LimitedHold' alone should tokenize as LH."""
        pairs = _token_pairs("LimitedHold")
        assert pairs == [(TokenType.LH, "LimitedHold")]

    def test_limitedhold_with_number_splits(self) -> None:
        """'LimitedHold10' should split into LH + NUMBER, like 'LH10'."""
        pairs = _token_pairs("LimitedHold10")
        assert pairs == [(TokenType.LH, "LimitedHold"), (TokenType.NUMBER, "10")]

    def test_limitedhold_with_number_and_unit(self) -> None:
        """'LimitedHold10s' should split into LH + NUMBER + TIME_UNIT."""
        pairs = _token_pairs("LimitedHold10s")
        assert pairs == [
            (TokenType.LH, "LimitedHold"),
            (TokenType.NUMBER, "10"),
            (TokenType.TIME_UNIT, "s"),
        ]

    def test_limitedhold_param_decl(self) -> None:
        """'LimitedHold = 10s' should produce LH EQUALS NUMBER TIME_UNIT."""
        types = _token_types("LimitedHold = 10s")
        assert types == [TokenType.LH, TokenType.EQUALS, TokenType.NUMBER, TokenType.TIME_UNIT]

    def test_limitedhold_expression_postfix(self) -> None:
        """'FI30 LimitedHold10' should tokenize correctly."""
        types = _token_types("FI30 LimitedHold10")
        assert types == [
            TokenType.SCHEDULE_TYPE,
            TokenType.NUMBER,
            TokenType.LH,
            TokenType.NUMBER,
        ]

    def test_lh_short_still_works(self) -> None:
        """Existing 'LH' / 'LH10' tokenization is unaffected."""
        assert _token_pairs("LH") == [(TokenType.LH, "LH")]
        assert _token_pairs("LH10") == [(TokenType.LH, "LH"), (TokenType.NUMBER, "10")]
        assert _token_pairs("LH10s") == [
            (TokenType.LH, "LH"),
            (TokenType.NUMBER, "10"),
            (TokenType.TIME_UNIT, "s"),
        ]
