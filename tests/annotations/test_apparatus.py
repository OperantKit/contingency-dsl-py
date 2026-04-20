"""Tests for apparatus-ext: types, validation, and extraction."""
from __future__ import annotations

import pytest

from contingency_dsl.ast import Annotation, Program, Special
from contingency_dsl.extensions import ExtensionModule, ExtensionRegistry

from contingency_dsl.annotations.apparatus import (
    ApparatusDeclarationSet,
    ApparatusExtension,
    ChamberAnnotation,
    HardwareAnnotation,
    InterfaceAnnotation,
)


# ---------------------------------------------------------------------------
# Module surface / protocol conformance
# ---------------------------------------------------------------------------


class TestApparatusExtensionProtocol:
    def test_name_and_version(self) -> None:
        ext = ApparatusExtension()
        assert ext.name == "apparatus-ext"
        assert ext.version == "0.1.0"

    def test_annotation_keywords(self) -> None:
        ext = ApparatusExtension()
        assert ext.annotation_keywords == frozenset(
            {"chamber", "interface", "hardware", "hw"}
        )

    def test_annotation_types_mapping(self) -> None:
        ext = ApparatusExtension()
        types = ext.annotation_types
        assert types["chamber"] is ChamberAnnotation
        assert types["interface"] is InterfaceAnnotation
        assert types["hardware"] is HardwareAnnotation
        assert types["hw"] is HardwareAnnotation
        # @hw is an alias of @hardware -> same dataclass
        assert types["hw"] is types["hardware"]

    def test_requires_empty(self) -> None:
        ext = ApparatusExtension()
        assert ext.requires == frozenset()

    def test_runtime_protocol_conformance(self) -> None:
        ext = ApparatusExtension()
        assert isinstance(ext, ExtensionModule)

    def test_no_keyword_overlap_with_temporal(self) -> None:
        from contingency_dsl.annotations.temporal import TemporalExtension

        a = ApparatusExtension()
        t = TemporalExtension()
        assert a.annotation_keywords & t.annotation_keywords == frozenset()

    def test_no_keyword_overlap_with_stimulus(self) -> None:
        # Per spec README, @operandum currently lives in stimulus-ext
        # (apparatus-ext does NOT claim it). The two extensions must be
        # disjoint in keywords for ExtensionRegistry.build to succeed.
        from contingency_dsl.annotations.stimulus import StimulusExtension

        a = ApparatusExtension()
        s = StimulusExtension()
        assert a.annotation_keywords & s.annotation_keywords == frozenset()

    def test_does_not_claim_operandum(self) -> None:
        # apparatus-ext must not include @operandum: it is currently in
        # stimulus-ext per implementation truth.
        ext = ApparatusExtension()
        assert "operandum" not in ext.annotation_keywords

    def test_registry_build_with_other_extensions(self) -> None:
        from contingency_dsl.annotations.stimulus import StimulusExtension
        from contingency_dsl.annotations.temporal import TemporalExtension

        reg = ExtensionRegistry.build(
            StimulusExtension(), TemporalExtension(), ApparatusExtension()
        )
        assert "chamber" in reg.all_annotation_keywords
        assert "interface" in reg.all_annotation_keywords
        assert "hardware" in reg.all_annotation_keywords
        assert "hw" in reg.all_annotation_keywords


# ---------------------------------------------------------------------------
# Annotation dataclass instantiation
# ---------------------------------------------------------------------------


class TestChamberAnnotation:
    def test_construct_minimal(self) -> None:
        ann = ChamberAnnotation(chamber="med-associates")
        assert ann.chamber == "med-associates"
        assert ann.model is None

    def test_construct_with_model(self) -> None:
        ann = ChamberAnnotation(chamber="med-associates", model="ENV-007")
        assert ann.chamber == "med-associates"
        assert ann.model == "ENV-007"

    def test_frozen(self) -> None:
        ann = ChamberAnnotation(chamber="med-associates")
        with pytest.raises(Exception):
            ann.chamber = "other"  # type: ignore[misc]


