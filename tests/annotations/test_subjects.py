"""Tests for subjects-ext: types, validation, and extraction."""
from __future__ import annotations

import pytest

from contingency_dsl.ast import Annotation, Program, Special
from contingency_dsl.extensions import ExtensionRegistry

from contingency_dsl.annotations.subjects import (
    DeprivationAnnotation,
    HistoryAnnotation,
    NAnnotation,
    SpeciesAnnotation,
    StrainAnnotation,
    SubjectsDeclarationSet,
    SubjectsExtension,
)


# ---------------------------------------------------------------------------
# Protocol conformance / surface tests
# ---------------------------------------------------------------------------


class TestSubjectsExtensionProtocol:
    def test_name_and_version(self) -> None:
        ext = SubjectsExtension()
        assert ext.name == "subjects-ext"
        assert ext.version == "0.1.0"

    def test_annotation_keywords(self) -> None:
        ext = SubjectsExtension()
        assert ext.annotation_keywords == frozenset(
            {"species", "strain", "deprivation", "history", "n"}
        )

    def test_annotation_types_mapping(self) -> None:
        ext = SubjectsExtension()
        types = ext.annotation_types
        assert types["species"] is SpeciesAnnotation
        assert types["strain"] is StrainAnnotation
        assert types["deprivation"] is DeprivationAnnotation
        assert types["history"] is HistoryAnnotation
        assert types["n"] is NAnnotation

    def test_requires_empty(self) -> None:
        ext = SubjectsExtension()
        assert ext.requires == frozenset()

    def test_no_keyword_overlap_with_stimulus(self) -> None:
        from contingency_dsl.annotations.stimulus import StimulusExtension

        s = SubjectsExtension()
        st = StimulusExtension()
        assert s.annotation_keywords & st.annotation_keywords == frozenset()

    def test_no_keyword_overlap_with_temporal(self) -> None:
        from contingency_dsl.annotations.temporal import TemporalExtension

        s = SubjectsExtension()
        t = TemporalExtension()
        assert s.annotation_keywords & t.annotation_keywords == frozenset()

    def test_registry_build_with_other_extensions(self) -> None:
        from contingency_dsl.annotations.stimulus import StimulusExtension
        from contingency_dsl.annotations.temporal import TemporalExtension

        reg = ExtensionRegistry.build(
            StimulusExtension(), TemporalExtension(), SubjectsExtension()
        )
        assert "species" in reg.all_annotation_keywords
        assert "strain" in reg.all_annotation_keywords
        assert "deprivation" in reg.all_annotation_keywords
        assert "history" in reg.all_annotation_keywords
        assert "n" in reg.all_annotation_keywords
        assert "reinforcer" in reg.all_annotation_keywords
        assert "clock" in reg.all_annotation_keywords


# ---------------------------------------------------------------------------
# Annotation dataclass instantiation
# ---------------------------------------------------------------------------


class TestSpeciesAnnotation:
    def test_construct(self) -> None:
        ann = SpeciesAnnotation(species="rat")
        assert ann.species == "rat"

    def test_frozen(self) -> None:
        ann = SpeciesAnnotation(species="rat")
        with pytest.raises(Exception):
            ann.species = "pigeon"  # type: ignore[misc]


class TestStrainAnnotation:
    def test_construct(self) -> None:
        ann = StrainAnnotation(strain="Long-Evans")
        assert ann.strain == "Long-Evans"

    def test_frozen(self) -> None:
        ann = StrainAnnotation(strain="Long-Evans")
        with pytest.raises(Exception):
            ann.strain = "Sprague-Dawley"  # type: ignore[misc]


class TestDeprivationAnnotation:
    def test_construct(self) -> None:
        ann = DeprivationAnnotation(hours=23.0, target="food")
        assert ann.hours == 23.0
        assert ann.target == "food"

    def test_frozen(self) -> None:
        ann = DeprivationAnnotation(hours=23.0, target="food")
        with pytest.raises(Exception):
            ann.hours = 12.0  # type: ignore[misc]


class TestHistoryAnnotation:
    def test_construct(self) -> None:
        ann = HistoryAnnotation(history="naive")
        assert ann.history == "naive"

    def test_frozen(self) -> None:
        ann = HistoryAnnotation(history="naive")
        with pytest.raises(Exception):
            ann.history = "experienced"  # type: ignore[misc]


class TestNAnnotation:
    def test_construct(self) -> None:
        ann = NAnnotation(n=8)
        assert ann.n == 8

    def test_frozen(self) -> None:
        ann = NAnnotation(n=8)
        with pytest.raises(Exception):
            ann.n = 4  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


