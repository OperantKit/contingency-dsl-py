"""Analyzer for composed-layer annotations.

Produces an ``ExecutionPlan`` for each ``@omission`` / ``@avoidance``
annotation found in a ``Program`` or ``PhaseSequence``: the structured
runtime instruction that a session executor interprets.

An ExecutionPlan pairs a typed annotation (:class:`OmissionAnnotation`
or :class:`AvoidanceAnnotation`) with the enclosing Pavlovian primitive
(Pair.* or similar respondent expression) and the phase label (if any)
in which the rule applies. Runtimes consume ExecutionPlans to decide
whether a given recorded response cancels or postpones the scheduled US
on a given trial.

The analyzer also validates structural consistency:

1. An ``@omission`` / ``@avoidance`` annotation must attach to a
   respondent primitive capable of carrying a US (``PairForwardDelay``,
   ``PairForwardTrace``, ``PairSimultaneous``, ``PairBackward``). Attaching
   it to an ``Extinction`` / ``CSOnly`` / ``USOnly`` primitive — none of
   which pair a US with a response-eligible CS window — is a semantic
   error because the cancellation rule has no US to cancel.
2. At most one of ``@omission`` / ``@avoidance`` may attach to the same
   primitive (their semantics conflict).
3. ``during="cs"`` (the @omission default) is only meaningful on a
   primitive that has a CS window; the Pair.* family satisfies this by
   construction.

Diagnostics are reported as ``str`` messages; a sentinel
:class:`ComposedAnalysisError` is raised when analysis is invoked with
``strict=True`` and at least one diagnostic is produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .types import AvoidanceAnnotation, OmissionAnnotation


# Names of respondent primitives that host a US and can therefore
# legally carry an @omission / @avoidance annotation. Resolved as
# ``type(node).__name__`` so this package does not import respondent
# AST classes directly (avoids circular dependency risk).
_US_BEARING_PAIRS: frozenset[str] = frozenset({
    "PairForwardDelay",
    "PairForwardTrace",
    "PairSimultaneous",
    "PairBackward",
})


class ComposedAnalysisError(ValueError):
    """Raised when strict analysis finds semantic violations."""


@dataclass(frozen=True)
class ExecutionPlan:
    """Runtime-consumable instruction for one cancellation / postponement rule.

    Attributes:
        rule: Typed annotation (``OmissionAnnotation`` or ``AvoidanceAnnotation``).
        pair_type: ``type(...).__name__`` of the enclosing respondent primitive.
        cs: CS identifier from the enclosing primitive.
        us: US identifier from the enclosing primitive.
        phase_label: Phase label if the annotation is inside a ``Phase`` node;
            ``None`` for flat ``Program``-level occurrences.
    """

    rule: OmissionAnnotation | AvoidanceAnnotation
    pair_type: str
    cs: str
    us: str
    phase_label: str | None = None


@dataclass
class AnalysisResult:
    """Result of composed-layer analysis."""

    plans: list[ExecutionPlan] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.diagnostics


def analyze(program_or_phase_sequence: Any, *, strict: bool = False) -> AnalysisResult:
    """Walk *program_or_phase_sequence* and return an :class:`AnalysisResult`.

    Args:
        program_or_phase_sequence: A ``Program`` or ``PhaseSequence`` AST
            as produced by :func:`contingency_dsl.parse` (possibly after
            :func:`contingency_dsl.analyze`).
        strict: When True, raise :class:`ComposedAnalysisError` instead of
            returning the result whenever diagnostics are non-empty.

    Returns:
        AnalysisResult with one ``ExecutionPlan`` per attached
        ``@omission`` / ``@avoidance`` annotation, plus any diagnostic
        strings produced during structural validation.
    """
    result = AnalysisResult()
    _walk(program_or_phase_sequence, None, result)

    if strict and result.diagnostics:
        raise ComposedAnalysisError(
            "composed-layer analysis found "
            f"{len(result.diagnostics)} diagnostic(s): "
            + "; ".join(result.diagnostics)
        )
    return result


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------


def _walk(node: Any, phase_label: str | None, result: AnalysisResult) -> None:
    """Dispatch on AST node kind and recurse into children.

    The walker is intentionally type-name driven (``type(node).__name__``)
    rather than using ``isinstance`` against imported classes; this lets
    the composed_ext package stay loosely coupled to contingency_dsl's
    respondent / experiment class set.
    """
    if node is None:
        return

    type_name = type(node).__name__

    if type_name == "PhaseSequence":
        for phase in getattr(node, "phases", ()):
            _walk(phase, getattr(phase, "label", None), result)
        return

    if type_name == "Phase":
        _walk(getattr(node, "schedule", None), phase_label or getattr(node, "label", None), result)
        return

    if type_name == "Program":
        _walk(getattr(node, "schedule", None), phase_label, result)
        return

    if type_name == "AnnotatedSchedule":
        inner = getattr(node, "expr", None)
        annotations = getattr(node, "annotations", ())
        _process_annotated_schedule(inner, annotations, phase_label, result)
        _walk(inner, phase_label, result)
        return

    if type_name == "Compound":
        for component in getattr(node, "components", ()):
            _walk(component, phase_label, result)
        return

    if type_name == "LimitedHold":
        _walk(getattr(node, "inner", None), phase_label, result)
        return

    if type_name == "Modifier":
        _walk(getattr(node, "inner", None), phase_label, result)
        return


# ---------------------------------------------------------------------------
# Per-node processing
# ---------------------------------------------------------------------------


def _process_annotated_schedule(
    inner: Any,
    annotations: Iterable[Any],
    phase_label: str | None,
    result: AnalysisResult,
) -> None:
    """Extract composed-ext annotations from an AnnotatedSchedule node.

    Performs structural validation:
    - Inner must be a US-bearing respondent pair.
    - At most one of @omission / @avoidance per node.
    """
    inner_type = type(inner).__name__ if inner is not None else "None"

    composed_annotations = [
        a
        for a in annotations
        if getattr(a, "keyword", None) in ("omission", "avoidance")
    ]
    if not composed_annotations:
        return

    if inner_type not in _US_BEARING_PAIRS:
        for a in composed_annotations:
            result.diagnostics.append(
                f"@{a.keyword} attached to {inner_type!r}, but composed-ext "
                f"cancellation / postponement rules require a US-bearing "
                f"respondent primitive (one of {sorted(_US_BEARING_PAIRS)})"
            )
        return

    if len(composed_annotations) > 1:
        keywords = sorted({a.keyword for a in composed_annotations})
        if len(keywords) > 1:
            result.diagnostics.append(
                f"conflicting composed-ext annotations on the same primitive: "
                f"{keywords} — at most one of @omission / @avoidance is admissible"
            )
            return
        result.diagnostics.append(
            f"multiple @{keywords[0]} annotations on the same primitive — "
            f"at most one is admissible"
        )
        return

    annotation = composed_annotations[0]
    rule = _typed_rule(annotation, result)
    if rule is None:
        return

    cs = getattr(inner, "cs", None)
    us = getattr(inner, "us", None)
    if not isinstance(cs, str) or not isinstance(us, str):
        result.diagnostics.append(
            f"@{annotation.keyword}: enclosing {inner_type} has non-string cs/us "
            f"references (cs={cs!r}, us={us!r})"
        )
        return

    result.plans.append(
        ExecutionPlan(
            rule=rule,
            pair_type=inner_type,
            cs=cs,
            us=us,
            phase_label=phase_label,
        )
    )


def _typed_rule(
    annotation: Any, result: AnalysisResult
) -> OmissionAnnotation | AvoidanceAnnotation | None:
    """Convert a raw ``Annotation`` into a typed rule, recording diagnostics."""
    params = getattr(annotation, "params", None) or {}
    keyword = getattr(annotation, "keyword", None)

    response = params.get("response")
    if not isinstance(response, str) or not response:
        result.diagnostics.append(
            f"@{keyword}: 'response' parameter is required (got {response!r})"
        )
        return None

    if keyword == "omission":
        during = params.get("during", "cs")
        if during not in ("cs", "iti", "trial"):
            result.diagnostics.append(
                f"@omission: 'during' must be one of cs/iti/trial (got {during!r})"
            )
            return None
        return OmissionAnnotation(response=response, during=during)

    if keyword == "avoidance":
        mode = params.get("mode", "cancel")
        if mode not in ("cancel", "postpone"):
            result.diagnostics.append(
                f"@avoidance: 'mode' must be one of cancel/postpone (got {mode!r})"
            )
            return None
        return AvoidanceAnnotation(response=response, mode=mode)

    return None
