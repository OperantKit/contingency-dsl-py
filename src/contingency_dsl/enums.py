"""Enumerations for the contingency-dsl type system.

The 3x3 atomic schedule grid: Distribution x Domain.

References:
    Ferster, C. B., & Skinner, B. F. (1957). Schedules of reinforcement.
    Catania, A. C. (2013). Learning (5th ed.).
"""

from __future__ import annotations

from enum import Enum


class Distribution(Enum):
    """How the schedule parameter is selected across cycles."""

    FIXED = "F"  # Deterministic constant
    VARIABLE = "V"  # Fleshler-Hoffman (1962) mean-preserving
    RANDOM = "R"  # Independent uniform sampling per trial


class Domain(Enum):
    """Which behavioral dimension controls reinforcement."""

    RATIO = "R"  # Response count
    INTERVAL = "I"  # Time + first response
    TIME = "T"  # Time only (response-independent)


class Combinator(Enum):
    """Compound schedule combinators (7 total)."""

    CONC = "Conc"  # Parallel, independent
    ALT = "Alt"  # Parallel, OR
    CONJ = "Conj"  # Parallel, AND
    CHAIN = "Chain"  # Sequential, discriminated
    TAND = "Tand"  # Sequential, undiscriminated
    MULT = "Mult"  # Alternating, discriminated
    MIX = "Mix"  # Alternating, undiscriminated


# Schedule type keywords: all 3x3 combinations
SCHEDULE_TYPE_KEYWORDS: frozenset[str] = frozenset(
    f"{d.value}{dom.value}" for d in Distribution for dom in Domain
)

# All uppercase-initial keywords (used for lexer disambiguation)
COMBINATOR_KEYWORDS: frozenset[str] = frozenset(c.value for c in Combinator)

DR_KEYWORDS: frozenset[str] = frozenset({"DRL", "DRH", "DRO"})

SPECIAL_KEYWORDS: frozenset[str] = frozenset({"EXT", "CRF"})

# Lowercase reserved words (cannot be used as identifiers)
LOWERCASE_RESERVED: frozenset[str] = frozenset({
    "let",
    "def",
    "hodos",
    "exponential",
    "linear",
    "start",
    "increment",
})

ALL_RESERVED: frozenset[str] = (
    SCHEDULE_TYPE_KEYWORDS
    | COMBINATOR_KEYWORDS
    | DR_KEYWORDS
    | SPECIAL_KEYWORDS
    | frozenset({"LH", "PR", "Repeat"})
    | LOWERCASE_RESERVED
)
