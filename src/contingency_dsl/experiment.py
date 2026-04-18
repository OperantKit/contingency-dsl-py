"""AST nodes for the contingency-dsl experiment layer.

The experiment layer sits above individual schedule expressions. A
`PhaseSequence` is an ordered list of `Phase` objects, each of which pairs a
schedule (operant, respondent, null, or phase-reference) with a stopping
criterion and phase-local annotations.

AST shapes mirror the schema definitions under
`contingency-dsl/schema/experiment/`. See
`contingency-dsl/conformance/experiment/` for the canonical serialized form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .ast import Annotation, ScheduleExpr


# --- Stopping criteria ---


@dataclass(frozen=True)
class FixedSessions:
    """Phase terminates after exactly `count` sessions."""

    count: int


@dataclass(frozen=True)
class Stability:
    """Phase terminates when a stability metric is satisfied.

    Kept deliberately loose to accommodate the visual / cv / rate / iri /
    latency method families without multiplying node types; the schema
    constrains which fields are meaningful for each method.
    """

    method: str  # "visual" | "cv" | "rate" | "iri" | "latency"
    window_sessions: int | None = None
    max_change_pct: float | None = None
    min_sessions: int | None = None
    measure: str | None = None  # "rate" | "iri" | "latency" | "reinforcers"


@dataclass(frozen=True)
class ExperimenterJudgment:
    """Phase terminates at the experimenter's discretion (no data criterion)."""


@dataclass(frozen=True)
class CumulativeReinforcements:
    """Phase terminates after `count` cumulative reinforcers."""

    count: int


@dataclass(frozen=True)
class PerformanceCriterion:
    """Phase terminates when a scalar measure crosses a threshold."""

    measure: str
    threshold: float
    op: str  # ">=" | "<=" | ">" | "<" | "=="
    window_sessions: int | None = None


Criterion = Union[
    FixedSessions,
    Stability,
    ExperimenterJudgment,
    CumulativeReinforcements,
    PerformanceCriterion,
]


# --- Phase body sentinels ---


@dataclass(frozen=True)
class PhaseRef:
    """Reference to a previously declared phase's schedule (`use <Label>`)."""

    ref: str


# The "schedule" slot on a Phase admits a ScheduleExpr, None (Pavlovian
# revaluation / no-schedule), or a PhaseRef awaiting analyzer resolution.
PhaseSchedule = Union[ScheduleExpr, PhaseRef, None]


# --- Phase and top-level sequence ---


@dataclass(frozen=True)
class Phase:
    """Single phase within a phase sequence.

    Keeps an explicit ``criterion`` slot because every fixture that names a
    criterion expects it in the serialized form. A None criterion is legal
    for terminal phases that rely on a shared / default stopping rule.
    """

    label: str
    schedule: PhaseSchedule = None
    criterion: Criterion | None = None
    phase_annotations: tuple[Annotation, ...] = ()


@dataclass(frozen=True)
class PhaseSequence:
    """Top-level AST node for experiment-layer inputs.

    `shared_annotations` carry experiment-level metadata (species, strain,
    reinforcer, etc.) that applies to every phase unless overridden by a
    phase-local annotation. `parse_warnings` carries non-fatal diagnostics
    (e.g., `ADVANCE_SINGLE_STEP`) raised by the experiment-layer parser so
    the analyzer can surface them without re-walking the source tokens.
    """

    phases: tuple[Phase, ...]
    shared_annotations: tuple[Annotation, ...] = ()
    parse_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Experiment:
    """Single experiment wrapper inside a Paper.

    body is a `Program` for single-schedule experiments or a `PhaseSequence`
    for multi-phase experiments. The exact Python type is not imported here
    to avoid circular imports; the serializer dispatches on the runtime type.
    """

    label: str
    body: object  # Program | PhaseSequence


@dataclass(frozen=True)
class Paper:
    """Top-level wrapper grouping multiple Experiments as they appear in a
    publication. `shared_annotations` are inherited by every experiment
    unless overridden by a per-experiment annotation with the same keyword.
    """

    experiments: tuple[Experiment, ...]
    shared_annotations: tuple[Annotation, ...] = ()
