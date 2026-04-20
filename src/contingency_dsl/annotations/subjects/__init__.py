"""subjects-ext: Subjects & history dimension for contingency-dsl.

Adds @species, @strain, @deprivation, @history, @n annotations.
Implements the ExtensionModule protocol defined in contingency-dsl.

References:
    American Psychological Association. (2020). Publication manual of the
        American Psychological Association (7th ed.).
        https://doi.org/10.1037/0000165-000
"""

from .extension import SubjectsExtension
from .types import (
    DeprivationAnnotation,
    HistoryAnnotation,
    NAnnotation,
    SpeciesAnnotation,
    StrainAnnotation,
    SubjectsDeclarationSet,
)

__all__ = [
    "SubjectsExtension",
    "SpeciesAnnotation",
    "StrainAnnotation",
    "DeprivationAnnotation",
    "HistoryAnnotation",
    "NAnnotation",
    "SubjectsDeclarationSet",
]
