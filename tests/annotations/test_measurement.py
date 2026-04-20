"""Tests for measurement-ext: types, validation, and extraction."""
from __future__ import annotations

import pytest

from contingency_dsl.ast import Annotation, Program, Special
from contingency_dsl.extensions import ExtensionRegistry

from contingency_dsl.annotations.measurement import (
    BaselineAnnotation,
    MeasurementDeclarationSet,
    MeasurementExtension,
    SessionEndAnnotation,
    SteadyStateAnnotation,
)
from contingency_dsl.annotations.measurement.validator import (
    ValidationDiagnostic,
    validate_measurement_annotation,
)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestMeasurementExtensionProtocol:
    def test_name_and_version(self) -> None:
        ext = MeasurementExtension()
        assert ext.name == "measurement-ext"
        assert ext.version == "0.1.0"

    def test_annotation_keywords_phase1(self) -> None:
        ext = MeasurementExtension()
        kw = ext.annotation_keywords
        assert "session_end" in kw
        assert "baseline" in kw
        assert "steady_state" in kw

    def test_annotation_keywords_phase2_registered(self) -> None:
        ext = MeasurementExtension()
        kw = ext.annotation_keywords
        assert "dependent_measure" in kw
        assert "phase_end" in kw
        assert "logging" in kw
        assert "iri_window" in kw
        assert "warmup_exclude" in kw

    def test_no_keyword_overlap_with_stimulus(self) -> None:
        """measurement-ext and stimulus-ext must have disjoint keywords."""
        from contingency_dsl.annotations.stimulus import StimulusExtension

        m = MeasurementExtension()
        s = StimulusExtension()
        overlap = m.annotation_keywords & s.annotation_keywords
        assert overlap == set(), f"Keyword overlap: {overlap}"

    def test_registry_build(self) -> None:
        from contingency_dsl.annotations.stimulus import StimulusExtension

        reg = ExtensionRegistry.build(StimulusExtension(), MeasurementExtension())
        assert "session_end" in reg.all_annotation_keywords
        assert "reinforcer" in reg.all_annotation_keywords

    def test_requires_empty(self) -> None:
        ext = MeasurementExtension()
        assert ext.requires == frozenset()

    def test_annotation_types_phase1(self) -> None:
        ext = MeasurementExtension()
        types = ext.annotation_types
        assert types["session_end"] is SessionEndAnnotation
        assert types["baseline"] is BaselineAnnotation
        assert types["steady_state"] is SteadyStateAnnotation


# ---------------------------------------------------------------------------
# @session_end validation
# ---------------------------------------------------------------------------


class TestSessionEndValidation:
    def test_valid_first_rule(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "first",
            "time": {"value": 60, "time_unit": "min"},
            "reinforcers": 60,
        })
        assert diags == []

    def test_valid_time_only(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "time_only",
            "time": {"value": 3600, "time_unit": "s"},
        })
        assert diags == []

    def test_valid_reinforcers_only(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "reinforcers_only",
            "reinforcers": 30,
        })
        assert diags == []

    def test_missing_rule(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "time": {"value": 60, "time_unit": "min"},
        })
        assert any(d.code == "SESSION_END_MISSING_PARAM" for d in diags)

    def test_unknown_rule(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "infinite",
            "time": {"value": 60, "time_unit": "min"},
        })
        assert any(d.code == "SESSION_END_UNKNOWN_RULE" for d in diags)

    def test_first_missing_time(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "first",
            "reinforcers": 60,
        })
        assert any(d.code == "SESSION_END_MISSING_PARAM" for d in diags)

    def test_first_missing_reinforcers(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "first",
            "time": {"value": 60, "time_unit": "min"},
        })
        assert any(d.code == "SESSION_END_MISSING_PARAM" for d in diags)

    def test_time_only_with_reinforcers(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "time_only",
            "time": {"value": 60, "time_unit": "min"},
            "reinforcers": 60,
        })
        assert any(d.code == "SESSION_END_INVALID_COMBO" for d in diags)

    def test_time_only_missing_time(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "time_only",
        })
        assert any(d.code == "SESSION_END_MISSING_PARAM" for d in diags)

    def test_reinforcers_only_with_time(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "reinforcers_only",
            "time": {"value": 60, "time_unit": "min"},
            "reinforcers": 60,
        })
        assert any(d.code == "SESSION_END_INVALID_COMBO" for d in diags)

    def test_reinforcers_only_missing_reinforcers(self) -> None:
        diags = validate_measurement_annotation("session_end", {
            "rule": "reinforcers_only",
        })
        assert any(d.code == "SESSION_END_MISSING_PARAM" for d in diags)


# ---------------------------------------------------------------------------
# @baseline validation
# ---------------------------------------------------------------------------


