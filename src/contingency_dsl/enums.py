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
    """Compound schedule combinators."""

    CONC = "Conc"  # Parallel, independent
    ALT = "Alt"  # Parallel, OR
    CONJ = "Conj"  # Parallel, AND
    CHAIN = "Chain"  # Sequential, discriminated
    TAND = "Tand"  # Sequential, undiscriminated
    MULT = "Mult"  # Alternating, discriminated
    MIX = "Mix"  # Alternating, undiscriminated
    OVERLAY = "Overlay"  # Punishment overlay (Azrin & Holz, 1966)
    INTERPOLATE = "Interpolate"  # Mid-session schedule change (interpolated probe)
    INTERP = "Interp"  # Short alias for Interpolate


# Schedule type keywords: all 3x3 combinations
SCHEDULE_TYPE_KEYWORDS: frozenset[str] = frozenset(
    f"{d.value}{dom.value}" for d in Distribution for dom in Domain
)

# All uppercase-initial keywords (used for lexer disambiguation)
COMBINATOR_KEYWORDS: frozenset[str] = frozenset(c.value for c in Combinator)

DR_KEYWORDS: frozenset[str] = frozenset({"DRL", "DRH", "DRO"})

# Compound keyword argument names (COD, FRCO, BO, PUNISH and their aliases)
KW_ARG_KEYWORDS: dict[str, str] = {
    "COD": "COD", "ChangeoverDelay": "COD",
    "FRCO": "FRCO", "FixedRatioChangeover": "FRCO",
    "BO": "BO", "Blackout": "BO",
    "PUNISH": "PUNISH",
}

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
    | frozenset({"LH", "RD", "ReinforcementDelay", "PR", "Repeat"})
    | frozenset(KW_ARG_KEYWORDS.keys())
    | LOWERCASE_RESERVED
)

# Experiment-layer keywords (classified only when the lexer is in block mode,
# triggered by the source containing a whole-word `phase`, `progressive`, or
# `shaping`). Keeping these out of LOWERCASE_RESERVED preserves backward
# compatibility for flat-mode inputs that happen to use these words as
# identifiers.
EXPERIMENT_BLOCK_TRIGGERS: frozenset[str] = frozenset({
    "phase", "progressive", "shaping", "experiment",
})
EXPERIMENT_LAYER_KEYWORDS: frozenset[str] = frozenset({
    "phase", "sessions", "stable", "use", "no_schedule",
    "shaping", "progressive", "steps", "interleave", "no_trailing",
    "advance", "when", "experiment",
})
