"""SubjectsExtension — implements ExtensionModule for subjects-ext.

Provides @species, @strain, @deprivation, @history, @n annotations.
Schema: contingency-dsl/schema/annotations/subjects.schema.json.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from contingency_dsl.ast import Annotation, Program
from contingency_dsl.extensions import ExtensionModule

from .types import (
    DeprivationAnnotation,
    HistoryAnnotation,
    NAnnotation,
    SpeciesAnnotation,
    StrainAnnotation,
    SubjectsDeclarationSet,
)

_KEYWORDS: frozenset[str] = frozenset(
    {"species", "strain", "deprivation", "history", "n"}
)


class SubjectsExtension:
    """Subjects & history dimension extension.

    Conforms to the ExtensionModule protocol. Declares the biological,
    motivational, and experiential conditions of the subjects: species,
    strain, deprivation operation (establishing operation), prior
    experimental history, and group size. All declarations are
    program-scoped singletons.
    """

    name: ClassVar[str] = "subjects-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return _KEYWORDS

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {
            "species": SpeciesAnnotation,
            "strain": StrainAnnotation,
            "deprivation": DeprivationAnnotation,
            "history": HistoryAnnotation,
            "n": NAnnotation,
        }

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Validate subjects-ext annotations.

        Checks (per subjects.schema.json):
        1. @species requires a positional string.
        2. @strain requires a positional string.
        3. @deprivation requires both `hours` (number >= 0) and `target`
           (string) named parameters; positional is rejected.
        4. @history requires a positional string.
        5. @n requires a positional integer >= 1.
        6. Each keyword may appear at most once per program (declarative
           singleton).
        """
        diagnostics: list[str] = []
        counts: dict[str, int] = {kw: 0 for kw in _KEYWORDS}

        for ann in annotations:
            if not isinstance(ann, Annotation):
                continue
            if ann.keyword not in _KEYWORDS:
                continue
            counts[ann.keyword] += 1
            if ann.keyword == "species":
                diagnostics.extend(_validate_species(ann))
            elif ann.keyword == "strain":
                diagnostics.extend(_validate_strain(ann))
            elif ann.keyword == "deprivation":
                diagnostics.extend(_validate_deprivation(ann))
            elif ann.keyword == "history":
                diagnostics.extend(_validate_history(ann))
            elif ann.keyword == "n":
                diagnostics.extend(_validate_n(ann))

        for kw, count in counts.items():
            if count > 1:
                diagnostics.append(
                    f"{kw.upper()}_MULTIPLE: at most one @{kw} annotation is "
                    f"permitted per program"
                )
        return diagnostics

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @staticmethod
    def extract_declarations(program: Program) -> SubjectsDeclarationSet:
        """Extract a SubjectsDeclarationSet from a Program's program_annotations."""
        species: SpeciesAnnotation | None = None
        strain: StrainAnnotation | None = None
        deprivation: DeprivationAnnotation | None = None
        history: HistoryAnnotation | None = None
        n: NAnnotation | None = None

        for ann in program.program_annotations:
            if ann.keyword == "species":
                parsed_species = _parse_species(ann)
                if parsed_species is not None:
                    species = parsed_species
            elif ann.keyword == "strain":
                parsed_strain = _parse_strain(ann)
                if parsed_strain is not None:
                    strain = parsed_strain
            elif ann.keyword == "deprivation":
                parsed_dep = _parse_deprivation(ann)
                if parsed_dep is not None:
                    deprivation = parsed_dep
            elif ann.keyword == "history":
                parsed_hist = _parse_history(ann)
                if parsed_hist is not None:
                    history = parsed_hist
            elif ann.keyword == "n":
                parsed_n = _parse_n(ann)
                if parsed_n is not None:
                    n = parsed_n

        return SubjectsDeclarationSet(
            species=species,
            strain=strain,
            deprivation=deprivation,
            history=history,
            n=n,
        )


# ---------------------------------------------------------------------------
# Per-annotation validators
# ---------------------------------------------------------------------------


