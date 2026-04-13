"""Unit tests for the contingency-dsl lexer."""

from __future__ import annotations

import pytest

from contingency_dsl.errors import LexError
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


class TestUnrecognizedTimeUnitSuffix:
    """Unrecognized time unit suffixes must raise LexError (#37-impl)."""

    def test_fr5sec_raises_lex_error(self) -> None:
        """'FR5sec' has unrecognized suffix 'sec'; must not be silently dropped."""
        with pytest.raises(LexError, match="unrecognized time unit suffix.*sec"):
            tokenize("FR5sec")

    def test_vi60sec_raises_lex_error(self) -> None:
        with pytest.raises(LexError, match="unrecognized time unit suffix.*sec"):
            tokenize("VI60sec")

    def test_fi30m_raises_lex_error(self) -> None:
        """'FI30m' — 'm' is not a valid unit (use 'min' or 'ms')."""
        with pytest.raises(LexError, match="unrecognized time unit suffix.*m"):
            tokenize("FI30m")

    def test_drl5sec_raises_lex_error(self) -> None:
        with pytest.raises(LexError, match="unrecognized time unit suffix.*sec"):
            tokenize("DRL5sec")

    def test_valid_units_still_work(self) -> None:
        """Confirm 's', 'ms', 'min' still tokenize correctly."""
        assert _token_pairs("FR5s") == [
            (TokenType.SCHEDULE_TYPE, "FR"),
            (TokenType.NUMBER, "5"),
            (TokenType.TIME_UNIT, "s"),
        ]
        assert _token_pairs("VI60ms") == [
            (TokenType.SCHEDULE_TYPE, "VI"),
            (TokenType.NUMBER, "60"),
            (TokenType.TIME_UNIT, "ms"),
        ]
        assert _token_pairs("FI5min") == [
            (TokenType.SCHEDULE_TYPE, "FI"),
            (TokenType.NUMBER, "5"),
            (TokenType.TIME_UNIT, "min"),
        ]
