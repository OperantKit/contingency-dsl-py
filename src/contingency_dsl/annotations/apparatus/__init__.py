"""apparatus-ext: Apparatus & hardware-declaration dimension for contingency-dsl.

Adds @chamber, @interface, @hardware (alias @hw) annotations.
Implements the ExtensionModule protocol defined in contingency-dsl.

Spec: contingency-dsl/annotations/apparatus-annotator/.
Schema: contingency-dsl/schema/annotations/apparatus.schema.json.
"""

from .extension import ApparatusExtension
from .types import (
    ApparatusDeclarationSet,
    ChamberAnnotation,
    HardwareAnnotation,
    InterfaceAnnotation,
)

__all__ = [
    "ApparatusExtension",
    "ChamberAnnotation",
    "InterfaceAnnotation",
    "HardwareAnnotation",
    "ApparatusDeclarationSet",
]