class TestInterfaceAnnotation:
    def test_construct_minimal(self) -> None:
        ann = InterfaceAnnotation(interface="serial")
        assert ann.interface == "serial"
        assert ann.port is None

    def test_construct_with_port(self) -> None:
        ann = InterfaceAnnotation(interface="serial", port="/dev/ttyUSB0")
        assert ann.interface == "serial"
        assert ann.port == "/dev/ttyUSB0"

    def test_frozen(self) -> None:
        ann = InterfaceAnnotation(interface="serial")
        with pytest.raises(Exception):
            ann.interface = "usb"  # type: ignore[misc]


class TestHardwareAnnotation:
    def test_construct(self) -> None:
        ann = HardwareAnnotation(hardware="med-associates")
        assert ann.hardware == "med-associates"

    def test_frozen(self) -> None:
        ann = HardwareAnnotation(hardware="med-associates")
        with pytest.raises(Exception):
            ann.hardware = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------


class TestChamberValidation:
    def test_valid_minimal(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [Annotation(keyword="chamber", positional="med-associates")]
        )
        assert diags == []

    def test_valid_with_model(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="chamber",
                    positional="med-associates",
                    params={"model": "ENV-007"},
                )
            ]
        )
        assert diags == []

    def test_missing_positional(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate([Annotation(keyword="chamber")])
        assert any("CHAMBER_MISSING_NAME" in d for d in diags)

    def test_empty_positional(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [Annotation(keyword="chamber", positional="")]
        )
        assert any("CHAMBER_MISSING_NAME" in d for d in diags)

    def test_non_string_model(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="chamber",
                    positional="med-associates",
                    params={"model": 42},
                )
            ]
        )
        assert any("CHAMBER_INVALID_MODEL" in d for d in diags)

    def test_at_most_one_chamber(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(keyword="chamber", positional="a"),
                Annotation(keyword="chamber", positional="b"),
            ]
        )
        assert any("CHAMBER_MULTIPLE" in d for d in diags)


class TestInterfaceValidation:
    def test_valid_minimal(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [Annotation(keyword="interface", positional="serial")]
        )
        assert diags == []

    def test_valid_with_port(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="interface",
                    positional="serial",
                    params={"port": "/dev/ttyUSB0"},
                )
            ]
        )
        assert diags == []

    def test_missing_positional(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate([Annotation(keyword="interface")])
        assert any("INTERFACE_MISSING_NAME" in d for d in diags)

    def test_non_string_port(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="interface",
                    positional="serial",
                    params={"port": 9600},
                )
            ]
        )
        assert any("INTERFACE_INVALID_PORT" in d for d in diags)

    def test_at_most_one_interface(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(keyword="interface", positional="serial"),
                Annotation(keyword="interface", positional="usb"),
            ]
        )
        assert any("INTERFACE_MULTIPLE" in d for d in diags)


class TestHardwareValidation:
    def test_valid_canonical(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [Annotation(keyword="hardware", positional="med-associates")]
        )
        assert diags == []

    def test_valid_alias_hw(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [Annotation(keyword="hw", positional="med-associates")]
        )
        assert diags == []

    def test_missing_positional_canonical(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate([Annotation(keyword="hardware")])
        assert any("HARDWARE_MISSING_NAME" in d for d in diags)

    def test_missing_positional_alias(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate([Annotation(keyword="hw")])
        assert any("HARDWARE_MISSING_NAME" in d for d in diags)

    def test_unexpected_params_rejected(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="hardware",
                    positional="med-associates",
                    params={"model": "ENV-007"},
                )
            ]
        )
        assert any("HARDWARE_UNEXPECTED_PARAMS" in d for d in diags)

    def test_at_most_one_hardware_canonical(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(keyword="hardware", positional="a"),
                Annotation(keyword="hardware", positional="b"),
            ]
        )
        assert any("HARDWARE_MULTIPLE" in d for d in diags)

    def test_alias_collision_diagnostic(self) -> None:
        # @hw and @hardware are the same canonical declaration; both
        # appearing simultaneously is an alias collision.
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(keyword="hardware", positional="a"),
                Annotation(keyword="hw", positional="a"),
            ]
        )
        assert any("HARDWARE_ALIAS_COLLISION" in d for d in diags)


