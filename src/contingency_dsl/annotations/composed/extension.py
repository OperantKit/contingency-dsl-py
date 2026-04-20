"""ComposedExtension — implements ExtensionModule for composed-ext.

Provides @omission, @avoidance annotations that express response-contingent
US modulation rules layered on top of Tier A respondent primitives.
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from contingency_dsl.ast import AnnotatedSchedule, Annotation, ScheduleExpr

from .types import AvoidanceAnnotation, OmissionAnnotation


_OMISSION_DURING_VALUES = frozenset({"cs", "iti", "trial"})
_AVOIDANCE_MODES = frozenset({"cancel", "postpone"})


class ComposedExtension:
    """Composed-layer execution-semantics extension.

    Conforms to the ExtensionModule protocol. Registers the @omission
    and @avoidance annotation keywords; the validator enforces that
    required parameters are present and that enum-valued parameters
    (during, mode) take admissible values.
    """

    name: ClassVar[str] = "composed-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"omission", "avoidance"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {
            "omission": OmissionAnnotation,
            "avoidance": AvoidanceAnnotation,
        }

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Validate composed-ext annotations.

        Checks:
        1. @omission requires `response` (str); optional `during` must be
           one of {cs, iti, trial}.
        2. @avoidance requires `response` (str); optional `mode` must be
           one of {cancel, postpone}.
        """
        diagnostics: list[str] = []
        for ann in annotations:
            if not isinstance(ann, Annotation):
                continue
            if ann.keyword == "omission":
                diagnostics.extend(_validate_omission(ann))
            elif ann.keyword == "avoidance":
                diagnostics.extend(_validate_avoidance(ann))
        return diagnostics

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @staticmethod
    def extract(program_schedule: ScheduleExpr) -> list[OmissionAnnotation | AvoidanceAnnotation]:
        """Walk ``program_schedule`` and return typed annotation instances.

        Only @omission and @avoidance annotations are extracted. Other
        annotations present on the same AST node are ignored.
        """
        out: list[OmissionAnnotation | AvoidanceAnnotation] = []
        _collect(program_schedule, out)
        return out


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_omission(ann: Annotation) -> list[str]:
    diag: list[str] = []
    params = ann.params or {}
    response = params.get("response")
    if not isinstance(response, str) or not response:
        diag.append("@omission requires a string 'response' parameter")
    during = params.get("during")
    if during is not None and during not in _OMISSION_DURING_VALUES:
        diag.append(
            f"@omission 'during' must be one of {sorted(_OMISSION_DURING_VALUES)} "
            f"(got {during!r})"
        )
    unknown = set(params) - {"response", "during"}
    if unknown:
        diag.append(
            f"@omission has unknown parameter(s): {sorted(unknown)}"
        )
    return diag


def _validate_avoidance(ann: Annotation) -> list[str]:
    diag: list[str] = []
    params = ann.params or {}
    response = params.get("response")
    if not isinstance(response, str) or not response:
        diag.append("@avoidance requires a string 'response' parameter")
    mode = params.get("mode")
    if mode is not None and mode not in _AVOIDANCE_MODES:
        diag.append(
            f"@avoidance 'mode' must be one of {sorted(_AVOIDANCE_MODES)} "
            f"(got {mode!r})"
        )
    unknown = set(params) - {"response", "mode"}
    if unknown:
        diag.append(
            f"@avoidance has unknown parameter(s): {sorted(unknown)}"
        )
    return diag


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------


def _collect(
    expr: Any,
    out: list[OmissionAnnotation | AvoidanceAnnotation],
) -> None:
    """Recursively descend into the AST and extract composed-ext annotations."""
    from contingency_dsl.ast import Compound, LimitedHold, Modifier
    from contingency_dsl.experiment import Phase, PhaseSequence

    if isinstance(expr, PhaseSequence):
        for phase in expr.phases:
            _collect(phase, out)
        return

    if isinstance(expr, Phase):
        if expr.schedule is not None:
            _collect(expr.schedule, out)
        return

    if isinstance(expr, AnnotatedSchedule):
        for ann in expr.annotations:
            converted = _convert(ann)
            if converted is not None:
                out.append(converted)
        _collect(expr.expr, out)
        return

    if isinstance(expr, Compound):
        for comp in expr.components:
            _collect(comp, out)
        return

    if isinstance(expr, LimitedHold):
        _collect(expr.inner, out)
        return

    if isinstance(expr, Modifier) and expr.inner is not None:
        _collect(expr.inner, out)


def _convert(ann: Annotation) -> OmissionAnnotation | AvoidanceAnnotation | None:
    params = ann.params or {}
    response = params.get("response")
    if not isinstance(response, str):
        return None
    if ann.keyword == "omission":
        during = params.get("during", "cs")
        if during not in _OMISSION_DURING_VALUES:
            return None
        return OmissionAnnotation(response=response, during=during)
    if ann.keyword == "avoidance":
        mode = params.get("mode", "cancel")
        if mode not in _AVOIDANCE_MODES:
            return None
        return AvoidanceAnnotation(response=response, mode=mode)
    return None