class TestSpeciesValidation:
    def test_valid_string(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="species", positional="rat")])
        assert diags == []

    def test_missing_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="species")])
        assert any("SPECIES_MISSING_NAME" in d for d in diags)

    def test_non_string_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="species", positional=42)])
        assert any("SPECIES_MISSING_NAME" in d for d in diags)

    def test_empty_string_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="species", positional="")])
        assert any("SPECIES_MISSING_NAME" in d for d in diags)


class TestStrainValidation:
    def test_valid_string(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [Annotation(keyword="strain", positional="Long-Evans")]
        )
        assert diags == []

    def test_missing_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="strain")])
        assert any("STRAIN_MISSING_NAME" in d for d in diags)

    def test_non_string_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="strain", positional=3.14)])
        assert any("STRAIN_MISSING_NAME" in d for d in diags)


class TestDeprivationValidation:
    def test_valid_food(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": 23, "target": "food"},
                )
            ]
        )
        assert diags == []

    def test_valid_water_zero_hours(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": 0, "target": "water"},
                )
            ]
        )
        assert diags == []

    def test_missing_hours(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [Annotation(keyword="deprivation", params={"target": "food"})]
        )
        assert any("DEPRIVATION_MISSING_HOURS" in d for d in diags)

    def test_missing_target(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [Annotation(keyword="deprivation", params={"hours": 23})]
        )
        assert any("DEPRIVATION_MISSING_TARGET" in d for d in diags)

    def test_negative_hours(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": -1, "target": "food"},
                )
            ]
        )
        assert any("DEPRIVATION_NEGATIVE_HOURS" in d for d in diags)

    def test_invalid_hours_type(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": "twenty-three", "target": "food"},
                )
            ]
        )
        assert any("DEPRIVATION_INVALID_HOURS" in d for d in diags)

    def test_invalid_hours_bool(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": True, "target": "food"},
                )
            ]
        )
        assert any("DEPRIVATION_INVALID_HOURS" in d for d in diags)

    def test_invalid_target_type(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": 23, "target": 42},
                )
            ]
        )
        assert any("DEPRIVATION_INVALID_TARGET" in d for d in diags)

    def test_empty_target(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": 23, "target": ""},
                )
            ]
        )
        assert any("DEPRIVATION_INVALID_TARGET" in d for d in diags)

    def test_unexpected_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    positional="food",
                    params={"hours": 23, "target": "food"},
                )
            ]
        )
        assert any("DEPRIVATION_UNEXPECTED_POSITIONAL" in d for d in diags)


class TestHistoryValidation:
    def test_valid_naive(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="history", positional="naive")])
        assert diags == []

    def test_valid_descriptive(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="history",
                    positional="experienced: 6 months lever-press training",
                )
            ]
        )
        assert diags == []

    def test_missing_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="history")])
        assert any("HISTORY_MISSING_DESCRIPTOR" in d for d in diags)

    def test_non_string_positional(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="history", positional=1)])
        assert any("HISTORY_MISSING_DESCRIPTOR" in d for d in diags)


class TestNValidation:
    def test_valid_positive_int(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional=8)])
        assert diags == []

    def test_valid_one(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional=1)])
        assert diags == []

    def test_invalid_zero(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional=0)])
        assert any("N_INVALID_VALUE" in d for d in diags)

    def test_invalid_negative(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional=-3)])
        assert any("N_INVALID_VALUE" in d for d in diags)

    def test_invalid_float(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional=8.5)])
        assert any("N_INVALID_VALUE" in d for d in diags)

    def test_invalid_string(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional="eight")])
        assert any("N_INVALID_VALUE" in d for d in diags)

    def test_invalid_bool(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n", positional=True)])
        assert any("N_INVALID_VALUE" in d for d in diags)

    def test_missing_value(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([Annotation(keyword="n")])
        assert any("N_MISSING_VALUE" in d for d in diags)


# ---------------------------------------------------------------------------
# Singleton enforcement (declarative singletons per program)
# ---------------------------------------------------------------------------


class TestSingletonEnforcement:
    def test_at_most_one_species(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(keyword="species", positional="rat"),
                Annotation(keyword="species", positional="pigeon"),
            ]
        )
        assert any("SPECIES_MULTIPLE" in d for d in diags)

    def test_at_most_one_strain(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(keyword="strain", positional="Long-Evans"),
                Annotation(keyword="strain", positional="Sprague-Dawley"),
            ]
        )
        assert any("STRAIN_MULTIPLE" in d for d in diags)

    def test_at_most_one_deprivation(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="deprivation",
                    params={"hours": 23, "target": "food"},
                ),
                Annotation(
                    keyword="deprivation",
                    params={"hours": 12, "target": "water"},
                ),
            ]
        )
        assert any("DEPRIVATION_MULTIPLE" in d for d in diags)

    def test_at_most_one_history(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(keyword="history", positional="naive"),
                Annotation(keyword="history", positional="experienced"),
            ]
        )
        assert any("HISTORY_MULTIPLE" in d for d in diags)

    def test_at_most_one_n(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(keyword="n", positional=8),
                Annotation(keyword="n", positional=4),
            ]
        )
        assert any("N_MULTIPLE" in d for d in diags)


