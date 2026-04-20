"""Annotation dataclasses for temporal-ext.

Frozen dataclasses representing parsed and validated temporal annotations
extracted from DSL program-level preamble: clock, warm-up, and the
algorithm used to materialise stochastic schedule values (VI/VR/RI/RR/VT).

References:
    Fleshler, M., & Hoffman, H. S. (1962). A progression for generating
        variable-interval schedules. Journal of the Experimental Analysis
        of Behavior, 5(4), 529-530. https://doi.org/10.1901/jeab.1962.5-529
    Hantula, D. A. (1991). A progression for generating variable-interval
        schedules. Journal of the Experimental Analysis of Behavior,
        56(2), 391-392. https://doi.org/10.1901/jeab.1991.56-391
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ClockAnnotation:
    """Parsed @clock annotation.

    Declares the session-wide time unit. Consumed by experiment-io, which
    binds the declared unit to a concrete hardware clock at session start.

    Examples:
        @clock(unit="s")
        @clock(unit="ms")
        @clock(unit="min")
    """

    unit: str


@dataclass(frozen=True)
class WarmupAnnotation:
    """Parsed @warmup annotation.

    Declares an initial period excluded from response/reinforcement records.
    The duration is expressed in the declared clock unit unless an explicit
    time_unit is attached.

    Examples:
        @warmup(duration=300)
        @warmup(duration=5min)
    """

    duration: float
    time_unit: str | None = None


@dataclass(frozen=True)
class AlgorithmAnnotation:
    """Parsed @algorithm annotation.

    Selects the parameter-generation algorithm for stochastic schedules.
    Consumed by contingency-py, which selects a parameter generator (e.g.
    Fleshler-Hoffman series) when materialising a stochastic schedule.

    Examples:
        @algorithm("fleshler-hoffman")
        @algorithm("fleshler-hoffman", n=12, seed=42)
        @algorithm("arithmetic", n=20)
    """

    name: str
    n: int | None = None
    seed: int | None = None


@dataclass(frozen=True)
class TemporalDeclarationSet:
    """All temporal declarations extracted from a single DSL program preamble.

    `clock` and `warmup` are program-scoped singletons. `algorithms` is keyed
    by the algorithm `name` so that multiple algorithm declarations (one per
    distinct generator) can coexist when a program drives mixed schedules.
    """

    clock: ClockAnnotation | None = None
    warmup: WarmupAnnotation | None = None
    algorithms: Mapping[str, AlgorithmAnnotation] = field(default_factory=dict)