class TestBaselineValidation:
    def test_valid_minimal(self) -> None:
        diags = validate_measurement_annotation("baseline", {
            "pre_training_sessions": 3,
        })
        assert diags == []

    def test_valid_with_measure(self) -> None:
        diags = validate_measurement_annotation("baseline", {
            "pre_training_sessions": 5,
            "measure": "no_training",
        })
        assert diags == []

    def test_missing_sessions(self) -> None:
        diags = validate_measurement_annotation("baseline", {})
        assert any(d.code == "BASELINE_INVALID_SESSIONS" for d in diags)

    def test_sessions_zero(self) -> None:
        diags = validate_measurement_annotation("baseline", {
            "pre_training_sessions": 0,
        })
        assert any(d.code == "BASELINE_INVALID_SESSIONS" for d in diags)

    def test_sessions_negative(self) -> None:
        diags = validate_measurement_annotation("baseline", {
            "pre_training_sessions": -1,
        })
        assert any(d.code == "BASELINE_INVALID_SESSIONS" for d in diags)

    def test_unknown_measure(self) -> None:
        diags = validate_measurement_annotation("baseline", {
            "pre_training_sessions": 3,
            "measure": "extinction",
        })
        assert any(d.code == "BASELINE_UNKNOWN_MEASURE" for d in diags)

    def test_all_valid_measures(self) -> None:
        for measure in ("operant_level", "no_training", "custom"):
            diags = validate_measurement_annotation("baseline", {
                "pre_training_sessions": 3,
                "measure": measure,
            })
            assert diags == [], f"Expected no diagnostics for measure={measure!r}"


# ---------------------------------------------------------------------------
# @steady_state validation
# ---------------------------------------------------------------------------


class TestSteadyStateValidation:
    def test_valid_minimal(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": 10,
        })
        assert diags == []

    def test_valid_with_min_sessions(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": 10,
            "min_sessions": 7,
        })
        assert diags == []

    def test_missing_window(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "max_change_pct": 10,
        })
        assert any(d.code == "STEADY_STATE_INVALID_WINDOW" for d in diags)

    def test_window_too_small(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 1,
            "max_change_pct": 10,
        })
        assert any(d.code == "STEADY_STATE_INVALID_WINDOW" for d in diags)

    def test_window_exact_minimum(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 2,
            "max_change_pct": 10,
        })
        assert diags == []

    def test_missing_max_change(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
        })
        assert any(d.code == "STEADY_STATE_NEGATIVE_CHANGE" for d in diags)

    def test_negative_max_change(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": -10,
        })
        assert any(d.code == "STEADY_STATE_NEGATIVE_CHANGE" for d in diags)

    def test_zero_max_change_is_valid(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": 0,
        })
        assert diags == []

    def test_min_sessions_less_than_window(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": 10,
            "min_sessions": 3,
        })
        assert any(d.code == "STEADY_STATE_INVALID_MIN_SESSIONS" for d in diags)

    def test_min_sessions_equal_to_window(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": 10,
            "min_sessions": 5,
        })
        assert diags == []

    def test_unknown_measure(self) -> None:
        diags = validate_measurement_annotation("steady_state", {
            "window_sessions": 5,
            "max_change_pct": 10,
            "measure": "response_count",
        })
        assert any(d.code == "STEADY_STATE_UNKNOWN_MEASURE" for d in diags)

    def test_all_valid_measures(self) -> None:
        for measure in ("rate", "reinforcers", "iri", "latency", "custom"):
            diags = validate_measurement_annotation("steady_state", {
                "window_sessions": 5,
                "max_change_pct": 10,
                "measure": measure,
            })
            assert diags == [], f"Expected no diagnostics for measure={measure!r}"


# ---------------------------------------------------------------------------
# Phase 2 keywords pass through without diagnostics
# ---------------------------------------------------------------------------


class TestPhase2Keywords:
    @pytest.mark.parametrize("keyword,params", [
        ("dependent_measure", {"anything": "goes"}),
        ("training_volume", {"anything": "goes"}),
        ("microstructure", {"anything": "goes"}),
        # @phase_end requires at least one stop criterion per schema
        # (PHASE_END_NO_CRITERIA); supply a minimal valid one.
        ("phase_end", {"min_sessions": 1}),
        ("logging", {"anything": "goes"}),
        ("iri_window", {"anything": "goes"}),
        ("warmup_exclude", {"anything": "goes"}),
    ])
    def test_phase2_keyword_no_diagnostics(
        self, keyword: str, params: dict[str, object]
    ) -> None:
        diags = validate_measurement_annotation(keyword, params)
        assert diags == []


# ---------------------------------------------------------------------------
# MeasurementExtension.validate (Annotation objects)
# ---------------------------------------------------------------------------


