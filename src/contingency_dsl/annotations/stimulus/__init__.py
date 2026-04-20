"""stimulus-ext: Stimulus identity dimension for contingency-dsl.

Adds @reinforcer, @sd, @operandum, @brief annotations.
Implements the ExtensionModule protocol defined in contingency-dsl.

Reference: theory.md §4.7
"""

from .extension import StimulusExtension
from .types import (
    BriefAnnotation,
    OperandumAnnotation,
    ReinforcerAnnotation,
    SDAnnotation,
    StimulusDeclarationSet,
)

__all__ = [
    "StimulusExtension",
    "ReinforcerAnnotation",
    "SDAnnotation",
    "OperandumAnnotation",
    "BriefAnnotation",
    "StimulusDeclarationSet",
]