class TestValidateMixed:
    def test_validate_ignores_non_annotation_objects(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate([object(), 42, "not_an_annotation"])
        assert diags == []

    def test_validate_ignores_unrelated_keywords(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [Annotation(keyword="reinforcer", positional="food")]
        )
        assert diags == []

    def test_validate_full_preamble(self) -> None:
        ext = ApparatusExtension()
        diags = ext.validate(
            [
                Annotation(
                    keyword="chamber",
                    positional="med-associates",
                    params={"model": "ENV-007"},
                ),
                Annotation(
                    keyword="interface",
                    positional="serial",
                    params={"port": "/dev/ttyUSB0"},
                ),
                Annotation(keyword="hardware", positional="med-associates"),
            ]
        )
        assert diags == []


# ---------------------------------------------------------------------------
# extract_declarations
# ---------------------------------------------------------------------------


class TestExtractDeclarations:
    def test_empty_program(self) -> None:
        program = Program(schedule=Special("EXT"))
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.chamber is None
        assert decls.interface is None
        assert decls.hardware is None

    def test_full_preamble(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="chamber",
                    positional="med-associates",
                    params={"model": "ENV-007"},
                ),
                Annotation(
                    keyword="interface",
                    positional="serial",
                    params={"port": "/dev/ttyUSB0"},
                ),
                Annotation(keyword="hardware", positional="med-associates"),
            ),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)

        assert decls.chamber is not None
        assert decls.chamber.chamber == "med-associates"
        assert decls.chamber.model == "ENV-007"

        assert decls.interface is not None
        assert decls.interface.interface == "serial"
        assert decls.interface.port == "/dev/ttyUSB0"

        assert decls.hardware is not None
        assert decls.hardware.hardware == "med-associates"

    def test_chamber_only(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="chamber", positional="med-associates"),
            ),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.chamber is not None
        assert decls.chamber.chamber == "med-associates"
        assert decls.chamber.model is None
        assert decls.interface is None
        assert decls.hardware is None

    def test_alias_hw_resolves_to_hardware(self) -> None:
        # @hw should populate the hardware field exactly like @hardware
        program = Program(
            program_annotations=(
                Annotation(keyword="hw", positional="med-associates"),
            ),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.hardware is not None
        assert isinstance(decls.hardware, HardwareAnnotation)
        assert decls.hardware.hardware == "med-associates"

    def test_extract_chamber_missing_positional_yields_none(self) -> None:
        program = Program(
            program_annotations=(Annotation(keyword="chamber"),),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.chamber is None

    def test_extract_interface_missing_positional_yields_none(self) -> None:
        program = Program(
            program_annotations=(Annotation(keyword="interface"),),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.interface is None

    def test_extract_hardware_missing_positional_yields_none(self) -> None:
        program = Program(
            program_annotations=(Annotation(keyword="hardware"),),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.hardware is None

    def test_extract_chamber_with_non_string_model_drops_model(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="chamber",
                    positional="med-associates",
                    params={"model": 42},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.chamber is not None
        assert decls.chamber.chamber == "med-associates"
        assert decls.chamber.model is None

    def test_extract_interface_with_non_string_port_drops_port(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(
                    keyword="interface",
                    positional="serial",
                    params={"port": 9600},
                ),
            ),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.interface is not None
        assert decls.interface.interface == "serial"
        assert decls.interface.port is None

    def test_unrelated_annotations_ignored(self) -> None:
        program = Program(
            program_annotations=(
                Annotation(keyword="reinforcer", positional="food"),
                Annotation(keyword="chamber", positional="med-associates"),
            ),
            schedule=Special("EXT"),
        )
        decls = ApparatusExtension.extract_declarations(program)
        assert decls.chamber is not None
        assert decls.chamber.chamber == "med-associates"


# ---------------------------------------------------------------------------
# ApparatusDeclarationSet immutability
# ---------------------------------------------------------------------------


class TestApparatusDeclarationSetImmutability:
    def test_frozen(self) -> None:
        decls = ApparatusDeclarationSet()
        with pytest.raises(Exception):
            decls.chamber = None  # type: ignore[misc]

    def test_default_factory_independence(self) -> None:
        a = ApparatusDeclarationSet()
        b = ApparatusDeclarationSet()
        assert a == b
        assert a is not b