class TestExtensionValidate:
    def test_validate_valid_annotations(self) -> None:
        ext = MeasurementExtension()
        anns = [
            Annotation(keyword="session_end", params={
                "rule": "first",
                "time": {"value": 60, "time_unit": "min"},
                "reinforcers": 60,
            }),
            Annotation(keyword="baseline", params={"pre_training_sessions": 3}),
        ]
        diagnostics = ext.validate(anns)
        assert diagnostics == []

    def test_validate_invalid_annotations(self) -> None:
        ext = MeasurementExtension()
        anns = [
            Annotation(keyword="session_end", params={"rule": "bogus_rule"}),
        ]
        diagnostics = ext.validate(anns)
        assert len(diagnostics) > 0
        assert any("SESSION_END_UNKNOWN_RULE" in d for d in diagnostics)

    def test_validate_ignores_non_measurement_annotations(self) -> None:
        ext = MeasurementExtension()
        # Pass a non-Annotation object — should not raise
        anns = [object(), 42, "not_an_annotation"]
        diagnostics = ext.validate(anns)
        assert diagnostics == []


# ---------------------------------------------------------------------------
# extract_declarations
# ---------------------------------------------------------------------------


class TestExtractDeclarations:
    def test_full_preamble(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="session_end", params={
                    "rule": "first",
                    "time": {"value": 60, "time_unit": "min"},
                    "reinforcers": 60,
                }),
                Annotation(keyword="baseline", params={
                    "pre_training_sessions": 3,
                }),
                Annotation(keyword="steady_state", params={
                    "window_sessions": 5,
                    "max_change_pct": 10,
                }),
            ),
            schedule=Special("EXT"),
        )
        decls = MeasurementExtension.extract_declarations(program)

        assert decls.session_end is not None
        assert decls.session_end.rule == "first"
        assert decls.session_end.time == 60.0
        assert decls.session_end.time_unit == "min"
        assert decls.session_end.reinforcers == 60

        assert decls.baseline is not None
        assert decls.baseline.pre_training_sessions == 3
        assert decls.baseline.measure == "operant_level"  # default

        assert decls.steady_state is not None
        assert decls.steady_state.window_sessions == 5
        assert decls.steady_state.max_change_pct == 10.0
        assert decls.steady_state.measure == "rate"  # default

    def test_empty_program(self) -> None:
        program = Program(schedule=Special("EXT"))
        decls = MeasurementExtension.extract_declarations(program)
        assert decls.session_end is None
        assert decls.baseline is None
        assert decls.steady_state is None

    def test_partial_preamble_session_end_only(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="session_end", params={
                    "rule": "time_only",
                    "time": 3600,
                }),
            ),
            schedule=Special("EXT"),
        )
        decls = MeasurementExtension.extract_declarations(program)
        assert decls.session_end is not None
        assert decls.session_end.rule == "time_only"
        assert decls.session_end.time == 3600.0
        assert decls.session_end.time_unit is None
        assert decls.session_end.reinforcers is None
        assert decls.baseline is None
        assert decls.steady_state is None

    def test_steady_state_with_all_params(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="steady_state", params={
                    "window_sessions": 5,
                    "max_change_pct": 5.0,
                    "measure": "iri",
                    "min_sessions": 8,
                }),
            ),
            schedule=Special("EXT"),
        )
        decls = MeasurementExtension.extract_declarations(program)
        assert decls.steady_state is not None
        assert decls.steady_state.window_sessions == 5
        assert decls.steady_state.max_change_pct == 5.0
        assert decls.steady_state.measure == "iri"
        assert decls.steady_state.min_sessions == 8

    def test_phase2_annotations_ignored_gracefully(self) -> None:
        """Phase 2 annotations in program_annotations don't raise errors."""
        program = Program(
            program_annotations=(
                Annotation(keyword="dependent_measure", params={"type": "rate"}),
                Annotation(keyword="baseline", params={"pre_training_sessions": 2}),
            ),
            schedule=Special("EXT"),
        )
        decls = MeasurementExtension.extract_declarations(program)
        assert decls.baseline is not None
        assert decls.baseline.pre_training_sessions == 2


# ---------------------------------------------------------------------------
# MeasurementDeclarationSet frozen immutability
# ---------------------------------------------------------------------------


class TestMeasurementDeclarationSetImmutability:
    def test_frozen(self) -> None:
        decls = MeasurementDeclarationSet()
        with pytest.raises(Exception):  # FrozenInstanceError
            decls.session_end = None  # type: ignore[misc]

    def test_session_end_annotation_frozen(self) -> None:
        ann = SessionEndAnnotation(rule="time_only", time=3600.0)
        with pytest.raises(Exception):
            ann.time = 0.0  # type: ignore[misc]

    def test_baseline_annotation_frozen(self) -> None:
        ann = BaselineAnnotation(pre_training_sessions=3)
        with pytest.raises(Exception):
            ann.pre_training_sessions = 0  # type: ignore[misc]

    def test_steady_state_annotation_frozen(self) -> None:
        ann = SteadyStateAnnotation(window_sessions=5, max_change_pct=10.0)
        with pytest.raises(Exception):
            ann.window_sessions = 1  # type: ignore[misc]
