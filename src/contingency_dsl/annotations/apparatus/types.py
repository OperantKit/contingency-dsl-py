"""Annotation dataclasses for apparatus-ext.

Frozen dataclasses representing parsed and validated apparatus annotations
extracted from a DSL program-level preamble: chamber identity, hardware
interface, and the physical hardware backend.

All three declarations are program-scoped singletons. Per the apparatus
annotator spec, the runtime that binds these declared identities to a
concrete driver lives in ``experiment-io``; this annotator only declares
*which* apparatus the program targets.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChamberAnnotation:
    """Parsed @chamber annotation.

    Identifies the experimental chamber. The positional argument is the
    chamber vendor or family name; the optional ``model`` parameter is a
    chamber model identifier.

    Examples:
        @chamber("med-associates")
        @chamber("med-associates", model="ENV-007")
    """

    chamber: str
    model: str | None = None


@dataclass(frozen=True)
class InterfaceAnnotation:
    """Parsed @interface annotation.

    Declares the hardware interface protocol used to drive the apparatus.
    The positional argument is the protocol or interface name; the optional
    ``port`` parameter is a device-port path.

    Examples:
        @interface("serial")
        @interface("serial", port="/dev/ttyUSB0")
    """

    interface: str
    port: str | None = None


@dataclass(frozen=True)
class HardwareAnnotation:
    """Parsed @hardware (alias @hw) annotation.

    Declares the physical hardware backend that realises the apparatus.
    The keyword has no parameters beyond a single positional name. Presence
    of @hardware implies a physical apparatus; omission implies a virtual
    or simulation backend.

    The canonical keyword surfaces as ``hardware``; the ``hw`` alias
    resolves to the same dataclass.

    Examples:
        @hardware("med-associates")
        @hw("med-associates")
    """

    hardware: str


@dataclass(frozen=True)
class ApparatusDeclarationSet:
    """All apparatus declarations extracted from a single DSL program preamble.

    All three fields are program-scoped singletons.
    """

    chamber: ChamberAnnotation | None = None
    interface: InterfaceAnnotation | None = None
    hardware: HardwareAnnotation | None = None
