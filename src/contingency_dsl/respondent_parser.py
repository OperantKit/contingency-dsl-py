"""Recursive descent productions for the respondent (Tier A) primitives.

Operates on the same token stream as the operant parser. Entry point
`try_parse_respondent` is called from `_Parser._parse_base_schedule` when
the head token is an uppercase identifier whose value matches a Tier A
primitive name. Returns the constructed respondent AST node, or None if
the token does not begin a respondent primitive.

The LL(1) decision set is:
    Pair         → Pair.* dispatch
    Extinction   → R5
    CSOnly       → R6
    USOnly       → R7
    Contingency  → R8
    TrulyRandom  → R9
    ExplicitlyUnpaired → R10
    Compound     → R11
    Serial       → R12
    ITI          → R13
    Differential → R14
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import ParseError, SourceSpan
from .respondent import (
    CSOnly,
    Compound,
    Contingency,
    Differential,
    Duration,
    ExplicitlyUnpaired,
    Extinction,
    ITI,
    PairBackward,
    PairForwardDelay,
    PairForwardTrace,
    PairSimultaneous,
    RespondentExpr,
    Serial,
    TrulyRandom,
    USOnly,
)
from .tokens import Token, TokenType

if TYPE_CHECKING:
    from .parser import _Parser


# Canonical Tier A primitive names (bare, i.e. without the Pair. prefix).
RESPONDENT_PRIMITIVE_NAMES: frozenset[str] = frozenset(
    {
        "Pair",
        "Extinction",
        "CSOnly",
        "USOnly",
        "Contingency",
        "TrulyRandom",
        "ExplicitlyUnpaired",
        "Compound",
        "Serial",
        "ITI",
        "Differential",
    }
)


# --- Public entry point -----------------------------------------------------


def try_parse_respondent(parser: _Parser) -> RespondentExpr | None:
    """Dispatch a respondent primitive based on the head identifier.

    Returns the parsed AST node, or None if the head token is not a
    known Tier A primitive.
    """
    tok = parser._peek()
    if tok.type != TokenType.IDENTIFIER:
        return None

    name = tok.value
    if name == "Pair":
        return _parse_pair(parser)
    if name == "Extinction":
        return _parse_extinction(parser)
    if name == "CSOnly":
        return _parse_cs_only(parser)
    if name == "USOnly":
        return _parse_us_only(parser)
    if name == "Contingency":
        return _parse_contingency(parser)
    if name == "TrulyRandom":
        return _parse_truly_random(parser)
    if name == "ExplicitlyUnpaired":
        return _parse_explicitly_unpaired(parser)
    if name == "Compound":
        return _parse_compound(parser)
    if name == "Serial":
        return _parse_serial(parser)
    if name == "ITI":
        return _parse_iti(parser)
    if name == "Differential":
        return _parse_differential(parser)
    return None


# --- Helpers ----------------------------------------------------------------


def _stim_ref(parser: _Parser, context: str) -> str:
    """Parse a stimulus reference: identifier or string literal."""
    tok = parser._peek()
    if tok.type == TokenType.IDENTIFIER:
        parser._advance()
        return tok.value
    if tok.type == TokenType.STRING_LITERAL:
        parser._advance()
        return tok.value
    raise ParseError(
        f"expected stimulus reference (identifier or string literal) in {context}, "
        f"got {tok.type.name} '{tok.value}'",
        SourceSpan(tok.line, tok.col),
    )


def _duration(parser: _Parser, context: str) -> Duration:
    """Parse a duration: number followed by a time unit."""
    num_tok = parser._peek()
    if num_tok.type != TokenType.NUMBER:
        raise ParseError(
            f"expected numeric value for {context}, got {num_tok.type.name} '{num_tok.value}'",
            SourceSpan(num_tok.line, num_tok.col),
        )
    parser._advance()
    unit_tok = parser._peek()
    if unit_tok.type != TokenType.TIME_UNIT:
        raise ParseError(
            f"expected time unit (s | ms | min) for {context}, got {unit_tok.type.name} '{unit_tok.value}'",
            SourceSpan(unit_tok.line, unit_tok.col),
        )
    parser._advance()
    return Duration(value=float(num_tok.value), unit=unit_tok.value)


def _probability(parser: _Parser, context: str) -> float:
    """Parse a probability: bare number (Phase 2 range check)."""
    num_tok = parser._peek()
    if num_tok.type != TokenType.NUMBER:
        raise ParseError(
            f"expected numeric probability for {context}, got {num_tok.type.name} '{num_tok.value}'",
            SourceSpan(num_tok.line, num_tok.col),
        )
    parser._advance()
    return float(num_tok.value)


def _trials(parser: _Parser, context: str) -> int:
    """Parse a trial count: positive integer-valued number."""
    num_tok = parser._peek()
    if num_tok.type != TokenType.NUMBER:
        raise ParseError(
            f"expected integer trial count for {context}, got {num_tok.type.name} '{num_tok.value}'",
            SourceSpan(num_tok.line, num_tok.col),
        )
    parser._advance()
    val = float(num_tok.value)
    if val != int(val):
        raise ParseError(
            f"trial count must be an integer, got {num_tok.value}",
            SourceSpan(num_tok.line, num_tok.col),
        )
    return int(val)


def _consume_name(parser: _Parser, expected_value: str) -> Token:
    """Consume an IDENTIFIER whose value matches expected_value."""
    tok = parser._peek()
    if tok.type != TokenType.IDENTIFIER or tok.value != expected_value:
        raise ParseError(
            f"expected identifier '{expected_value}', got {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )
    parser._advance()
    return tok


def _parse_kwarg_key(parser: _Parser, allowed: frozenset[str], context: str) -> str:
    """Peek at an IDENTIFIER/PR_STEP and consume the key followed by '='.

    PR_STEP is used here because the lexer tags `exponential`, `uniform`,
    `linear`, `hodos` as PR_STEP; respondent uses `uniform` and
    `exponential` as distribution values (see _iti_distribution).
    Keys themselves are always plain lowercase identifiers.
    """
    tok = parser._peek()
    if tok.type != TokenType.IDENTIFIER or tok.value not in allowed:
        raise ParseError(
            f"expected keyword argument ({', '.join(sorted(allowed))}) in {context}, "
            f"got {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )
    parser._advance()
    parser._expect(TokenType.EQUALS, f"{context} '{tok.value}='")
    return tok.value


def _parse_cs_list(parser: _Parser, context: str) -> tuple[str, ...]:
    """Parse a bracketed CS list: [ stim (, stim)+ ]"""
    parser._expect(TokenType.LBRACKET, f"{context} cs_list opening bracket")
    items: list[str] = [_stim_ref(parser, f"{context} cs_list element")]
    while parser._at(TokenType.COMMA):
        parser._advance()
        items.append(_stim_ref(parser, f"{context} cs_list element"))
    parser._expect(TokenType.RBRACKET, f"{context} cs_list closing bracket")
    if len(items) < 2:
        # The grammar demands at least two CSs per Compound/Serial.
        raise ParseError(
            f"{context} requires at least 2 CS references",
            SourceSpan(parser._peek().line, parser._peek().col),
        )
    return tuple(items)


# --- Per-primitive productions ---------------------------------------------


def _parse_extinction(parser: _Parser) -> Extinction:
    _consume_name(parser, "Extinction")
    parser._expect(TokenType.LPAREN, "Extinction opening paren")
    # cs_ref or cs=<stim_ref>
    tok = parser._peek()
    if (
        tok.type == TokenType.IDENTIFIER
        and tok.value == "cs"
        and parser._pos + 1 < len(parser._tokens)
        and parser._tokens[parser._pos + 1].type == TokenType.EQUALS
    ):
        parser._advance()
        parser._advance()
    cs = _stim_ref(parser, "Extinction cs")
    parser._expect(TokenType.RPAREN, "Extinction closing paren")
    return Extinction(cs=cs)


def _parse_cs_only(parser: _Parser) -> CSOnly:
    _consume_name(parser, "CSOnly")
    parser._expect(TokenType.LPAREN, "CSOnly opening paren")
    cs = _parse_optional_kw_stim(parser, "cs", "CSOnly")
    parser._expect(TokenType.COMMA, "CSOnly comma")
    # trials: positional number or trials=number
    tok = parser._peek()
    if (
        tok.type == TokenType.IDENTIFIER
        and tok.value == "trials"
        and parser._pos + 1 < len(parser._tokens)
        and parser._tokens[parser._pos + 1].type == TokenType.EQUALS
    ):
        parser._advance()
        parser._advance()
    trials = _trials(parser, "CSOnly trials")
    parser._expect(TokenType.RPAREN, "CSOnly closing paren")
    return CSOnly(cs=cs, trials=trials)


def _parse_us_only(parser: _Parser) -> USOnly:
    _consume_name(parser, "USOnly")
    parser._expect(TokenType.LPAREN, "USOnly opening paren")
    us = _parse_optional_kw_stim(parser, "us", "USOnly")
    parser._expect(TokenType.COMMA, "USOnly comma")
    tok = parser._peek()
    if (
        tok.type == TokenType.IDENTIFIER
        and tok.value == "trials"
        and parser._pos + 1 < len(parser._tokens)
        and parser._tokens[parser._pos + 1].type == TokenType.EQUALS
    ):
        parser._advance()
        parser._advance()
    trials = _trials(parser, "USOnly trials")
    parser._expect(TokenType.RPAREN, "USOnly closing paren")
    return USOnly(us=us, trials=trials)


def _parse_optional_kw_stim(parser: _Parser, kw: str, context: str) -> str:
    """Accept either `<kw>=<stim>` or a bare `<stim>` for the first argument."""
    tok = parser._peek()
    if (
        tok.type == TokenType.IDENTIFIER
        and tok.value == kw
        and parser._pos + 1 < len(parser._tokens)
        and parser._tokens[parser._pos + 1].type == TokenType.EQUALS
    ):
        parser._advance()
        parser._advance()
    return _stim_ref(parser, f"{context} {kw}")


def _parse_contingency(parser: _Parser) -> Contingency:
    _consume_name(parser, "Contingency")
    parser._expect(TokenType.LPAREN, "Contingency opening paren")
    p1 = _parse_optional_kw_prob(parser, "p_us_given_cs", "Contingency")
    parser._expect(TokenType.COMMA, "Contingency comma")
    p2 = _parse_optional_kw_prob(parser, "p_us_given_no_cs", "Contingency")
    parser._expect(TokenType.RPAREN, "Contingency closing paren")
    return Contingency(p_us_given_cs=p1, p_us_given_no_cs=p2)


def _parse_optional_kw_prob(parser: _Parser, kw: str, context: str) -> float:
    tok = parser._peek()
    if (
        tok.type == TokenType.IDENTIFIER
        and tok.value == kw
        and parser._pos + 1 < len(parser._tokens)
        and parser._tokens[parser._pos + 1].type == TokenType.EQUALS
    ):
        parser._advance()
        parser._advance()
    return _probability(parser, f"{context} {kw}")


def _parse_truly_random(parser: _Parser) -> TrulyRandom:
    _consume_name(parser, "TrulyRandom")
    parser._expect(TokenType.LPAREN, "TrulyRandom opening paren")
    cs = _parse_optional_kw_stim(parser, "cs", "TrulyRandom")
    parser._expect(TokenType.COMMA, "TrulyRandom comma")
    us = _parse_optional_kw_stim(parser, "us", "TrulyRandom")
    p: float | None = None
    if parser._at(TokenType.COMMA):
        parser._advance()
        _parse_kwarg_key(parser, frozenset({"p"}), "TrulyRandom")
        p = _probability(parser, "TrulyRandom p")
    parser._expect(TokenType.RPAREN, "TrulyRandom closing paren")
    return TrulyRandom(cs=cs, us=us, p=p)


def _parse_explicitly_unpaired(parser: _Parser) -> ExplicitlyUnpaired:
    _consume_name(parser, "ExplicitlyUnpaired")
    parser._expect(TokenType.LPAREN, "ExplicitlyUnpaired opening paren")
    cs = _parse_optional_kw_stim(parser, "cs", "ExplicitlyUnpaired")
    parser._expect(TokenType.COMMA, "ExplicitlyUnpaired comma")
    us = _parse_optional_kw_stim(parser, "us", "ExplicitlyUnpaired")
    min_sep: Duration | None = None
    if parser._at(TokenType.COMMA):
        parser._advance()
        _parse_kwarg_key(
            parser, frozenset({"min_separation"}), "ExplicitlyUnpaired"
        )
        min_sep = _duration(parser, "ExplicitlyUnpaired min_separation")
    parser._expect(TokenType.RPAREN, "ExplicitlyUnpaired closing paren")
    return ExplicitlyUnpaired(cs=cs, us=us, min_separation=min_sep)


def _parse_compound(parser: _Parser) -> Compound:
    _consume_name(parser, "Compound")
    parser._expect(TokenType.LPAREN, "Compound opening paren")
    # cs_list= keyword required (grammar uses [ ... ])
    _parse_kwarg_key(parser, frozenset({"cs_list"}), "Compound")
    items = _parse_cs_list(parser, "Compound")
    mode = "Simultaneous"
    if parser._at(TokenType.COMMA):
        parser._advance()
        _parse_kwarg_key(parser, frozenset({"mode"}), "Compound")
        mode_tok = parser._peek()
        if mode_tok.type != TokenType.IDENTIFIER or mode_tok.value != "Simultaneous":
            raise ParseError(
                f"Compound mode must be 'Simultaneous', got {mode_tok.type.name} '{mode_tok.value}'",
                SourceSpan(mode_tok.line, mode_tok.col),
            )
        parser._advance()
        mode = "Simultaneous"
    parser._expect(TokenType.RPAREN, "Compound closing paren")
    return Compound(cs_list=items, mode=mode)


def _parse_serial(parser: _Parser) -> Serial:
    _consume_name(parser, "Serial")
    parser._expect(TokenType.LPAREN, "Serial opening paren")
    _parse_kwarg_key(parser, frozenset({"cs_list"}), "Serial")
    items = _parse_cs_list(parser, "Serial")
    parser._expect(TokenType.COMMA, "Serial comma")
    _parse_kwarg_key(parser, frozenset({"isi"}), "Serial")
    isi = _duration(parser, "Serial isi")
    parser._expect(TokenType.RPAREN, "Serial closing paren")
    return Serial(cs_list=items, isi=isi)


# The lexer tags "fixed", "uniform", "exponential" inconsistently:
# `fixed` is IDENTIFIER; `uniform` and `exponential` are PR_STEP. Recognize both.
_ITI_DISTRIBUTIONS: frozenset[str] = frozenset({"fixed", "uniform", "exponential"})


def _parse_iti(parser: _Parser) -> ITI:
    _consume_name(parser, "ITI")
    parser._expect(TokenType.LPAREN, "ITI opening paren")
    # distribution: positional or distribution=<name>
    tok = parser._peek()
    if (
        tok.type == TokenType.IDENTIFIER
        and tok.value == "distribution"
        and parser._pos + 1 < len(parser._tokens)
        and parser._tokens[parser._pos + 1].type == TokenType.EQUALS
    ):
        parser._advance()
        parser._advance()
    dist_tok = parser._peek()
    if dist_tok.value not in _ITI_DISTRIBUTIONS or dist_tok.type not in (
        TokenType.IDENTIFIER,
        TokenType.PR_STEP,
    ):
        raise ParseError(
            f"ITI distribution must be one of {sorted(_ITI_DISTRIBUTIONS)}, "
            f"got {dist_tok.type.name} '{dist_tok.value}'",
            SourceSpan(dist_tok.line, dist_tok.col),
        )
    parser._advance()
    distribution = dist_tok.value
    parser._expect(TokenType.COMMA, "ITI comma")
    _parse_kwarg_key(parser, frozenset({"mean"}), "ITI")
    mean = _duration(parser, "ITI mean")
    parser._expect(TokenType.RPAREN, "ITI closing paren")
    return ITI(distribution=distribution, mean=mean)


def _parse_differential(parser: _Parser) -> Differential:
    _consume_name(parser, "Differential")
    parser._expect(TokenType.LPAREN, "Differential opening paren")
    cs_pos = _parse_optional_kw_stim(
        parser, "cs_positive", "Differential"
    )
    parser._expect(TokenType.COMMA, "Differential comma")
    cs_neg = _parse_optional_kw_stim(
        parser, "cs_negative", "Differential"
    )
    us: str | None = None
    if parser._at(TokenType.COMMA):
        parser._advance()
        us = _parse_optional_kw_stim(parser, "us", "Differential")
    parser._expect(TokenType.RPAREN, "Differential closing paren")
    return Differential(cs_positive=cs_pos, cs_negative=cs_neg, us=us)


# --- Pair.* dispatch --------------------------------------------------------


def _parse_pair(parser: _Parser) -> RespondentExpr:
    """Parse Pair.<mode>(...) primitives (R1-R4)."""
    _consume_name(parser, "Pair")
    parser._expect(TokenType.DOT, "'.' after Pair")
    mode_tok = parser._peek()
    if mode_tok.type != TokenType.IDENTIFIER:
        raise ParseError(
            f"expected Pair mode identifier after '.', got {mode_tok.type.name} '{mode_tok.value}'",
            SourceSpan(mode_tok.line, mode_tok.col),
        )
    mode = mode_tok.value
    parser._advance()

    if mode == "ForwardDelay":
        return _parse_pair_forward_delay(parser)
    if mode == "ForwardTrace":
        return _parse_pair_forward_trace(parser)
    if mode == "Simultaneous":
        return _parse_pair_simultaneous(parser)
    if mode == "Backward":
        return _parse_pair_backward(parser)
    raise ParseError(
        f"unknown Pair mode '{mode}'; expected one of "
        f"ForwardDelay, ForwardTrace, Simultaneous, Backward",
        SourceSpan(mode_tok.line, mode_tok.col),
    )


def _parse_pair_forward_delay(parser: _Parser) -> PairForwardDelay:
    parser._expect(TokenType.LPAREN, "Pair.ForwardDelay opening paren")
    cs = _parse_optional_kw_stim(parser, "cs", "Pair.ForwardDelay")
    parser._expect(TokenType.COMMA, "Pair.ForwardDelay comma after cs")
    us = _parse_optional_kw_stim(parser, "us", "Pair.ForwardDelay")
    parser._expect(TokenType.COMMA, "Pair.ForwardDelay comma after us")
    # Remaining two args are isi and cs_duration (order-independent when keyword'd).
    kwargs = _parse_pair_kwargs(
        parser, allowed=frozenset({"isi", "cs_duration"}), context="Pair.ForwardDelay"
    )
    if "isi" not in kwargs or "cs_duration" not in kwargs:
        tok = parser._peek()
        missing = sorted({"isi", "cs_duration"} - kwargs.keys())
        raise ParseError(
            f"Pair.ForwardDelay missing keyword argument(s): {', '.join(missing)}",
            SourceSpan(tok.line, tok.col),
        )
    parser._expect(TokenType.RPAREN, "Pair.ForwardDelay closing paren")
    return PairForwardDelay(
        cs=cs, us=us, isi=kwargs["isi"], cs_duration=kwargs["cs_duration"]
    )


def _parse_pair_forward_trace(parser: _Parser) -> PairForwardTrace:
    parser._expect(TokenType.LPAREN, "Pair.ForwardTrace opening paren")
    cs = _parse_optional_kw_stim(parser, "cs", "Pair.ForwardTrace")
    parser._expect(TokenType.COMMA, "Pair.ForwardTrace comma after cs")
    us = _parse_optional_kw_stim(parser, "us", "Pair.ForwardTrace")
    parser._expect(TokenType.COMMA, "Pair.ForwardTrace comma after us")
    kwargs = _parse_pair_kwargs(
        parser,
        allowed=frozenset({"trace_interval", "cs_duration"}),
        context="Pair.ForwardTrace",
    )
    if "trace_interval" not in kwargs:
        tok = parser._peek()
        raise ParseError(
            "Pair.ForwardTrace missing required keyword argument: trace_interval",
            SourceSpan(tok.line, tok.col),
        )
    parser._expect(TokenType.RPAREN, "Pair.ForwardTrace closing paren")
    return PairForwardTrace(
        cs=cs,
        us=us,
        trace_interval=kwargs["trace_interval"],
        cs_duration=kwargs.get("cs_duration"),
    )


def _parse_pair_simultaneous(parser: _Parser) -> PairSimultaneous:
    parser._expect(TokenType.LPAREN, "Pair.Simultaneous opening paren")
    cs = _parse_optional_kw_stim(parser, "cs", "Pair.Simultaneous")
    parser._expect(TokenType.COMMA, "Pair.Simultaneous comma")
    us = _parse_optional_kw_stim(parser, "us", "Pair.Simultaneous")
    parser._expect(TokenType.RPAREN, "Pair.Simultaneous closing paren")
    return PairSimultaneous(cs=cs, us=us)


def _parse_pair_backward(parser: _Parser) -> PairBackward:
    parser._expect(TokenType.LPAREN, "Pair.Backward opening paren")
    # Positional order is (us, cs, isi) to match temporal order.
    us = _parse_optional_kw_stim(parser, "us", "Pair.Backward")
    parser._expect(TokenType.COMMA, "Pair.Backward comma after us")
    cs = _parse_optional_kw_stim(parser, "cs", "Pair.Backward")
    parser._expect(TokenType.COMMA, "Pair.Backward comma after cs")
    kwargs = _parse_pair_kwargs(
        parser, allowed=frozenset({"isi"}), context="Pair.Backward"
    )
    if "isi" not in kwargs:
        tok = parser._peek()
        raise ParseError(
            "Pair.Backward missing required keyword argument: isi",
            SourceSpan(tok.line, tok.col),
        )
    parser._expect(TokenType.RPAREN, "Pair.Backward closing paren")
    return PairBackward(us=us, cs=cs, isi=kwargs["isi"])


def _parse_pair_kwargs(
    parser: _Parser, *, allowed: frozenset[str], context: str
) -> dict[str, Duration]:
    """Parse zero or more trailing kwargs of the form key=<duration>."""
    kwargs: dict[str, Duration] = {}
    while True:
        tok = parser._peek()
        if tok.type != TokenType.IDENTIFIER:
            break
        if tok.value not in allowed:
            raise ParseError(
                f"unknown keyword argument '{tok.value}' in {context}; "
                f"expected one of {sorted(allowed)}",
                SourceSpan(tok.line, tok.col),
            )
        key = tok.value
        parser._advance()
        parser._expect(TokenType.EQUALS, f"{context} {key}=")
        kwargs[key] = _duration(parser, f"{context} {key}")
        if parser._at(TokenType.COMMA):
            parser._advance()
            continue
        break
    return kwargs
