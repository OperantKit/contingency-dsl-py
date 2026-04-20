"""Annotation dataclasses for measurement-ext.

Frozen dataclasses representing parsed and validated measurement annotations
extracted from DSL program-level preamble.

References:
    Baron, A., & Perone, M. (1998). Experimental design and analysis in the
        laboratory study of human operant behavior. In K. A. Lattal & M.
        Perone (Eds.), Handbook of research methods in human operant behavior
        (pp. 45-91). Plenum Press.
    Sidman, M. (1960). Tactics of scientific research. Basic Books.
    Skinner, B. F. (1938). The behavior of organisms. Appleton-Century-Crofts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SessionEndAnnotation:
    """Parsed @session_end annotation.

    Defines session termination criteria.
    Baron & Perone (1998) session-ending conventions.
    """

    rule: Literal["first", "time_only", "reinforcers_only"]
    time: float | None = None          # seconds (from time_value, normalized)
    time_unit: str | None = None       # original unit for roundtrip
    reinforcers: int | None = None


@dataclass(frozen=True)
class BaselineAnnotation:
    """Parsed @baseline annotation.

    Baseline/operant level measurement.
    Skinner (1938) operant level concept.
    """

    pre_training_sessions: int
    measure: Literal["operant_level", "no_training", "custom"] = "operant_level"


@dataclass(frozen=True)
class SteadyStateAnnotation:
    """Parsed @steady_state annotation.

    Phase stability criteria.
    Sidman (1960) steady-state strategy.
    """

    window_sessions: int
    max_change_pct: float
    measure: Literal["rate", "reinforcers", "iri", "latency", "custom"] = "rate"
    min_sessions: int | None = None  # defaults to window_sessions at runtime


@dataclass(frozen=True)
class MeasurementDeclarationSet:
    """All measurement declarations from a DSL program's preamble."""

    session_end: SessionEndAnnotation | None = None
    baseline: BaselineAnnotation | None = None
    steady_state: SteadyStateAnnotation | None = None
