"""MeasurementExtension — implements ExtensionModule for measurement-ext.

Provides @session_end, @baseline, @steady_state annotations.
Schema: contingency-dsl/schema/annotations/measurement.schema.json.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from contingency_dsl.ast import Annotation, Program

from .types import (
    BaselineAnnotation,
    MeasurementDeclarationSet,
    SessionEndAnnotation,
    SteadyStateAnnotation,
)
from .validator import validate_measurement_annotation


class MeasurementExtension:
    """Measurement dimension extension (JEAB Methods: Measurement section).

    Conforms to the ExtensionModule protocol.

    Phase 1 (this implementation): @session_end, @baseline, @steady_state
    Phase 2 (planned): @dependent_measure, @training_volume, @microstructure,
                       @phase_end, @logging, @iri_window, @warmup_exclude
    """

    name: ClassVar[str] = "measurement-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({
            # Phase 1 — validated
            "session_end",
            "baseline",
            "steady_state",
            # Phase 2 — registered but not yet validated
            "dependent_measure",
            "training_volume",
            "microstructure",
            "phase_end",
            "logging",
            "iri_window",
            "warmup_exclude",
        })

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {
            "session_end": SessionEndAnnotation,
            "baseline": BaselineAnnotation,
            "steady_state": SteadyStateAnnotation,
        }

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Validate measurement annotations.

        Phase 1: validates session_end, baseline, steady_state constraints.
        Phase 2 keywords are registered but pass through without diagnostics.
        """
        diagnostics: list[str] = []
        for ann in annotations:
            if isinstance(ann, Annotation) and ann.keyword in self.annotation_keywords:
                params = ann.params or {}
                for diag in validate_measurement_annotation(ann.keyword, params):
                    diagnostics.append(f"{diag.code}: {diag.message}")
        return diagnostics

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @staticmethod
    def extract_declarations(program: Program) -> MeasurementDeclarationSet:
        """Extract MeasurementDeclarationSet from a Program's program_annotations."""
        session_end: SessionEndAnnotation | None = None
        baseline: BaselineAnnotation | None = None
        steady_state: SteadyStateAnnotation | None = None

        for ann in program.program_annotations:
            if ann.keyword == "session_end":
                session_end = _parse_session_end(ann)
            elif ann.keyword == "baseline":
                baseline = _parse_baseline(ann)
            elif ann.keyword == "steady_state":
                steady_state = _parse_steady_state(ann)

        return MeasurementDeclarationSet(
            session_end=session_end,
            baseline=baseline,
            steady_state=steady_state,
        )


def _parse_session_end(ann: Annotation) -> SessionEndAnnotation:
    """Parse @session_end annotation into SessionEndAnnotation."""
    params = ann.params or {}
    rule = params.get("rule", "first")

    time_val = params.get("time")
    time_seconds: float | None = None
    time_unit: str | None = None
    if isinstance(time_val, dict):
        time_seconds = float(time_val["value"])
        time_unit = time_val.get("time_unit")
    elif isinstance(time_val, (int, float)):
        time_seconds = float(time_val)

    reinforcers = params.get("reinforcers")
    reinforcers_int: int | None = None
    if isinstance(reinforcers, (int, float)):
        reinforcers_int = int(reinforcers)

    return SessionEndAnnotation(
        rule=rule,
        time=time_seconds,
        time_unit=time_unit,
        reinforcers=reinforcers_int,
    )


def _parse_baseline(ann: Annotation) -> BaselineAnnotation:
    """Parse @baseline annotation into BaselineAnnotation."""
    params = ann.params or {}
    sessions = params.get("pre_training_sessions", 1)
    if isinstance(sessions, float):
        sessions = int(sessions)
    measure = params.get("measure", "operant_level")
    return BaselineAnnotation(
        pre_training_sessions=int(sessions),
        measure=measure,
    )


def _parse_steady_state(ann: Annotation) -> SteadyStateAnnotation:
    """Parse @steady_state annotation into SteadyStateAnnotation."""
    params = ann.params or {}
    window = params.get("window_sessions", 5)
    if isinstance(window, float):
        window = int(window)
    max_change = params.get("max_change_pct", 10.0)
    if isinstance(max_change, int):
        max_change = float(max_change)
    measure = params.get("measure", "rate")
    min_sessions = params.get("min_sessions")
    if isinstance(min_sessions, float):
        min_sessions = int(min_sessions)
    return SteadyStateAnnotation(
        window_sessions=int(window),
        max_change_pct=float(max_change),
        measure=measure,
        min_sessions=int(min_sessions) if min_sessions is not None else None,
    )