# ---------------------------------------------------------------------------
# Mixed / non-relevant input handling
# ---------------------------------------------------------------------------


class TestValidateMixed:
    def test_validate_ignores_non_annotation_objects(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate([object(), 42, "not_an_annotation"])
        assert diags == []

    def test_validate_ignores_unrelated_keywords(self) -> None:
        ext = SubjectsExtension()
        diags = ext.validate(
            [
                Annotation(keyword="reinforcer", positional="food"),
                Annotation(keyword="clock", params={"unit": "s"}),
            ]
        )
        assert diags == []


# ---------------------------------------------------------------------------
# extract_declarations
# ---------------------------------------------------------------------------


class TestExtractDeclarations:
    def test_empty_program(self) -> None:
        program = Program(schedule=Special("EXT"))
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.species is None
        assert decls.strain is None
        assert decls.deprivation is None
        assert decls.history is None
        assert decls.n is None

    def test_full_preamble(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="species", positional="rat"),
                Annotation(keyword="strain", positional="Long-Evans"),
                Annotation(
                    keyword="deprivation",
                    params={"hours": 23, "target": "food"},
                ),
                Annotation(keyword="history", positional="naive"),
                Annotation(keyword="n", positional=8),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)

        assert decls.species == SpeciesAnnotation(species="rat")
        assert decls.strain == StrainAnnotation(strain="Long-Evans")
        assert decls.deprivation == DeprivationAnnotation(
            hours=23.0, target="food"
        )
        assert decls.history == HistoryAnnotation(history="naive")
        assert decls.n == NAnnotation(n=8)

    def test_partial_preamble(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="species", positional="pigeon"),
                Annotation(keyword="n", positional=4),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.species == SpeciesAnnotation(species="pigeon")
        assert decls.n == NAnnotation(n=4)
        assert decls.strain is None
        assert decls.deprivation is None
        assert decls.history is None

    def test_unrelated_annotations_ignored(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="reinforcer", positional="food"),
                Annotation(keyword="species", positional="rat"),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.species == SpeciesAnnotation(species="rat")
        assert decls.strain is None

    def test_extract_invalid_species_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="species", positional=42),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.species is None

    def test_extract_invalid_strain_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="strain", positional=""),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.strain is None

    def test_extract_invalid_history_yields_none(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="history"),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.history is None

    def test_extract_invalid_deprivation_missing_target(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="deprivation", params={"hours": 23}),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.deprivation is None

    def test_extract_invalid_deprivation_negative_hours(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="deprivation",
                    params={"hours": -1, "target": "food"},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.deprivation is None

    def test_extract_invalid_deprivation_bool_hours(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="deprivation",
                    params={"hours": True, "target": "food"},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.deprivation is None

    def test_extract_invalid_n_zero(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="n", positional=0),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.n is None

    def test_extract_invalid_n_float(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="n", positional=8.5),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.n is None

    def test_extract_invalid_n_missing(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="n"),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.n is None

    def test_extract_invalid_n_bool(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="n", positional=True),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.n is None

    def test_extract_deprivation_integer_hours(self) -> None:
        """Integer hours should be coerced to float in the parsed annotation."""
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="deprivation",
                    params={"hours": 23, "target": "food"},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = SubjectsExtension.extract_declarations(program)
        assert decls.deprivation is not None
        assert decls.deprivation.hours == 23.0
        assert isinstance(decls.deprivation.hours, float)


# ---------------------------------------------------------------------------
# SubjectsDeclarationSet immutability
# ---------------------------------------------------------------------------


class TestSubjectsDeclarationSetImmutability:
    def test_frozen(self) -> None:
        decls = SubjectsDeclarationSet()
        with pytest.raises(Exception):
            decls.species = None  # type: ignore[misc]

    def test_default_all_none(self) -> None:
        decls = SubjectsDeclarationSet()
        assert decls.species is None
        assert decls.strain is None
        assert decls.deprivation is None
        assert decls.history is None
        assert decls.n is None
