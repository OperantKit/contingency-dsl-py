"""Token types and Token dataclass for the contingency-dsl lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """Lexical token categories produced by :mod:`contingency_dsl.lexer`.

    Each member corresponds to a single terminal in the DSL grammar
    (``schema/operant/grammar.ebnf``). Values are auto-assigned and
    carry no semantic meaning; equality and identity comparisons are
    performed on members rather than numeric codes.
    """

    # Atomic schedule type: FR, VR, RR, FI, VI, RI, FT, VT, RT
    SCHEDULE_TYPE = auto()
    # Numeric literal
    NUMBER = auto()
    # Time unit: s, ms, min
    TIME_UNIT = auto()
    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    EQUALS = auto()
    ARROW = auto()  # -> (directional keyword arg: COD(1->2)=2s)
    LBRACKET = auto()  # [ (list literal: annotation arrays and respondent cs_list)
    RBRACKET = auto()  # ] (list literal: annotation arrays and respondent cs_list)
    LBRACE = auto()  # { (object literal: @trial_mix components)
    RBRACE = auto()  # } (object literal: @trial_mix components)
    DOT = auto()  # . (dotted primitive: Pair.ForwardDelay)
    MINUS = auto()  # - (negative annotation values)
    # Keywords
    LET = auto()
    LH = auto()
    RD = auto()  # ReinforcementDelay (program-level param_decl only)
    EXT = auto()
    CRF = auto()
    COMBINATOR = auto()  # Conc, Alt, Conj, Chain, Tand, Mult, Mix
    KW_ARG_NAME = auto()  # COD, ChangeoverDelay, FRCO, FixedRatioChangeover, BO, Blackout
    DR_MOD = auto()  # DRL, DRH, DRO
    PR = auto()
    REPEAT = auto()
    DISTRIBUTION_NAME = auto()  # hodos, linear, exponential, uniform, fixed (cross-layer; see schema/foundations/grammar.ebnf)
    PR_PARAM = auto()  # start, increment
    # Identifier (user-defined name)
    IDENTIFIER = auto()
    # Annotation prefix: @
    AT = auto()
    # String literal: "..."
    STRING_LITERAL = auto()
    # Experiment-layer block syntax (emitted only in block-mode lexing)
    COLON = auto()  # : (phase/progressive/shaping header terminator)
    NEWLINE = auto()  # logical line break inside a block
    INDENT = auto()  # indent level increase
    DEDENT = auto()  # indent level decrease
    GTE = auto()  # >= (sessions >= N)
    PERCENT = auto()  # % (threshold=5%)
    # Experiment-layer keywords (only classified in block mode)
    PHASE = auto()
    SESSIONS = auto()
    STABLE = auto()
    USE = auto()
    NO_SCHEDULE = auto()
    SHAPING = auto()
    PROGRESSIVE = auto()
    STEPS = auto()
    INTERLEAVE = auto()
    NO_TRAILING = auto()
    ADVANCE = auto()
    WHEN = auto()
    # Paper-layer: `experiment <label>:` block keyword
    EXPERIMENT = auto()
    # Placeholder `{ident}` used in progressive schedule templates to expand
    # per step.
    PLACEHOLDER = auto()
    # End of file
    EOF = auto()


@dataclass(frozen=True)
class Token:
    """A single lexical token emitted by the lexer.

    Attributes carry the token category, its source lexeme, and the 1-based
    source position used when constructing :class:`~contingency_dsl.errors.SourceSpan`
    for diagnostic messages.
    """

    type: TokenType
    value: str
    line: int
    col: int
