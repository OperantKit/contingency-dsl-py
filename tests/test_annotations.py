"""Tests for annotation parsing, serialization, and printing (§4.7).

Annotations are only parsed when an ExtensionRegistry is provided.
Without extensions, '@' in source text raises a LexError (closed by default).
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

import pytest

from contingency_dsl import (
    AnnotatedSchedule,
    Annotation,
    AnnotationArg,
    Atomic,
    Compound,
    LexError,
    LimitedHold,
    ParseError,
    Program,
    SecondOrder,
    Special,
    parse,
    format_expr,
    format_program,
    to_dict,
    from_dict,
)
from contingency_dsl.extensions import ExtensionModule, ExtensionRegistry


# --- Minimal test extension ---


class _StimulusExt:
    """Minimal stimulus-ext for testing."""

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


class _SocialExt:
    """Minimal social-ext for testing."""

    name: ClassVar[str] = "social-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"subject", "interlocking"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()


@pytest.fixture
def stimulus_registry() -> ExtensionRegistry:
    return ExtensionRegistry.build(_StimulusExt())


@pytest.fixture
def multi_registry() -> ExtensionRegistry:
    return ExtensionRegistry.build(_StimulusExt(), _SocialExt())


# === Extension Registry Tests ===


class TestExtensionRegistry:
    def test_build_single(self):
        reg = ExtensionRegistry.build(_StimulusExt())
        assert "reinforcer" in reg.all_annotation_keywords
        assert "sd" in reg.all_annotation_keywords
        assert "stimulus-ext" in reg

    def test_build_multiple(self):
        reg = ExtensionRegistry.build(_StimulusExt(), _SocialExt())
        assert "reinforcer" in reg.all_annotation_keywords
        assert "subject" in reg.all_annotation_keywords

    def test_duplicate_extension_name(self):
        with pytest.raises(ValueError, match="duplicate extension name"):
            ExtensionRegistry.build(_StimulusExt(), _StimulusExt())

    def test_keyword_disjointness_violation(self):
        class _ConflictExt:
            name: ClassVar[str] = "conflict-ext"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"reinforcer"})  # conflicts with stimulus-ext

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset()

        with pytest.raises(ValueError, match="annotation keyword '@reinforcer' claimed by both"):
            ExtensionRegistry.build(_StimulusExt(), _ConflictExt())

    def test_missing_dependency(self):
        class _DependentExt:
            name: ClassVar[str] = "dependent-ext"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"dependent"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"stimulus-ext"})

        with pytest.raises(ValueError, match="requires"):
            ExtensionRegistry.build(_DependentExt())

    def test_satisfied_dependency(self):
        class _DependentExt:
            name: ClassVar[str] = "dependent-ext"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"dependent"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"stimulus-ext"})

        reg = ExtensionRegistry.build(_StimulusExt(), _DependentExt())
        assert "dependent" in reg.all_annotation_keywords


# === Closed by Default (no extensions) ===


class TestClosedByDefault:
    def test_at_sign_without_extensions_is_parse_error(self):
        """@ is lexed as AT token but rejected by parser without extensions."""
        with pytest.raises(ParseError, match="unexpected token.*AT"):
            parse('FR5 @reinforcer("food")')

    def test_plain_schedule_without_extensions(self):
        """Existing schedules continue to work without extensions."""
        prog = parse("FR5")
        assert isinstance(prog.schedule, Atomic)


# === Annotation Parsing ===


class TestAnnotationParsing:
    def test_single_annotation_with_string_arg(self, stimulus_registry):
        prog = parse('FR5 @reinforcer("food")', extensions=stimulus_registry)
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, Atomic)
        assert len(sched.annotations) == 1
        ann = sched.annotations[0]
        assert ann.name == "reinforcer"
        assert len(ann.args) == 1
        assert ann.args[0].value == "food"
        assert ann.args[0].key is None

    def test_multiple_annotations(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("food") @sd("red_light")',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert len(sched.annotations) == 2
        assert sched.annotations[0].name == "reinforcer"
        assert sched.annotations[1].name == "sd"

    def test_annotation_with_keyword_args(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("tone", type="conditioned", alpha0=0.3)',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        ann = sched.annotations[0]
        assert ann.name == "reinforcer"
        assert len(ann.args) == 3
        assert ann.args[0] == AnnotationArg(value="tone")
        assert ann.args[1] == AnnotationArg(value="conditioned", key="type")
        assert ann.args[2] == AnnotationArg(value=0.3, key="alpha0")

    def test_annotation_no_args(self, stimulus_registry):
        prog = parse("FR5 @operandum", extensions=stimulus_registry)
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        ann = sched.annotations[0]
        assert ann.name == "operandum"
        assert ann.args == ()

    def test_annotation_after_lh(self, stimulus_registry):
        """LH is parsed first, then annotations wrap the result."""
        prog = parse(
            'FI30 LH10 @sd("light")',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, LimitedHold)
        assert sched.annotations[0].name == "sd"

    def test_annotation_on_special(self, stimulus_registry):
        prog = parse('EXT @reinforcer("none")', extensions=stimulus_registry)
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, Special)

    def test_annotation_inside_compound(self, stimulus_registry):
        prog = parse(
            'Mult(FR5 @sd("red"), VI30s @sd("green"))',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, Compound)
        assert isinstance(sched.components[0], AnnotatedSchedule)
        assert isinstance(sched.components[1], AnnotatedSchedule)
        assert sched.components[0].annotations[0].args[0].value == "red"
        assert sched.components[1].annotations[0].args[0].value == "green"

    def test_annotation_on_second_order(self, stimulus_registry):
        prog = parse(
            'FR5(FI30) @brief("light", duration=2)',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, SecondOrder)
        ann = sched.annotations[0]
        assert ann.name == "brief"
        assert ann.args[0].value == "light"
        assert ann.args[1] == AnnotationArg(value=2.0, key="duration")

    def test_unknown_annotation_keyword(self, stimulus_registry):
        with pytest.raises(ParseError, match="unknown annotation '@unknown'"):
            parse('FR5 @unknown("foo")', extensions=stimulus_registry)

    def test_multi_extension_annotations(self, multi_registry):
        prog = parse(
            'FR5 @reinforcer("food") @subject("A")',
            extensions=multi_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert len(sched.annotations) == 2
        assert sched.annotations[0].name == "reinforcer"
        assert sched.annotations[1].name == "subject"

    def test_annotation_with_numeric_positional(self, stimulus_registry):
        prog = parse(
            "FR5(FI30) @brief(2)",
            extensions=stimulus_registry,
        )
        ann = prog.schedule.annotations[0]
        assert ann.args[0].value == 2.0

    def test_annotation_with_let_binding(self, stimulus_registry):
        prog = parse(
            'let baseline = VI60s\nbaseline @reinforcer("food")',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)


# === Printer Roundtrip ===


class TestAnnotationPrinter:
    def test_format_annotated(self, stimulus_registry):
        prog = parse('FR5 @reinforcer("food")', extensions=stimulus_registry)
        text = format_program(prog)
        assert text == 'FR5 @reinforcer("food")'

    def test_format_multiple_annotations(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("food") @sd("light")',
            extensions=stimulus_registry,
        )
        text = format_program(prog)
        assert text == 'FR5 @reinforcer("food") @sd("light")'

    def test_format_annotation_with_kwargs(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("tone", type="conditioned")',
            extensions=stimulus_registry,
        )
        text = format_program(prog)
        assert text == 'FR5 @reinforcer("tone", type="conditioned")'

    def test_format_no_args(self, stimulus_registry):
        prog = parse("FR5 @operandum", extensions=stimulus_registry)
        text = format_program(prog)
        assert text == "FR5 @operandum"

    def test_format_compound_with_annotations(self, stimulus_registry):
        prog = parse(
            'Mult(FR5 @sd("red"), VI30s @sd("green"))',
            extensions=stimulus_registry,
        )
        text = format_program(prog)
        assert text == 'Mult(FR5 @sd("red"), VI30s @sd("green"))'

    def test_format_lh_with_annotation(self, stimulus_registry):
        prog = parse(
            'FI30 LH10 @sd("light")',
            extensions=stimulus_registry,
        )
        text = format_program(prog)
        assert text == 'FI30 LH10 @sd("light")'


# === Serializer Roundtrip ===


class TestAnnotationSerializer:
    def test_to_dict_annotated(self, stimulus_registry):
        prog = parse('FR5 @reinforcer("food")', extensions=stimulus_registry)
        d = to_dict(prog)
        sched = d["schedule"]
        assert sched["type"] == "AnnotatedSchedule"
        assert sched["expr"]["type"] == "Atomic"
        assert len(sched["annotations"]) == 1
        assert sched["annotations"][0]["name"] == "reinforcer"
        assert sched["annotations"][0]["args"][0]["value"] == "food"

    def test_dict_roundtrip(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("food", type="unconditioned")',
            extensions=stimulus_registry,
        )
        d = to_dict(prog)
        restored = from_dict(d)
        assert to_dict(restored) == d

    def test_dict_roundtrip_compound(self, stimulus_registry):
        prog = parse(
            'Mult(FR5 @sd("red"), VI30s @sd("green"))',
            extensions=stimulus_registry,
        )
        d = to_dict(prog)
        restored = from_dict(d)
        assert to_dict(restored) == d
