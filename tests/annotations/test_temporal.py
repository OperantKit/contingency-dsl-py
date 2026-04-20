"""Tests for temporal-ext: types, validation, and extraction."""
from __future__ import annotations

import pytest

from contingency_dsl.ast import Annotation, Program, Special
from contingency_dsl.extensions import ExtensionRegistry

from contingency_dsl.annotations.temporal import (
    AlgorithmAnnotation,
    ClockAnnotation,
    TemporalDeclarationSet,
    TemporalExtension,
    WarmupAnnotation,
)


# ---------------------------------------------------------------------------
# Protocol conformance / surface tests
# ---------------------------------------------------------------------------


class TestTemporalExtensionProtocol:
    def test_name_and_version(self) -> None:
        ext = TemporalExtension()
        assert ext.name == "temporal-ext"
        assert ext.version == "0.1.0"

    def test_annotation_keywords(self) -> None:
        ext = TemporalExtension()
        assert ext.annotation_keywords == frozenset({"clock", "warmup", "algorithm"})

    def test_annotation_types_mapping(self) -> None:
        ext = TemporalExtension()
        types = ext.annotation_types
        assert types["clock"] is ClockAnnotation
        assert types["warmup"] is WarmupAnnotation
        assert types["algorithm"] is AlgorithmAnnotation

    def test_requires_empty(self) -> None:
        ext = TemporalExtension()
        assert ext.requires == frozenset()

    def test_no_keyword_overlap_with_stimulus(self) -> None:
        from contingency_dsl.annotations.stimulus import StimulusExtension

        t = TemporalExtension()
        s = StimulusExtension()
        assert t.annotation_keywords & s.annotation_keywords == frozenset()

    def test_registry_build_with_other_extensions(self) -> None:
        from contingency_dsl.annotations.stimulus import StimulusExtension

        reg = ExtensionRegistry.build(StimulusExtension(), TemporalExtension())
        assert "clock" in reg.all_annotation_keywords
        assert "warmup" in reg.all_annotation_keywords
        assert "algorithm" in reg.all_annotation_keywords
        assert "reinforcer" in reg.all_annotation_keywords


# ---------------------------------------------------------------------------
# Annotation dataclass instantiation
# ---------------------------------------------------------------------------


class TestClockAnnotation:
    def test_construct_seconds(self) -> None:
        ann = ClockAnnotation(unit="s")
        assert ann.unit == "s"

    def test_construct_milliseconds(self) -> None:
        ann = ClockAnnotation(unit="ms")
        assert ann.unit == "ms"

    def test_construct_minutes(self) -> None:
        ann = ClockAnnotation(unit="min")
        assert ann.unit == "min"

    def test_frozen(self) -> None:
        ann = ClockAnnotation(unit="s")
        with pytest.raises(Exception):
            ann.unit = "ms"  # type: ignore[misc]


class TestWarmupAnnotation:
    def test_construct(self) -> None:
        ann = WarmupAnnotation(duration=300.0)
        assert ann.duration == 300.0
        assert ann.time_unit is None

    def test_construct_with_unit(self) -> None:
        ann = WarmupAnnotation(duration=5.0, time_unit="min")
        assert ann.duration == 5.0
        assert ann.time_unit == "min"

    def test_frozen(self) -> None:
        ann = WarmupAnnotation(duration=300.0)
        with pytest.raises(Exception):
            ann.duration = 0.0  # type: ignore[misc]


class TestAlgorithmAnnotation:
    def test_construct_minimal(self) -> None:
        ann = AlgorithmAnnotation(name="fleshler-hoffman")
        assert ann.name == "fleshler-hoffman"
        assert ann.n is None
        assert ann.seed is None

    def test_construct_with_n_and_seed(self) -> None:
        ann = AlgorithmAnnotation(name="fleshler-hoffman", n=12, seed=42)
        assert ann.name == "fleshler-hoffman"
        assert ann.n == 12
        assert ann.seed == 42

    def test_construct_arithmetic(self) -> None:
        ann = AlgorithmAnnotation(name="arithmetic", n=20)
        assert ann.name == "arithmetic"
        assert ann.n == 20

    def test_frozen(self) -> None:
        ann = AlgorithmAnnotation(name="fleshler-hoffman")
        with pytest.raises(Exception):
            ann.name = "arithmetic"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


