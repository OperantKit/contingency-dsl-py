"""Integration tests for stimulus-ext with contingency-dsl-py.

Tests the full pipeline: DSL text -> parse with extensions -> extract declarations.
Uses a minimal inline StimulusExtension to avoid cross-package dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar, Mapping, Sequence

import pytest

from contingency_dsl import (
    AnnotatedSchedule,
    Annotation,
    AnnotationArg,
    Atomic,
    Compound,
    LimitedHold,
    SecondOrder,
    parse,
    format_program,
    to_dict,
    from_dict,
)
from contingency_dsl.extensions import ExtensionModule, ExtensionRegistry


# --- Inline stimulus-ext (mirrors contingency_annotator.stimulus_ext) ---


class _StimulusExt:
    name: ClassVar[str] = "stimulus-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"reinforcer", "sd", "operandum", "brief"})

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
    return ExtensionRegistry.build(_StimulusExt())


# === Three-term contingency: SD -> R -> SR ===


class TestThreeTermContingency:
    """Verify that the full three-term contingency can be expressed in DSL."""

    def test_basic_three_term(self, reg):
        """SD -> R -> SR expressed declaratively."""
        prog = parse(
            'FR5 @sd("red_light") @operandum("left_lever") @reinforcer("food_pellet")',
            extensions=reg,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, Atomic)
        names = [a.keyword for a in sched.annotations]
        assert names == ["sd", "operandum", "reinforcer"]

    def test_mult_with_discriminated_components(self, reg):
        """Multiple schedule with different SDs per component."""
        prog = parse(
            'Mult(FR5 @sd("red") @reinforcer("food"), VI30s @sd("green") @reinforcer("water"))',
            extensions=reg,
        )
        sched = prog.schedule
        assert isinstance(sched, Compound)
        assert len(sched.components) == 2

        comp1 = sched.components[0]
        assert isinstance(comp1, AnnotatedSchedule)
        assert comp1.annotations[0].keyword == "sd"
        assert comp1.annotations[0].positional == "red"

        comp2 = sched.components[1]
        assert isinstance(comp2, AnnotatedSchedule)
        assert comp2.annotations[0].keyword == "sd"
        assert comp2.annotations[0].positional == "green"

    def test_conc_with_operandum_binding(self, reg):
        """Concurrent schedule with operandum-to-stimulus mapping."""
        prog = parse(
            'Conc(VI30s @operandum("left") @reinforcer("food"), VI60s @operandum("right") @reinforcer("food"))',
            extensions=reg,
        )
        sched = prog.schedule
        assert isinstance(sched, Compound)
        left = sched.components[0]
        right = sched.components[1]
        assert isinstance(left, AnnotatedSchedule)
        assert isinstance(right, AnnotatedSchedule)
        assert left.annotations[0].positional == "left"
        assert right.annotations[0].positional == "right"

    def test_second_order_with_brief(self, reg):
        """Second-order schedule with brief stimulus (Issue #17)."""
        prog = parse(
            'FR5(FI30s) @brief("light", duration=2) @reinforcer("food_pellet")',
            extensions=reg,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, SecondOrder)
        brief = sched.annotations[0]
        assert brief.keyword == "brief"
        assert brief.positional == "light"
        assert brief.params["duration"] == 2

    def test_conditioned_reinforcer(self, reg):
        """Conditioned reinforcer with backup specification."""
        prog = parse(
            'FR5 @reinforcer("tone", type="conditioned", backup="food")',
            extensions=reg,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        ann = sched.annotations[0]
        assert ann.positional == "tone"
        assert ann.params["type"] == "conditioned"
        assert ann.params["backup"] == "food"


# === Roundtrip Tests ===


class TestAnnotationRoundtrip:
    """Parse -> Print -> Re-parse roundtrips for annotated expressions."""

    ANNOTATED_EXAMPLES = [
        'FR5 @reinforcer("food")',
        'FR5 @sd("light") @reinforcer("food")',
        'FR5 @reinforcer("tone", type="conditioned")',
        'FR5 @operandum("lever")',
        'FR5(FI30s) @brief("light", duration=2)',
        # LH postfix round-trips are covered by conformance; the in-memory
        # roundtrip here would need printer support for the flat-form leaf.
        'Mult(FR5 @sd("red"), VI30s @sd("green"))',
        'Conc(VI30s @operandum("left"), VI60s @operandum("right"))',
        'FR5 @operandum',
    ]

    @pytest.mark.parametrize("source", ANNOTATED_EXAMPLES)
    def test_print_roundtrip(self, reg, source):
        """parse(format(parse(x))) == parse(x) for annotated expressions."""
        prog1 = parse(source, extensions=reg)
        text1 = format_program(prog1)
        prog2 = parse(text1, extensions=reg)
        text2 = format_program(prog2)
        assert text1 == text2

    @pytest.mark.parametrize("source", ANNOTATED_EXAMPLES)
    def test_serializer_roundtrip(self, reg, source):
        """from_dict(to_dict(parse(x))) == parse(x) for annotated expressions."""
        prog = parse(source, extensions=reg)
        d = to_dict(prog)
        restored = from_dict(d)
        assert to_dict(restored) == d


# === Semantic Analysis with Annotations ===


class TestAnnotationAnalyzer:
    """Verify that analyzer handles annotated schedules correctly."""

    def test_let_binding_with_annotation(self, reg):
        """Let-bound identifier referenced in annotated schedule."""
        from contingency_dsl import analyze

        prog = parse(
            'let baseline = VI60s\nbaseline @reinforcer("food")',
            extensions=reg,
        )
        result = analyze(prog)
        sched = result.program.schedule
        assert isinstance(sched, AnnotatedSchedule)
        # After expansion, the inner expr should be the Atomic VI60s
        assert isinstance(sched.expr, Atomic)

    def test_repeat_expansion_with_annotation(self, reg):
        """Repeat inside annotated schedule expands correctly."""
        from contingency_dsl import analyze

        prog = parse(
            'Repeat(3, FR5) @reinforcer("food")',
            extensions=reg,
        )
        result = analyze(prog)
        sched = result.program.schedule
        assert isinstance(sched, AnnotatedSchedule)
        # After Repeat expansion, inner should be Tand(FR5, FR5, FR5)
        assert isinstance(sched.expr, Compound)
        assert len(sched.expr.components) == 3

    def test_lh_default_with_annotation(self, reg):
        """Program-level LH default applies inside annotated schedule."""
        from contingency_dsl import analyze

        prog = parse(
            'LH = 10\nFR5 @reinforcer("food")',
            extensions=reg,
        )
        result = analyze(prog)
        sched = result.program.schedule
        # The annotation wraps a LimitedHold(FR5)
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, LimitedHold)
