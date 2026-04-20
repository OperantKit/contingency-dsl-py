"""ApparatusExtension — implements ExtensionModule for apparatus-ext.

Provides @chamber, @interface, @hardware (alias @hw) annotations.
Schema: contingency-dsl/schema/annotations/apparatus.schema.json.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from contingency_dsl.ast import Annotation, Program
from contingency_dsl.extensions import ExtensionModule

from .types import (
    ApparatusDeclarationSet,
    ChamberAnnotation,
    HardwareAnnotation,
    InterfaceAnnotation,
)

_HARDWARE_KEYWORDS: frozenset[str] = frozenset({"hardware", "hw"})


class ApparatusExtension:
    """Apparatus & hardware declaration dimension extension.

    Conforms to the ExtensionModule protocol. Declares the chamber model,
    hardware interface, and physical hardware backend that realise the
    contingency program. The declarations are program-level intent only;
    the experiment-io runtime resolves them to concrete drivers.
    """

    name: ClassVar[str] = "apparatus-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"chamber", "interface", "hardware", "hw"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {
            "chamber": ChamberAnnotation,
            "interface": InterfaceAnnotation,
            "hardware": HardwareAnnotation,
            "hw": HardwareAnnotation,
        }

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Validate apparatus-ext annotations.

        Checks:
        1. @chamber requires a positional string. Optional ``model`` is a string.
        2. @interface requires a positional string. Optional ``port`` is a string.
        3. @hardware / @hw requires a positional string and accepts no params.
        4. Each canonical keyword is declared at most once per program.
        5. @hw and @hardware do not co-occur (alias collision).
        """
        diagnostics: list[str] = []
        chamber_count = 0
        interface_count = 0
        hardware_count = 0
        hw_alias_count = 0
        canonical_hardware_count = 0

        for ann in annotations:
            if not isinstance(ann, Annotation):
                continue
            if ann.keyword == "chamber":
                chamber_count += 1
                diagnostics.extend(_validate_chamber(ann))
            elif ann.keyword == "interface":
                interface_count += 1
                diagnostics.extend(_validate_interface(ann))
            elif ann.keyword in _HARDWARE_KEYWORDS:
                hardware_count += 1
                if ann.keyword == "hw":
                    hw_alias_count += 1
                else:
                    canonical_hardware_count += 1
                diagnostics.extend(_validate_hardware(ann))

        if chamber_count > 1:
            diagnostics.append(
                "CHAMBER_MULTIPLE: at most one @chamber annotation is permitted "
                "per program"
            )
        if interface_count > 1:
            diagnostics.append(
                "INTERFACE_MULTIPLE: at most one @interface annotation is "
                "permitted per program"
            )
        if hardware_count > 1:
            diagnostics.append(
                "HARDWARE_MULTIPLE: at most one @hardware annotation is "
                "permitted per program"
            )
        if hw_alias_count >= 1 and canonical_hardware_count >= 1:
            diagnostics.append(
                "HARDWARE_ALIAS_COLLISION: @hw and @hardware refer to the same "
                "declaration; specify only one"
            )

        return diagnostics

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @staticmethod
    def extract_declarations(program: Program) -> ApparatusDeclarationSet:
        """Extract an ApparatusDeclarationSet from a Program's program_annotations."""
        chamber: ChamberAnnotation | None = None
        interface: InterfaceAnnotation | None = None
        hardware: HardwareAnnotation | None = None

        for ann in program.program_annotations:
            if ann.keyword == "chamber":
                parsed_chamber = _parse_chamber(ann)
                if parsed_chamber is not None:
                    chamber = parsed_chamber
            elif ann.keyword == "interface":
                parsed_interface = _parse_interface(ann)
                if parsed_interface is not None:
                    interface = parsed_interface
            elif ann.keyword in _HARDWARE_KEYWORDS:
                parsed_hardware = _parse_hardware(ann)
                if parsed_hardware is not None:
                    hardware = parsed_hardware

        return ApparatusDeclarationSet(
            chamber=chamber,
            interface=interface,
            hardware=hardware,
        )


# ---------------------------------------------------------------------------
# Per-annotation validators
# ---------------------------------------------------------------------------


def _validate_chamber(ann: Annotation) -> list[str]:
    diagnostics: list[str] = []
    if not isinstance(ann.positional, str) or ann.positional == "":
        diagnostics.append(
            "CHAMBER_MISSING_NAME: @chamber requires a positional string argument"
        )
    params = ann.params or {}
    model = params.get("model")
    if model is not None and not isinstance(model, str):
        diagnostics.append(
            f"CHAMBER_INVALID_MODEL: @chamber 'model' must be a string, "
            f"got {model!r}"
        )
    return diagnostics


def _validate_interface(ann: Annotation) -> list[str]:
    diagnostics: list[str] = []
    if not isinstance(ann.positional, str) or ann.positional == "":
        diagnostics.append(
            "INTERFACE_MISSING_NAME: @interface requires a positional string "
            "argument"
        )
    params = ann.params or {}
    port = params.get("port")
    if port is not None and not isinstance(port, str):
        diagnostics.append(
            f"INTERFACE_INVALID_PORT: @interface 'port' must be a string, "
            f"got {port!r}"
        )
    return diagnostics


def _validate_hardware(ann: Annotation) -> list[str]:
    diagnostics: list[str] = []
    label = "@hw" if ann.keyword == "hw" else "@hardware"
    if not isinstance(ann.positional, str) or ann.positional == "":
        diagnostics.append(
            f"HARDWARE_MISSING_NAME: {label} requires a positional string "
            f"argument"
        )
    params = ann.params or {}
    if params:
        diagnostics.append(
            f"HARDWARE_UNEXPECTED_PARAMS: {label} accepts no named parameters, "
            f"got {sorted(params.keys())}"
        )
    return diagnostics


# ---------------------------------------------------------------------------
# Per-annotation parsers
# ---------------------------------------------------------------------------


def _parse_chamber(ann: Annotation) -> ChamberAnnotation | None:
    if not isinstance(ann.positional, str) or ann.positional == "":
        return None
    params = ann.params or {}
    model_raw = params.get("model")
    model: str | None = model_raw if isinstance(model_raw, str) else None
    return ChamberAnnotation(chamber=ann.positional, model=model)


def _parse_interface(ann: Annotation) -> InterfaceAnnotation | None:
    if not isinstance(ann.positional, str) or ann.positional == "":
        return None
    params = ann.params or {}
    port_raw = params.get("port")
    port: str | None = port_raw if isinstance(port_raw, str) else None
    return InterfaceAnnotation(interface=ann.positional, port=port)


def _parse_hardware(ann: Annotation) -> HardwareAnnotation | None:
    if not isinstance(ann.positional, str) or ann.positional == "":
        return None
    return HardwareAnnotation(hardware=ann.positional)


# Static check: ApparatusExtension conforms to ExtensionModule Protocol.
_: ExtensionModule = ApparatusExtension()
