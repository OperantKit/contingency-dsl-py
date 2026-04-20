"""Tests for composed-ext: types, validation, protocol conformance, extraction."""
from __future__ import annotations

import pytest

from contingency_dsl import parse
from contingency_dsl.ast import Annotation
from contingency_dsl.extensions import ExtensionModule, ExtensionRegistry

from contingency_dsl.annotations.composed import (
    AvoidanceAnnotation,
    ComposedExtension,
    OmissionAnnotation,
)
from contingency_dsl.annotations import StimulusExtension


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestComposedExtensionProtocol:
    def test_name_and_version(self) -> None:
        ext = ComposedExtension()
        assert ext.name == "composed-ext"
        assert ext.version == "0.1.0"

    def test_annotation_keywords(self) -> None:
        ext = ComposedExtension()
        assert ext.annotation_keywords == frozenset({"omission", "avoidance"})

    def test_annotation_types(self) -> None:
        ext = ComposedExtension()
        types = ext.annotation_types
        assert types["omission"] is OmissionAnnotation
        assert types["avoidance"] is AvoidanceAnnotation

    def test_requires_is_empty(self) -> None:
        assert ComposedExtension().requires == frozenset()

    def test_conforms_to_protocol(self) -> None:
        assert isinstance(ComposedExtension(), ExtensionModule)

    def test_registers_in_extension_registry(self) -> None:
        reg = ExtensionRegistry.build(ComposedExtension())
        assert "omission" in reg.all_annotation_keywords
        assert "avoidance" in reg.all_annotation_keywords

    def test_disjoint_from_stimulus_extension(self) -> None:
        reg = ExtensionRegistry.build(ComposedExtension(), StimulusExtension())
        assert {"omission", "avoidance", "reinforcer", "sd"} <= reg.all_annotation_keywords


# ---------------------------------------------------------------------------
# Validation — @omission
# ---------------------------------------------------------------------------


class TestOmissionValidation:
    def _ann(self, **params) -> Annotation:
        return Annotation(keyword="omission", params=params)

    def test_valid_minimal(self) -> None:
        diag = ComposedExtension().validate([self._ann(response="key_peck")])
        assert diag == []

    def test_valid_with_during(self) -> None:
        diag = ComposedExtension().validate(
            [self._ann(response="key_peck", during="cs")]
        )
        assert diag == []

    def test_missing_response(self) -> None:
        diag = ComposedExtension().validate([self._ann(during="cs")])
        assert any("'response'" in d for d in diag)

    def test_empty_response(self) -> None:
        diag = ComposedExtension().validate([self._ann(response="")])
        assert any("'response'" in d for d in diag)

    def test_invalid_during(self) -> None:
        diag = ComposedExtension().validate(
            [self._ann(response="key_peck", during="nonsense")]
        )
        assert any("during" in d for d in diag)

    def test_unknown_parameter(self) -> None:
        diag = ComposedExtension().validate(
            [self._ann(response="key_peck", bogus=1)]
        )
        assert any("unknown parameter" in d for d in diag)


# ---------------------------------------------------------------------------
# Validation — @avoidance
# ---------------------------------------------------------------------------


class TestAvoidanceValidation:
    def _ann(self, **params) -> Annotation:
        return Annotation(keyword="avoidance", params=params)

    def test_valid_minimal(self) -> None:
        diag = ComposedExtension().validate([self._ann(response="lever_press")])
        assert diag == []

    def test_valid_modes(self) -> None:
        for mode in ("cancel", "postpone"):
            diag = ComposedExtension().validate(
                [self._ann(response="lever_press", mode=mode)]
            )
            assert diag == [], f"mode={mode} should be valid"

    def test_missing_response(self) -> None:
        diag = ComposedExtension().validate([self._ann(mode="cancel")])
        assert any("'response'" in d for d in diag)

    def test_invalid_mode(self) -> None:
        diag = ComposedExtension().validate(
            [self._ann(response="lever_press", mode="nonsense")]
        )
        assert any("mode" in d for d in diag)


# ---------------------------------------------------------------------------
# End-to-end: parse DSL + extract typed annotations
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def _reg(self) -> ExtensionRegistry:
        # composed_ext alone is insufficient for the full composed-procedure
        # DSL (which also uses @cs/@us/... and phase blocks); we register a
        # stub for those keywords here because composed_ext is specifically
        # testing @omission/@avoidance extraction.
        from dataclasses import dataclass
        from typing import ClassVar, Mapping, Sequence, Any

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

        return ExtensionRegistry.build(ComposedExtension(), _RespondentStub())

    def test_extract_omission_from_pair(self) -> None:
        src = (
            "@cs(label=\"key_light\", duration=6s)\n"
            "@us(label=\"grain\")\n\n"
            "phase omission_training:\n"
            "  sessions = 20\n"
            "  Pair.ForwardDelay(key_light, grain, isi=6s, cs_duration=6s) "
            "@omission(response=\"key_peck\", during=\"cs\")"
        )
        result = parse(src, extensions=self._reg())
        extracted = ComposedExtension.extract(result)
        assert len(extracted) == 1
        ann = extracted[0]
        assert isinstance(ann, OmissionAnnotation)
        assert ann.response == "key_peck"
        assert ann.during == "cs"

    def test_extract_avoidance_from_pair(self) -> None:
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
        result = parse(src, extensions=self._reg())
        extracted = ComposedExtension.extract(result)
        assert len(extracted) == 1
        ann = extracted[0]
        assert isinstance(ann, AvoidanceAnnotation)
        assert ann.response == "lever_press"
        assert ann.mode == "cancel"

    def test_extract_empty_when_no_composed_annotations(self) -> None:
        src = "Pair.ForwardDelay(tone, shock, isi=10s, cs_duration=15s)"
        result = parse(src, extensions=self._reg())
        assert ComposedExtension.extract(result.schedule) == []

    def test_default_during_when_omitted(self) -> None:
        src = (
            "@cs(label=\"key_light\", duration=6s)\n"
            "@us(label=\"grain\")\n\n"
            "phase train:\n"
            "  sessions = 1\n"
            "  Pair.ForwardDelay(key_light, grain, isi=6s, cs_duration=6s) "
            "@omission(response=\"key_peck\")"
        )
        result = parse(src, extensions=self._reg())
        extracted = ComposedExtension.extract(result)
        assert extracted[0].during == "cs"  # default

    def test_default_mode_when_omitted(self) -> None:
        src = (
            "@cs(label=\"tone\", duration=5s)\n"
            "@us(label=\"shock\")\n\n"
            "phase train:\n"
            "  sessions = 1\n"
            "  Pair.ForwardDelay(tone, shock, isi=5s, cs_duration=5s) "
            "@avoidance(response=\"lever_press\")"
        )
        result = parse(src, extensions=self._reg())
        extracted = ComposedExtension.extract(result)
        assert extracted[0].mode == "cancel"  # default
