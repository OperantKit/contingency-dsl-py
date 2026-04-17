"""Respondent (two-term, CS-US) Tier A primitive AST nodes.

Mirrors schema/respondent/ast.schema.json. Every node is an immutable
frozen dataclass. Duration and Probability are modeled as simple value
types because the respondent layer only needs them as literal parameter
values (no arithmetic at parse time).

References:
    Pavlov (1927), Rescorla (1967, 1968), Mackintosh (1974).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


# --- Shared value types ---


@dataclass(frozen=True)
class Duration:
    """Time-valued parameter with an explicit unit.

    Mirrors schema/foundations/types.schema.json#/$defs/Duration.
    """

    value: float
    unit: str  # "s", "ms", "min"


# Probability is just a float in [0, 1]; validation is semantic (Phase 2).
Probability = float

# StimulusRef is a string identifier or literal label.
StimulusRef = str


# --- Tier A primitive nodes (R1-R14) ---


@dataclass(frozen=True)
class PairForwardDelay:
    """R1. CS onset precedes US onset; CS continues through US onset.

    Pavlov (1927). `Pair.ForwardDelay(cs, us, isi, cs_duration)`.
    """

    cs: StimulusRef
    us: StimulusRef
    isi: Duration
    cs_duration: Duration


@dataclass(frozen=True)
class PairForwardTrace:
    """R2. CS offset precedes US onset; trace gap separates them.

    Ellison (1964). `Pair.ForwardTrace(cs, us, trace_interval)`.
    """

    cs: StimulusRef
    us: StimulusRef
    trace_interval: Duration
    cs_duration: Duration | None = None


@dataclass(frozen=True)
class PairSimultaneous:
    """R3. CS onset equals US onset.

    Rescorla (1980). `Pair.Simultaneous(cs, us)`.
    """

    cs: StimulusRef
    us: StimulusRef


@dataclass(frozen=True)
class PairBackward:
    """R4. US onset precedes CS onset.

    Spetch, Wilkie, & Pinel (1981). `Pair.Backward(us, cs, isi)`.
    Source-text argument order is (us, cs) to match temporal order.
    """

    us: StimulusRef
    cs: StimulusRef
    isi: Duration


@dataclass(frozen=True)
class Extinction:
    """R5. CS-alone presentations after an acquisition history.

    Pavlov (1927); Bouton (2004). `Extinction(cs)`.
    """

    cs: StimulusRef


@dataclass(frozen=True)
class CSOnly:
    """R6. CS presentations without US (phase-independent).

    Lubow & Moore (1959). `CSOnly(cs, trials)`.
    """

    cs: StimulusRef
    trials: int


@dataclass(frozen=True)
class USOnly:
    """R7. US presentations without CS.

    Randich & LoLordo (1979). `USOnly(us, trials)`.
    """

    us: StimulusRef
    trials: int


@dataclass(frozen=True)
class Contingency:
    """R8. Point in the Rescorla (1967) contingency space.

    `Contingency(p_us_given_cs, p_us_given_no_cs)`. Argument order is
    fixed (CS-conditional first) and NOT permutable.
    """

    p_us_given_cs: Probability
    p_us_given_no_cs: Probability


@dataclass(frozen=True)
class TrulyRandom:
    """R9. Syntactic sugar for Contingency(p, p) on the diagonal.

    Rescorla (1967). `TrulyRandom(cs, us)` or `TrulyRandom(cs, us, p=...)`.
    """

    cs: StimulusRef
    us: StimulusRef
    p: Probability | None = None


@dataclass(frozen=True)
class ExplicitlyUnpaired:
    """R10. Contingency(0, p) with temporal-separation constraint.

    Ayres, Benedict, & Witcher (1975). `ExplicitlyUnpaired(cs, us, min_separation=...)`.
    """

    cs: StimulusRef
    us: StimulusRef
    min_separation: Duration | None = None


@dataclass(frozen=True)
class Compound:
    """R11. Multiple CSs presented together.

    Rescorla & Wagner (1972). `Compound(cs_list=[...], mode=Simultaneous)`.
    Default mode is "Simultaneous".
    """

    cs_list: tuple[StimulusRef, ...]
    mode: str = "Simultaneous"


@dataclass(frozen=True)
class Serial:
    """R12. Multiple CSs in temporal order.

    Rescorla (1972). `Serial(cs_list=[...], isi=...)`.
    """

    cs_list: tuple[StimulusRef, ...]
    isi: Duration


@dataclass(frozen=True)
class ITI:
    """R13. Intertrial-interval structural element.

    `ITI(distribution, mean=...)`. distribution ∈ {fixed, uniform, exponential}.
    """

    distribution: str
    mean: Duration


@dataclass(frozen=True)
class Differential:
    """R14. Differential conditioning: CS+ vs CS- contrast.

    Pavlov (1927); Mackintosh (1974).
    `Differential(cs_positive=..., cs_negative=..., us=...)`. The `us` is
    optional in the short form (US inferred from enclosing @us annotation).
    """

    cs_positive: StimulusRef
    cs_negative: StimulusRef
    us: StimulusRef | None = None


# Union over all Tier A respondent primitives.
RespondentExpr = Union[
    PairForwardDelay,
    PairForwardTrace,
    PairSimultaneous,
    PairBackward,
    Extinction,
    CSOnly,
    USOnly,
    Contingency,
    TrulyRandom,
    ExplicitlyUnpaired,
    Compound,
    Serial,
    ITI,
    Differential,
]


# Type name mapping for (de)serialization — mirrors the JSON Schema
# `type` discriminator.
RESPONDENT_TYPE_NAMES: dict[type, str] = {
    PairForwardDelay: "PairForwardDelay",
    PairForwardTrace: "PairForwardTrace",
    PairSimultaneous: "PairSimultaneous",
    PairBackward: "PairBackward",
    Extinction: "Extinction",
    CSOnly: "CSOnly",
    USOnly: "USOnly",
    Contingency: "Contingency",
    TrulyRandom: "TrulyRandom",
    ExplicitlyUnpaired: "ExplicitlyUnpaired",
    Compound: "Compound",
    Serial: "Serial",
    ITI: "ITI",
    Differential: "Differential",
}
