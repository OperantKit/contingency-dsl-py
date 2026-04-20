"""TemporalExtension — implements ExtensionModule for temporal-ext.

Provides @clock, @warmup, @algorithm annotations.
Schema: contingency-dsl/schema/annotations/procedure-temporal.schema.json.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from contingency_dsl.ast import Annotation, Program
from contingency_dsl.extensions import ExtensionModule

from .types import (
    AlgorithmAnnotation,
    ClockAnnotation,
    TemporalDeclarationSet,
    WarmupAnnotation,
)

_VALID_CLOCK_UNITS: frozenset[str] = frozenset({"s", "ms", "min"})
_KNOWN_ALGORITHMS: frozenset[str] = frozenset({"fleshler-hoffman", "arithmetic"})


class TemporalExtension:
    """Temporal & algorithmic-setup dimension extension.

    Conforms to the ExtensionModule protocol. Declares the session time
    unit, warm-up period, and the algorithm used to materialise stochastic
    schedule values. The declarations are intent only; the runtime layers
    (experiment-io, contingency-py) resolve them.
    """

    name: ClassVar[str] = "temporal-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"clock", "warmup", "algorithm"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {
            "clock": ClockAnnotation,
            "warmup": WarmupAnnotation,
            "algorithm": AlgorithmAnnotation,
        }

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Validate temporal-ext annotations.

        Checks:
        1. @clock unit must be one of {"s", "ms", "min"}.
        2. At most one @clock per program (declarative singleton).
        3. @warmup duration must be present and non-negative.
        4. @algorithm name must be present and a known generator.
        5. @algorithm n, when given, must be a positive integer.
        """
        diagnostics: list[str] = []
        clock_count = 0
        for ann in annotations:
            if not isinstance(ann, Annotation):
                continue
            if ann.keyword == "clock":
                clock_count += 1
                diagnostics.extend(_validate_clock(ann))
            elif ann.keyword == "warmup":
                diagnostics.extend(_validate_warmup(ann))
            elif ann.keyword == "algorithm":
                diagnostics.extend(_validate_algorithm(ann))
        if clock_count > 1:
            diagnostics.append(
                "CLOCK_MULTIPLE: at most one @clock annotation is permitted per program"
            )
        return diagnostics

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @staticmethod
    def extract_declarations(program: Program) -> TemporalDeclarationSet:
        """Extract a TemporalDeclarationSet from a Program's program_annotations."""
        clock: ClockAnnotation | None = None
        warmup: WarmupAnnotation | None = None
        algorithms: dict[str, AlgorithmAnnotation] = {}

        for ann in program.program_annotations:
            if ann.keyword == "clock":
                clock = _parse_clock(ann)
            elif ann.keyword == "warmup":
                warmup = _parse_warmup(ann)
            elif ann.keyword == "algorithm":
                algo = _parse_algorithm(ann)
                if algo is not None:
                    algorithms[algo.name] = algo

        return TemporalDeclarationSet(
            clock=clock,
            warmup=warmup,
            algorithms=algorithms,
        )


# ---------------------------------------------------------------------------
# Per-annotation validators
# ---------------------------------------------------------------------------


def _validate_clock(ann: Annotation) -> list[str]:
    params = ann.params or {}
    unit = params.get("unit")
    if unit is None:
        return ["CLOCK_MISSING_UNIT: @clock requires a 'unit' parameter"]
    if unit not in _VALID_CLOCK_UNITS:
        return [
            f"CLOCK_INVALID_UNIT: @clock unit must be one of "
            f"{sorted(_VALID_CLOCK_UNITS)}, got {unit!r}"
        ]
    return []


def _validate_warmup(ann: Annotation) -> list[str]:
    params = ann.params or {}
    duration = params.get("duration")
    if duration is None:
        return ["WARMUP_MISSING_DURATION: @warmup requires a 'duration' parameter"]
    numeric = _coerce_duration(duration)
    if numeric is None:
        return ["WARMUP_MISSING_DURATION: @warmup 'duration' must be a number"]
    if numeric < 0:
        return [
            f"WARMUP_NEGATIVE_DURATION: @warmup duration must be non-negative, "
            f"got {numeric}"
        ]
    return []


def _validate_algorithm(ann: Annotation) -> list[str]:
    diagnostics: list[str] = []
    name = ann.positional
    if not isinstance(name, str) or name == "":
        diagnostics.append(
            "ALGORITHM_MISSING_NAME: @algorithm requires a positional name argument"
        )
    elif name not in _KNOWN_ALGORITHMS:
        diagnostics.append(
            f"ALGORITHM_UNKNOWN: @algorithm name must be one of "
            f"{sorted(_KNOWN_ALGORITHMS)}, got {name!r}"
        )

    params = ann.params or {}
    n = params.get("n")
    if n is not None:
        if not isinstance(n, (int, float)) or isinstance(n, bool):
            diagnostics.append(
                f"ALGORITHM_INVALID_N: @algorithm 'n' must be a positive integer, "
                f"got {n!r}"
            )
        else:
            n_int = int(n)
            if n_int < 1 or n_int != n:
                diagnostics.append(
                    f"ALGORITHM_INVALID_N: @algorithm 'n' must be a positive integer, "
                    f"got {n!r}"
                )
    return diagnostics


# ---------------------------------------------------------------------------
# Per-annotation parsers
# ---------------------------------------------------------------------------


def _parse_clock(ann: Annotation) -> ClockAnnotation | None:
    params = ann.params or {}
    unit = params.get("unit")
    if not isinstance(unit, str):
        return None
    return ClockAnnotation(unit=unit)


def _parse_warmup(ann: Annotation) -> WarmupAnnotation | None:
    params = ann.params or {}
    duration = params.get("duration")
    numeric: float | None = None
    time_unit: str | None = None
    if isinstance(duration, dict):
        value = duration.get("value")
        if isinstance(value, (int, float)):
            numeric = float(value)
        unit = duration.get("time_unit")
        if isinstance(unit, str):
            time_unit = unit
    elif isinstance(duration, (int, float)):
        numeric = float(duration)
    if numeric is None:
        return None
    return WarmupAnnotation(duration=numeric, time_unit=time_unit)


def _parse_algorithm(ann: Annotation) -> AlgorithmAnnotation | None:
    name = ann.positional
    if not isinstance(name, str) or name == "":
        return None
    params = ann.params or {}
    n_raw = params.get("n")
    n: int | None = None
    if isinstance(n_raw, (int, float)) and not isinstance(n_raw, bool):
        n = int(n_raw)
    seed_raw = params.get("seed")
    seed: int | None = None
    if isinstance(seed_raw, (int, float)) and not isinstance(seed_raw, bool):
        seed = int(seed_raw)
    return AlgorithmAnnotation(name=name, n=n, seed=seed)


def _coerce_duration(value: Any) -> float | None:
    """Accept either a bare number or a {value, time_unit} dict."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return float(inner)
    return None


# Static check: TemporalExtension conforms to ExtensionModule Protocol.
_: ExtensionModule = TemporalExtension()
