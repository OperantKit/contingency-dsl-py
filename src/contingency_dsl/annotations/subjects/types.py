"""Annotation dataclasses for subjects-ext.

Frozen dataclasses representing parsed and validated subjects annotations
extracted from DSL program-level preamble. Declares the biological,
motivational, and experiential conditions of the organisms run under a
contingency program: species, strain, deprivation operation, prior
experimental history, and group size.

References:
    American Psychological Association. (2020). Publication manual of the
        American Psychological Association (7th ed.).
        https://doi.org/10.1037/0000165-000
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeciesAnnotation:
    """Parsed @species annotation.

    Declares the species of the subjects run under the program.

    Examples:
        @species("rat")
        @species("pigeon")
    """

    species: str


@dataclass(frozen=True)
class StrainAnnotation:
    """Parsed @strain annotation.

    Declares the strain of the subjects (e.g., "Long-Evans", "Sprague-Dawley").

    Examples:
        @strain("Long-Evans")
        @strain("Sprague-Dawley")
    """

    strain: str


@dataclass(frozen=True)
class DeprivationAnnotation:
    """Parsed @deprivation annotation.

    Declares the establishing operation that maintains the reinforcer's
    efficacy: hours of deprivation and the deprivation target.

    Examples:
        @deprivation(hours=23, target="food")
        @deprivation(hours=12, target="water")
    """

    hours: float
    target: str


@dataclass(frozen=True)
class HistoryAnnotation:
    """Parsed @history annotation.

    Free-form descriptor of the subjects' prior experimental history.

    Examples:
        @history("naive")
        @history("experienced: 6 months lever-press training")
    """

    history: str


@dataclass(frozen=True)
class NAnnotation:
    """Parsed @n annotation.

    Number of subjects in the group. Must be a positive integer.

    Examples:
        @n(8)
        @n(4)
    """

    n: int


@dataclass(frozen=True)
class SubjectsDeclarationSet:
    """All subjects declarations extracted from a single DSL program preamble.

    All fields are program-scoped singletons; each keyword may appear at
    most once per program.
    """

    species: SpeciesAnnotation | None = None
    strain: StrainAnnotation | None = None
    deprivation: DeprivationAnnotation | None = None
    history: HistoryAnnotation | None = None
    n: NAnnotation | None = None
