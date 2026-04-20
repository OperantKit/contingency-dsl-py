"""StimulusExtension — implements ExtensionModule for stimulus-ext.

Provides @reinforcer, @sd, @operandum, @brief annotations.
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from contingency_dsl.ast import AnnotatedSchedule, Annotation, ScheduleExpr

from .types import (
    BriefAnnotation,
    OperandumAnnotation,
    ReinforcerAnnotation,
    SDAnnotation,
    StimulusDeclarationSet,
)


class StimulusExtension:
    """Stimulus identity dimension extension (§4.7).

    Conforms to the ExtensionModule protocol.
    """

    name: ClassVar[str] = "stimulus-ext"
    version: ClassVar[str] = "0.1.0"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"reinforcer", "sd", "operandum", "brief"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {
            "reinforcer": ReinforcerAnnotation,
            "sd": SDAnnotation,
            "operandum": OperandumAnnotation,
            "brief": BriefAnnotation,
        }

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Validate stimulus-ext annotations.

        Checks:
        1. Conditioned reinforcers must specify backup
        2. Generalized reinforcers must have 2+ backups
        3. Operandum names must be unique within a Conc
        """
        diagnostics: list[str] = []
        reinforcer_names: set[str] = set()
        backup_refs: set[str] = set()

        for ann in annotations:
            if isinstance(ann, ReinforcerAnnotation):
                reinforcer_names.add(ann.name)
                if ann.reinforcer_type == "conditioned" and not ann.backup_ids:
                    diagnostics.append(
                        f"conditioned reinforcer '{ann.name}' must specify at least one backup"
                    )
                if ann.reinforcer_type == "generalized" and len(ann.backup_ids) < 2:
                    diagnostics.append(
                        f"generalized reinforcer '{ann.name}' must specify at least 2 backups"
                    )
                for bid in ann.backup_ids:
                    backup_refs.add(bid)

        # Check referential integrity: backup references must exist
        for ref in backup_refs:
            if ref not in reinforcer_names:
                diagnostics.append(
                    f"backup reinforcer '{ref}' referenced but not declared"
                )

        return diagnostics

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @staticmethod
    def extract_declarations(program_schedule: ScheduleExpr) -> StimulusDeclarationSet:
        """Extract StimulusDeclarationSet from an annotated AST.

        Walks the AST and collects all stimulus-ext annotations.
        """
        reinforcers: dict[str, ReinforcerAnnotation] = {}
        operandum_bindings: dict[str, OperandumAnnotation] = {}
        sd_bindings: dict[str, SDAnnotation] = {}
        brief_specs: dict[str, BriefAnnotation] = {}

        _collect_annotations(
            program_schedule, reinforcers, operandum_bindings, sd_bindings, brief_specs
        )

        return StimulusDeclarationSet(
            reinforcers=reinforcers,
            operandum_bindings=operandum_bindings,
            sd_bindings=sd_bindings,
            brief_specs=brief_specs,
        )


def _collect_annotations(
    expr: ScheduleExpr,
    reinforcers: dict[str, ReinforcerAnnotation],
    operandum_bindings: dict[str, OperandumAnnotation],
    sd_bindings: dict[str, SDAnnotation],
    brief_specs: dict[str, BriefAnnotation],
) -> None:
    """Recursively collect stimulus-ext annotations from the AST."""
    from contingency_dsl.ast import Compound, LimitedHold, Modifier

    match expr:
        case AnnotatedSchedule(expr=inner, annotations=anns):
            for ann in anns:
                _process_annotation(
                    ann, reinforcers, operandum_bindings, sd_bindings, brief_specs
                )
            _collect_annotations(
                inner, reinforcers, operandum_bindings, sd_bindings, brief_specs
            )

        case Compound(components=components):
            for comp in components:
                _collect_annotations(
                    comp, reinforcers, operandum_bindings, sd_bindings, brief_specs
                )

        case LimitedHold(inner=inner):
            _collect_annotations(
                inner, reinforcers, operandum_bindings, sd_bindings, brief_specs
            )

        case Modifier(inner=inner) if inner is not None:
            _collect_annotations(
                inner, reinforcers, operandum_bindings, sd_bindings, brief_specs
            )


def _process_annotation(
    ann: Annotation,
    reinforcers: dict[str, ReinforcerAnnotation],
    operandum_bindings: dict[str, OperandumAnnotation],
    sd_bindings: dict[str, SDAnnotation],
    brief_specs: dict[str, BriefAnnotation],
) -> None:
    """Convert a raw Annotation AST node into a typed annotation dataclass."""
    if ann.keyword == "reinforcer":
        reinforcers[_get_positional_str(ann)] = _parse_reinforcer(ann)
    elif ann.keyword == "sd":
        sd_bindings[_get_positional_str(ann)] = _parse_sd(ann)
    elif ann.keyword == "operandum":
        operandum_bindings[_get_positional_str(ann)] = _parse_operandum(ann)
    elif ann.keyword == "brief":
        brief_specs[_get_positional_str(ann)] = _parse_brief(ann)


def _get_positional_str(ann: Annotation) -> str:
    """Get the positional string argument from an annotation."""
    if isinstance(ann.positional, str):
        return ann.positional
    return ""


def _get_kwarg(ann: Annotation, key: str) -> str | float | None:
    """Get a keyword argument value from an annotation."""
    if ann.params is None:
        return None
    return ann.params.get(key)


def _parse_reinforcer(ann: Annotation) -> ReinforcerAnnotation:
    """Parse @reinforcer annotation into ReinforcerAnnotation."""
    name = _get_positional_str(ann)
    rtype = _get_kwarg(ann, "type")
    backup = _get_kwarg(ann, "backup")
    power = _get_kwarg(ann, "power")
    alpha0 = _get_kwarg(ann, "alpha0")

    backup_ids: tuple[str, ...] = ()
    if isinstance(backup, str):
        backup_ids = (backup,)

    return ReinforcerAnnotation(
        name=name,
        reinforcer_type=rtype if isinstance(rtype, str) and rtype in ("unconditioned", "conditioned", "generalized") else "unconditioned",
        backup_ids=backup_ids,
        innate_power=float(power) if power is not None else 1.0,
        initial_alpha=float(alpha0) if alpha0 is not None else 0.5,
    )


def _parse_sd(ann: Annotation) -> SDAnnotation:
    """Parse @sd annotation into SDAnnotation."""
    name = _get_positional_str(ann)
    component = _get_kwarg(ann, "component")
    return SDAnnotation(
        name=name,
        component=int(component) if component is not None else None,
    )


def _parse_operandum(ann: Annotation) -> OperandumAnnotation:
    """Parse @operandum annotation into OperandumAnnotation."""
    return OperandumAnnotation(name=_get_positional_str(ann))


def _parse_brief(ann: Annotation) -> BriefAnnotation:
    """Parse @brief annotation into BriefAnnotation."""
    name = _get_positional_str(ann)
    duration = _get_kwarg(ann, "duration")
    time_unit = _get_kwarg(ann, "time_unit")
    return BriefAnnotation(
        name=name,
        duration=float(duration) if duration is not None else None,
        time_unit=str(time_unit) if time_unit is not None else None,
    )
