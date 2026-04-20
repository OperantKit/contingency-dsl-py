"""Tests for composed_ext.analyzer — ExecutionPlan extraction and validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Sequence

import pytest

from contingency_dsl import parse
from contingency_dsl.extensions import ExtensionRegistry

from contingency_dsl.annotations.composed import (
    AnalysisResult,
    AvoidanceAnnotation,
    ComposedAnalysisError,
    ComposedExtension,
    ExecutionPlan,
    OmissionAnnotation,
    analyze,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RespondentStub:
    name: ClassVar[str] = "respondent-stub"
    version: ClassVar[str] = "test"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"cs", "us", "iti", "cs_interval"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()


@pytest.fixture
def reg() -> ExtensionRegistry:
    return ExtensionRegistry.build(ComposedExtension(), _RespondentStub())


# ---------------------------------------------------------------------------
# Happy-path: Phase sequence with @omission
# ---------------------------------------------------------------------------


def test_phase_sequence_with_omission_produces_one_plan(reg) -> None:
    src = (
        "@cs(label=\"key_light\", duration=6s)\n"
        "@us(label=\"grain\")\n\n"
        "phase omission_training:\n"
        "  sessions = 20\n"
        "  Pair.ForwardDelay(key_light, grain, isi=6s, cs_duration=6s) "
        "@omission(response=\"key_peck\", during=\"cs\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast)

    assert result.is_valid
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert isinstance(plan.rule, OmissionAnnotation)
    assert plan.rule.response == "key_peck"
    assert plan.rule.during == "cs"
    assert plan.pair_type == "PairForwardDelay"
    assert plan.cs == "key_light"
    assert plan.us == "grain"
    assert plan.phase_label == "omission_training"


def test_phase_sequence_with_avoidance_produces_one_plan(reg) -> None:
    src = (
        "@cs(label=\"tone\", duration=5s)\n"
        "@us(label=\"shock\")\n\n"
        "phase warmup:\n"
        "  sessions = 2\n"
        "  VI30s\n\n"
        "phase avoidance_training:\n"
        "  sessions = 20\n"
        "  Pair.ForwardDelay(tone, shock, isi=5s, cs_duration=5s) "
        "@avoidance(response=\"lever_press\", mode=\"cancel\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast)

    assert result.is_valid
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert isinstance(plan.rule, AvoidanceAnnotation)
    assert plan.rule.mode == "cancel"
    assert plan.phase_label == "avoidance_training"


def test_program_level_omission_has_no_phase_label(reg) -> None:
    src = (
        "Pair.ForwardDelay(tone, shock, isi=10s, cs_duration=15s) "
        "@omission(response=\"key_peck\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast)
    assert len(result.plans) == 1
    assert result.plans[0].phase_label is None


def test_pair_backward_is_us_bearing(reg) -> None:
    src = (
        "Pair.Backward(shock, tone, isi=10s) "
        "@avoidance(response=\"lever_press\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast)
    assert result.is_valid
    assert result.plans[0].pair_type == "PairBackward"
    assert result.plans[0].us == "shock"
    assert result.plans[0].cs == "tone"


def test_no_composed_annotations_produces_empty_plan(reg) -> None:
    src = "Pair.ForwardDelay(tone, shock, isi=10s, cs_duration=15s)"
    ast = parse(src, extensions=reg)
    result = analyze(ast)
    assert result.is_valid
    assert result.plans == []


def test_multiple_phases_yield_multiple_plans(reg) -> None:
    src = (
        "@cs(label=\"tone\", duration=5s)\n"
        "@us(label=\"shock\")\n\n"
        "phase omission_train:\n"
        "  sessions = 10\n"
        "  Pair.ForwardDelay(tone, shock, isi=5s, cs_duration=5s) "
        "@omission(response=\"peck\")\n\n"
        "phase avoidance_train:\n"
        "  sessions = 10\n"
        "  Pair.ForwardDelay(tone, shock, isi=5s, cs_duration=5s) "
        "@avoidance(response=\"press\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast)

    assert result.is_valid
    assert len(result.plans) == 2
    labels = {p.phase_label for p in result.plans}
    assert labels == {"omission_train", "avoidance_train"}


# ---------------------------------------------------------------------------
# Structural violations
# ---------------------------------------------------------------------------


def test_omission_on_extinction_is_diagnosed(reg) -> None:
    src = (
        "Extinction(tone) @omission(response=\"key_peck\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast)
    assert not result.is_valid
    assert any("Extinction" in d for d in result.diagnostics)
    assert any("US-bearing" in d for d in result.diagnostics)
    assert result.plans == []


def test_avoidance_on_cs_only_is_diagnosed(reg) -> None:
    src = "CSOnly(tone, 10) @avoidance(response=\"lever_press\")"
    ast = parse(src, extensions=reg)
    result = analyze(ast)
    assert not result.is_valid
    assert any("CSOnly" in d for d in result.diagnostics)


def test_missing_response_parameter_is_diagnosed(reg) -> None:
    # A malformed annotation — response absent — constructed by parsing
    # without a response kwarg. The parser allows this because annotation
    # validation is semantic; the analyzer catches it.
    from contingency_dsl.ast import Annotation, AnnotatedSchedule
    from contingency_dsl.respondent import PairForwardDelay, Duration

    bad = AnnotatedSchedule(
        expr=PairForwardDelay(
            cs="tone",
            us="shock",
            isi=Duration(value=10, unit="s"),
            cs_duration=Duration(value=15, unit="s"),
        ),
        annotations=(Annotation(keyword="omission", params={"during": "cs"}),),
    )
    from contingency_dsl.ast import Program

    fake_program = Program(schedule=bad)
    result = analyze(fake_program)
    assert not result.is_valid
    assert any("response" in d for d in result.diagnostics)


def test_invalid_during_is_diagnosed(reg) -> None:
    from contingency_dsl.ast import Annotation, AnnotatedSchedule, Program
    from contingency_dsl.respondent import PairForwardDelay, Duration

    bad = AnnotatedSchedule(
        expr=PairForwardDelay(
            cs="tone",
            us="shock",
            isi=Duration(value=10, unit="s"),
            cs_duration=Duration(value=15, unit="s"),
        ),
        annotations=(
            Annotation(
                keyword="omission",
                params={"response": "peck", "during": "nowhere"},
            ),
        ),
    )
    result = analyze(Program(schedule=bad))
    assert not result.is_valid
    assert any("during" in d for d in result.diagnostics)


def test_invalid_avoidance_mode_is_diagnosed(reg) -> None:
    from contingency_dsl.ast import Annotation, AnnotatedSchedule, Program
    from contingency_dsl.respondent import PairForwardDelay, Duration

    bad = AnnotatedSchedule(
        expr=PairForwardDelay(
            cs="tone",
            us="shock",
            isi=Duration(value=10, unit="s"),
            cs_duration=Duration(value=15, unit="s"),
        ),
        annotations=(
            Annotation(
                keyword="avoidance",
                params={"response": "press", "mode": "bogus"},
            ),
        ),
    )
    result = analyze(Program(schedule=bad))
    assert not result.is_valid
    assert any("mode" in d for d in result.diagnostics)


def test_both_omission_and_avoidance_is_diagnosed(reg) -> None:
    from contingency_dsl.ast import Annotation, AnnotatedSchedule, Program
    from contingency_dsl.respondent import PairForwardDelay, Duration

    bad = AnnotatedSchedule(
        expr=PairForwardDelay(
            cs="tone",
            us="shock",
            isi=Duration(value=10, unit="s"),
            cs_duration=Duration(value=15, unit="s"),
        ),
        annotations=(
            Annotation(keyword="omission", params={"response": "peck"}),
            Annotation(keyword="avoidance", params={"response": "press"}),
        ),
    )
    result = analyze(Program(schedule=bad))
    assert not result.is_valid
    assert any("conflicting" in d for d in result.diagnostics)


# ---------------------------------------------------------------------------
# strict mode
# ---------------------------------------------------------------------------


def test_strict_mode_raises_on_diagnostic(reg) -> None:
    src = "Extinction(tone) @omission(response=\"key_peck\")"
    ast = parse(src, extensions=reg)
    with pytest.raises(ComposedAnalysisError):
        analyze(ast, strict=True)


def test_strict_mode_silent_when_valid(reg) -> None:
    src = (
        "Pair.ForwardDelay(tone, shock, isi=10s, cs_duration=15s) "
        "@omission(response=\"peck\")"
    )
    ast = parse(src, extensions=reg)
    result = analyze(ast, strict=True)  # must not raise
    assert result.is_valid
    assert len(result.plans) == 1
