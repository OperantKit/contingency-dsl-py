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
from contingency_dsl.extensions import (
    CyclicDependencyError,
    ExtensionModule,
    ExtensionRegistry,
)


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

    def test_cyclic_dependency_two_extensions(self):
        """A→B→A cycle is detected."""

        class _ExtA:
            name: ClassVar[str] = "ext-a"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_a"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-b"})

        class _ExtB:
            name: ClassVar[str] = "ext-b"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_b"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-a"})

        with pytest.raises(CyclicDependencyError, match="cyclic dependency"):
            ExtensionRegistry.build(_ExtA(), _ExtB())

    def test_cyclic_dependency_three_extensions(self):
        """A→B→C→A cycle is detected."""

        class _ExtA:
            name: ClassVar[str] = "ext-a"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_a"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-b"})

        class _ExtB:
            name: ClassVar[str] = "ext-b"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_b"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-c"})

        class _ExtC:
            name: ClassVar[str] = "ext-c"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_c"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-a"})

        with pytest.raises(CyclicDependencyError, match="cyclic dependency"):
            ExtensionRegistry.build(_ExtA(), _ExtB(), _ExtC())

    def test_self_dependency_is_cyclic(self):
        """An extension requiring itself is a trivial cycle."""

        class _SelfRef:
            name: ClassVar[str] = "self-ref"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_self"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"self-ref"})

        with pytest.raises(CyclicDependencyError):
            ExtensionRegistry.build(_SelfRef())

    def test_deep_acyclic_chain_allowed(self):
        """A→B→C→D (no cycle) should succeed regardless of depth."""

        def _make_ext(name: str, req: str | None, kw: str):
            class _Ext:
                pass

            _Ext.name = name  # type: ignore[attr-defined]
            _Ext.version = "0.1.0"  # type: ignore[attr-defined]
            _Ext.annotation_keywords = property(lambda self: frozenset({kw}))
            _Ext.annotation_types = property(lambda self: {})
            _Ext.validate = lambda self, ann: []
            _Ext.requires = property(
                lambda self, r=req: frozenset({r}) if r else frozenset()
            )
            return _Ext()

        d = _make_ext("ext-d", None, "kw_d")
        c = _make_ext("ext-c", "ext-d", "kw_c")
        b = _make_ext("ext-b", "ext-c", "kw_b")
        a = _make_ext("ext-a", "ext-b", "kw_a")

        reg = ExtensionRegistry.build(a, b, c, d)
        assert "kw_a" in reg.all_annotation_keywords
        assert "kw_d" in reg.all_annotation_keywords

    def test_cyclic_dependency_error_contains_cycle(self):
        """CyclicDependencyError.cycle contains the offending nodes."""

        class _ExtA:
            name: ClassVar[str] = "ext-a"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_a"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-b"})

        class _ExtB:
            name: ClassVar[str] = "ext-b"
            version: ClassVar[str] = "0.1.0"

            @property
            def annotation_keywords(self) -> frozenset[str]:
                return frozenset({"kw_b"})

            @property
            def annotation_types(self) -> Mapping[str, type]:
                return {}

            def validate(self, annotations: Sequence[Any]) -> list[str]:
                return []

            @property
            def requires(self) -> frozenset[str]:
                return frozenset({"ext-a"})

        with pytest.raises(CyclicDependencyError) as exc_info:
            ExtensionRegistry.build(_ExtA(), _ExtB())
        err = exc_info.value
        assert "ext-a" in err.cycle
        assert "ext-b" in err.cycle
        assert err.cycle[0] == err.cycle[-1]  # closed loop


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
        assert ann.keyword == "reinforcer"
        assert ann.positional == "food"
        assert ann.params is None

    def test_multiple_annotations(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("food") @sd("red_light")',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert len(sched.annotations) == 2
        assert sched.annotations[0].keyword == "reinforcer"
        assert sched.annotations[1].keyword == "sd"

    def test_annotation_with_keyword_args(self, stimulus_registry):
        prog = parse(
            'FR5 @reinforcer("tone", type="conditioned", alpha0=0.3)',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        ann = sched.annotations[0]
        assert ann.keyword == "reinforcer"
        assert ann.positional == "tone"
        assert ann.params["type"] == "conditioned"
        assert ann.params["alpha0"] == 0.3

    def test_annotation_no_args(self, stimulus_registry):
        prog = parse("FR5 @operandum", extensions=stimulus_registry)
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        ann = sched.annotations[0]
        assert ann.keyword == "operandum"
        assert ann.positional is None
        assert ann.params is None

    def test_annotation_after_lh(self, stimulus_registry):
        """LH is parsed first, then annotations wrap the result."""
        prog = parse(
            'FI30 LH10 @sd("light")',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, LimitedHold)
        assert sched.annotations[0].keyword == "sd"

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
        assert sched.components[0].annotations[0].positional == "red"
        assert sched.components[1].annotations[0].positional == "green"

    def test_annotation_on_second_order(self, stimulus_registry):
        prog = parse(
            'FR5(FI30) @brief("light", duration=2)',
            extensions=stimulus_registry,
        )
        sched = prog.schedule
        assert isinstance(sched, AnnotatedSchedule)
        assert isinstance(sched.expr, SecondOrder)
        ann = sched.annotations[0]
        assert ann.keyword == "brief"
        assert ann.positional == "light"
        assert ann.params["duration"] == 2

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
        assert sched.annotations[0].keyword == "reinforcer"
        assert sched.annotations[1].keyword == "subject"

    def test_annotation_with_numeric_positional(self, stimulus_registry):
        prog = parse(
            "FR5(FI30) @brief(2)",
            extensions=stimulus_registry,
        )
        ann = prog.schedule.annotations[0]
        assert ann.positional == 2

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
        # Schedule-level annotations on a leaf (Atomic / Compound / ...) are
        # flattened onto the leaf's `annotations` array per
        # schema/operant/ast.schema.json. Program-level hoisting is only
        # applied for stateful / trial-based leaves (see the stateful
        # conformance fixtures).
        assert sched["type"] == "Atomic"
        annotations = sched["annotations"]
        assert len(annotations) == 1
        assert annotations[0]["keyword"] == "reinforcer"
        assert annotations[0]["positional"] == "food"

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
