"""Token types and Token dataclass for the contingency-dsl lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
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
    PR_STEP = auto()  # hodos, exponential, linear
    PR_PARAM = auto()  # start, increment
    # Identifier (user-defined name)
    IDENTIFIER = auto()
    # Annotation prefix: @
    AT = auto()
    # String literal: "..."
    STRING_LITERAL = auto()
    # End of file
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    col: int