def _validate_species(ann: Annotation) -> list[str]:
    value = ann.positional
    if not isinstance(value, str) or value == "":
        return [
            "SPECIES_MISSING_NAME: @species requires a positional string argument"
        ]
    return []


def _validate_strain(ann: Annotation) -> list[str]:
    value = ann.positional
    if not isinstance(value, str) or value == "":
        return [
            "STRAIN_MISSING_NAME: @strain requires a positional string argument"
        ]
    return []


def _validate_deprivation(ann: Annotation) -> list[str]:
    diagnostics: list[str] = []
    if ann.positional is not None:
        diagnostics.append(
            "DEPRIVATION_UNEXPECTED_POSITIONAL: @deprivation does not accept "
            "positional arguments; use hours= and target= named parameters"
        )

    params = ann.params or {}
    hours = params.get("hours")
    target = params.get("target")

    if hours is None:
        diagnostics.append(
            "DEPRIVATION_MISSING_HOURS: @deprivation requires an 'hours' parameter"
        )
    elif isinstance(hours, bool) or not isinstance(hours, (int, float)):
        diagnostics.append(
            f"DEPRIVATION_INVALID_HOURS: @deprivation 'hours' must be a "
            f"non-negative number, got {hours!r}"
        )
    elif hours < 0:
        diagnostics.append(
            f"DEPRIVATION_NEGATIVE_HOURS: @deprivation 'hours' must be "
            f"non-negative, got {hours}"
        )

    if target is None:
        diagnostics.append(
            "DEPRIVATION_MISSING_TARGET: @deprivation requires a 'target' parameter"
        )
    elif not isinstance(target, str) or target == "":
        diagnostics.append(
            f"DEPRIVATION_INVALID_TARGET: @deprivation 'target' must be a "
            f"non-empty string, got {target!r}"
        )

    return diagnostics


def _validate_history(ann: Annotation) -> list[str]:
    value = ann.positional
    if not isinstance(value, str) or value == "":
        return [
            "HISTORY_MISSING_DESCRIPTOR: @history requires a positional string "
            "argument"
        ]
    return []


def _validate_n(ann: Annotation) -> list[str]:
    value = ann.positional
    if value is None:
        return ["N_MISSING_VALUE: @n requires a positional integer argument"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [
            f"N_INVALID_VALUE: @n must be a positive integer >= 1, got {value!r}"
        ]
    n_int = int(value)
    if n_int != value or n_int < 1:
        return [
            f"N_INVALID_VALUE: @n must be a positive integer >= 1, got {value!r}"
        ]
    return []


# ---------------------------------------------------------------------------
# Per-annotation parsers
# ---------------------------------------------------------------------------


def _parse_species(ann: Annotation) -> SpeciesAnnotation | None:
    value = ann.positional
    if not isinstance(value, str) or value == "":
        return None
    return SpeciesAnnotation(species=value)


def _parse_strain(ann: Annotation) -> StrainAnnotation | None:
    value = ann.positional
    if not isinstance(value, str) or value == "":
        return None
    return StrainAnnotation(strain=value)


def _parse_deprivation(ann: Annotation) -> DeprivationAnnotation | None:
    params = ann.params or {}
    hours_raw = params.get("hours")
    target = params.get("target")
    if isinstance(hours_raw, bool) or not isinstance(hours_raw, (int, float)):
        return None
    if hours_raw < 0:
        return None
    if not isinstance(target, str) or target == "":
        return None
    return DeprivationAnnotation(hours=float(hours_raw), target=target)


def _parse_history(ann: Annotation) -> HistoryAnnotation | None:
    value = ann.positional
    if not isinstance(value, str) or value == "":
        return None
    return HistoryAnnotation(history=value)


def _parse_n(ann: Annotation) -> NAnnotation | None:
    value = ann.positional
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    n_int = int(value)
    if n_int != value or n_int < 1:
        return None
    return NAnnotation(n=n_int)


# Static check: SubjectsExtension conforms to ExtensionModule Protocol.
_: ExtensionModule = SubjectsExtension()