class TestClockValidation:
    def test_valid_seconds(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([Annotation(keyword="clock", params={"unit": "s"})])
        assert diags == []

    def test_valid_ms(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([Annotation(keyword="clock", params={"unit": "ms"})])
        assert diags == []

    def test_valid_min(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([Annotation(keyword="clock", params={"unit": "min"})])
        assert diags == []

    def test_invalid_unit(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([Annotation(keyword="clock", params={"unit": "hour"})])
        assert len(diags) == 1
        assert "CLOCK_INVALID_UNIT" in diags[0]

    def test_missing_unit(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([Annotation(keyword="clock", params={})])
        assert len(diags) == 1
        assert "CLOCK_MISSING_UNIT" in diags[0]

    def test_at_most_one_clock(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="clock", params={"unit": "s"}),
            Annotation(keyword="clock", params={"unit": "ms"}),
        ])
        assert any("CLOCK_MULTIPLE" in d for d in diags)


class TestWarmupValidation:
    def test_valid_positive(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="warmup", params={"duration": 300}),
        ])
        assert diags == []

    def test_valid_zero(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="warmup", params={"duration": 0}),
        ])
        assert diags == []

    def test_invalid_negative(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="warmup", params={"duration": -1}),
        ])
        assert any("WARMUP_NEGATIVE_DURATION" in d for d in diags)

    def test_missing_duration(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="warmup", params={}),
        ])
        assert any("WARMUP_MISSING_DURATION" in d for d in diags)


class TestAlgorithmValidation:
    def test_valid_fleshler_hoffman(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="algorithm", positional="fleshler-hoffman"),
        ])
        assert diags == []

    def test_valid_arithmetic(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="algorithm", positional="arithmetic"),
        ])
        assert diags == []

    def test_valid_with_n_and_seed(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="algorithm",
                positional="fleshler-hoffman",
                params={"n": 12, "seed": 42},
            ),
        ])
        assert diags == []

    def test_unknown_algorithm(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="algorithm", positional="bogus-generator"),
        ])
        assert any("ALGORITHM_UNKNOWN" in d for d in diags)

    def test_missing_name(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([Annotation(keyword="algorithm")])
        assert any("ALGORITHM_MISSING_NAME" in d for d in diags)

    def test_invalid_n_zero(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="algorithm",
                positional="fleshler-hoffman",
                params={"n": 0},
            ),
        ])
        assert any("ALGORITHM_INVALID_N" in d for d in diags)

    def test_invalid_n_negative(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="algorithm",
                positional="fleshler-hoffman",
                params={"n": -3},
            ),
        ])
        assert any("ALGORITHM_INVALID_N" in d for d in diags)


class TestValidateMixed:
    def test_validate_ignores_non_annotation_objects(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([object(), 42, "not_an_annotation"])
        assert diags == []

    def test_validate_ignores_unrelated_keywords(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="reinforcer", positional="food"),
        ])
        assert diags == []


# ---------------------------------------------------------------------------
# extract_declarations
# ---------------------------------------------------------------------------


class TestExtractDeclarations:
    def test_empty_program(self) -> None:
        program = Program(schedule=Special("EXT"))
        decls = TemporalExtension.extract_declarations(program)
        assert decls.clock is None
        assert decls.warmup is None
        assert decls.algorithms == {}

    def test_full_preamble(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="clock", params={"unit": "s"}),
                Annotation(keyword="warmup", params={"duration": 300}),
                Annotation(
                    keyword="algorithm",
                    positional="fleshler-hoffman",
                    params={"n": 12, "seed": 42},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)

        assert decls.clock is not None
        assert decls.clock.unit == "s"

        assert decls.warmup is not None
        assert decls.warmup.duration == 300.0

        assert "fleshler-hoffman" in decls.algorithms
        algo = decls.algorithms["fleshler-hoffman"]
        assert algo.name == "fleshler-hoffman"
        assert algo.n == 12
        assert algo.seed == 42

    def test_clock_only(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="clock", params={"unit": "ms"}),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.clock is not None
        assert decls.clock.unit == "ms"
        assert decls.warmup is None
        assert decls.algorithms == {}

    def test_warmup_with_time_unit_dict(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="warmup",
                    params={"duration": {"value": 5, "time_unit": "min"}},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.warmup is not None
        assert decls.warmup.duration == 5.0
        assert decls.warmup.time_unit == "min"

    def test_multiple_algorithms(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="algorithm", positional="fleshler-hoffman"),
                Annotation(
                    keyword="algorithm",
                    positional="arithmetic",
                    params={"n": 20},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert "fleshler-hoffman" in decls.algorithms
        assert "arithmetic" in decls.algorithms
        assert decls.algorithms["arithmetic"].n == 20

    def test_unrelated_annotations_ignored(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="reinforcer", positional="food"),
                Annotation(keyword="clock", params={"unit": "s"}),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.clock is not None
        assert decls.clock.unit == "s"


# ---------------------------------------------------------------------------
# TemporalDeclarationSet immutability
# ---------------------------------------------------------------------------


class TestTemporalDeclarationSetImmutability:
    def test_frozen(self) -> None:
        decls = TemporalDeclarationSet()
        with pytest.raises(Exception):
            decls.clock = None  # type: ignore[misc]

    def test_default_factory_independence(self) -> None:
        a = TemporalDeclarationSet()
        b = TemporalDeclarationSet()
        # Different instances must not share the algorithms dict
        assert a.algorithms is not b.algorithms or a.algorithms == {}


# ---------------------------------------------------------------------------
# Edge-case coverage for parsers and coercion helpers
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_warmup_non_numeric_duration_diagnostic(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="warmup", params={"duration": "five"}),
        ])
        assert any("WARMUP_MISSING_DURATION" in d for d in diags)

    def test_algorithm_n_bool_is_invalid(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="algorithm",
                positional="fleshler-hoffman",
                params={"n": True},
            ),
        ])
        assert any("ALGORITHM_INVALID_N" in d for d in diags)

    def test_algorithm_n_non_integer_float(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="algorithm",
                positional="fleshler-hoffman",
                params={"n": 12.5},
            ),
        ])
        assert any("ALGORITHM_INVALID_N" in d for d in diags)

    def test_algorithm_n_non_numeric(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="algorithm",
                positional="fleshler-hoffman",
                params={"n": "twelve"},
            ),
        ])
        assert any("ALGORITHM_INVALID_N" in d for d in diags)

    def test_extract_clock_with_non_string_unit_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="clock", params={"unit": 42}),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.clock is None

    def test_extract_warmup_with_non_numeric_duration_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="warmup", params={"duration": "five"}),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.warmup is None

    def test_extract_algorithm_with_missing_name_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="algorithm"),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.algorithms == {}

    def test_extract_warmup_dict_without_value_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="warmup",
                    params={"duration": {"time_unit": "min"}},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.warmup is None

    def test_validate_warmup_duration_dict(self) -> None:
        """@warmup(duration=5min) — dict-shaped value should validate as numeric."""
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="warmup",
                params={"duration": {"value": 5, "time_unit": "min"}},
            ),
        ])
        assert diags == []

    def test_validate_warmup_duration_dict_negative(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(
                keyword="warmup",
                params={"duration": {"value": -1, "time_unit": "s"}},
            ),
        ])
        assert any("WARMUP_NEGATIVE_DURATION" in d for d in diags)

    def test_validate_warmup_bool_duration_rejected(self) -> None:
        ext = TemporalExtension()
        diags = ext.validate([
            Annotation(keyword="warmup", params={"duration": True}),
        ])
        assert any("WARMUP_MISSING_DURATION" in d for d in diags)

    def test_extract_algorithm_seed_int(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="algorithm",
                    positional="fleshler-hoffman",
                    params={"seed": 99},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = TemporalExtension.extract_declarations(program)
        assert decls.algorithms["fleshler-hoffman"].seed == 99
        assert decls.algorithms["fleshler-hoffman"].n is None
