"""Semantic analyzer for contingency-dsl.

Post-parse transformations:
1. Let-binding expansion (single-pass substitution)
2. Repeat expansion to Tand
3. Associative flattening (Theorem 2)
4. Program-level LH default application
5. Warning generation
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from .ast import (
    AnnotatedSchedule,
    Atomic,
    Binding,
    Compound,
    IdentifierRef,
    LimitedHold,
    Modifier,
    ParamDecl,
    Program,
    ScheduleExpr,
    SecondOrder,
    Special,
)
from .enums import Combinator, Domain
from .errors import SemanticError


@dataclass
class AnalysisResult:
    """Result of semantic analysis."""

    program: Program
    warnings: list[str]


def analyze(program: Program) -> AnalysisResult:
    """Run semantic analysis on a parsed Program.

    Returns a new Program with:
    - All IdentifierRef nodes replaced by their bound values
    - Repeat expanded to Tand
    - Same-combinator nesting flattened (Theorem 2: Associativity)
    - Program-level LH default applied
    - Bindings cleared (no longer needed after expansion)
    """
    warns: list[str] = []

    # Step 1: Expand let bindings
    schedule, used_names = _expand_bindings(program.bindings, program.schedule)

    # Step 1b: Warn about unused bindings
    for binding in program.bindings:
        if binding.name not in used_names:
            warns.append(f"unused binding '{binding.name}'")

    # Step 2: Expand Repeat -> Tand
    schedule = _expand_repeats(schedule)

    # Step 3: Flatten same-combinator nesting (Theorem 2: Associativity)
    schedule = _flatten_associative(schedule)

    # Step 4: Apply program-level LH default
    if program.param_decls:
        for decl in program.param_decls:
            if decl.name == "LH":
                schedule = _apply_lh_default(schedule, decl.value, decl.time_unit)

    # Step 5: Generate warnings
    has_program_cod = any(
        d.name in ("COD", "ChangeoverDelay") for d in program.param_decls
    )
    warns.extend(_collect_warnings(schedule, has_program_cod=has_program_cod))

    return AnalysisResult(
        program=Program(
            param_decls=(),
            bindings=(),
            schedule=schedule,
        ),
        warnings=warns,
    )


def _expand_bindings(
    bindings: tuple[Binding, ...],
    schedule: ScheduleExpr,
) -> tuple[ScheduleExpr, set[str]]:
    """Expand let bindings via single-pass substitution.

    Returns the expanded schedule and the set of binding names that were used.
    """
    env: dict[str, ScheduleExpr] = {}
    defined_names: set[str] = set()
    used_names: set[str] = set()

    for binding in bindings:
        # Check shadowing
        if binding.name in defined_names:
            raise SemanticError(f"duplicate binding '{binding.name}'")
        defined_names.add(binding.name)

        # Expand the binding's value (may reference earlier bindings)
        expanded_value, refs = _substitute(binding.value, env)
        used_names.update(refs)
        env[binding.name] = expanded_value

    # Expand the main schedule
    expanded_schedule, refs = _substitute(schedule, env)
    used_names.update(refs)

    return expanded_schedule, used_names


def _substitute(
    expr: ScheduleExpr,
    env: dict[str, ScheduleExpr],
) -> tuple[ScheduleExpr, set[str]]:
    """Substitute IdentifierRef nodes with their bound values."""
    refs: set[str] = set()

    match expr:
        case IdentifierRef(name=name):
            if name not in env:
                raise SemanticError(f"undefined identifier '{name}'")
            refs.add(name)
            return env[name], refs

        case Compound(combinator=comb, components=components):
            new_components = []
            for comp in components:
                new_comp, comp_refs = _substitute(comp, env)
                new_components.append(new_comp)
                refs.update(comp_refs)
            return Compound(combinator=comb, components=tuple(new_components)), refs

        case LimitedHold(hold_duration=dur, inner=inner, time_unit=unit):
            new_inner, inner_refs = _substitute(inner, env)
            refs.update(inner_refs)
            return LimitedHold(hold_duration=dur, inner=new_inner, time_unit=unit), refs

        case Modifier(modifier=mod, inner=inner) if inner is not None:
            new_inner, inner_refs = _substitute(inner, env)
            refs.update(inner_refs)
            return Modifier(
                modifier=expr.modifier,
                value=expr.value,
                time_unit=expr.time_unit,
                inner=new_inner,
                pr_step=expr.pr_step,
                pr_start=expr.pr_start,
                pr_increment=expr.pr_increment,
            ), refs

        case SecondOrder():
            return expr, refs

        case AnnotatedSchedule(expr=inner, annotations=anns):
            new_inner, inner_refs = _substitute(inner, env)
            refs.update(inner_refs)
            return AnnotatedSchedule(expr=new_inner, annotations=anns), refs

        case Atomic() | Special() | Modifier():
            return expr, refs

        case _:
            return expr, refs


def _expand_repeats(expr: ScheduleExpr) -> ScheduleExpr:
    """Expand Repeat(n, S) -> Tand(S, ..., S) [n copies]."""
    match expr:
        case Modifier(modifier="Repeat", value=count, inner=inner) if inner is not None and count is not None:
            n = int(count)
            if n <= 0:
                raise SemanticError(f"Repeat count must be positive, got {n}")
            expanded_inner = _expand_repeats(inner)
            if n == 1:
                return expanded_inner  # Identity: Repeat(1, S) ≡ S
            return Compound(
                combinator=Combinator.TAND,
                components=tuple(expanded_inner for _ in range(n)),
            )

        case Compound(combinator=comb, components=components):
            return Compound(
                combinator=comb,
                components=tuple(_expand_repeats(c) for c in components),
            )

        case LimitedHold(hold_duration=dur, inner=inner, time_unit=unit):
            return LimitedHold(
                hold_duration=dur,
                inner=_expand_repeats(inner),
                time_unit=unit,
            )

        case Modifier(inner=inner) if inner is not None:
            return Modifier(
                modifier=expr.modifier,
                value=expr.value,
                time_unit=expr.time_unit,
                inner=_expand_repeats(inner),
                pr_step=expr.pr_step,
                pr_start=expr.pr_start,
                pr_increment=expr.pr_increment,
            )

        case AnnotatedSchedule(expr=inner, annotations=anns):
            return AnnotatedSchedule(expr=_expand_repeats(inner), annotations=anns)

        case _:
            return expr


def _flatten_associative(expr: ScheduleExpr) -> ScheduleExpr:
    """Flatten nested same-combinator Compound nodes (Theorem 2: Associativity).

    Tand(A, Tand(B, C)) -> Tand(A, B, C) for all seven combinators.
    """
    match expr:
        case Compound(combinator=comb, components=components):
            flat: list[ScheduleExpr] = []
            for child in components:
                fc = _flatten_associative(child)
                if isinstance(fc, Compound) and fc.combinator == comb:
                    flat.extend(fc.components)
                else:
                    flat.append(fc)
            return Compound(combinator=comb, components=tuple(flat))

        case LimitedHold(hold_duration=dur, inner=inner, time_unit=unit):
            return LimitedHold(
                hold_duration=dur,
                inner=_flatten_associative(inner),
                time_unit=unit,
            )

        case Modifier(inner=inner) if inner is not None:
            return Modifier(
                modifier=expr.modifier,
                value=expr.value,
                time_unit=expr.time_unit,
                inner=_flatten_associative(inner),
                pr_step=expr.pr_step,
                pr_start=expr.pr_start,
                pr_increment=expr.pr_increment,
            )

        case AnnotatedSchedule(expr=inner, annotations=anns):
            return AnnotatedSchedule(
                expr=_flatten_associative(inner), annotations=anns
            )

        case _:
            return expr


def _apply_lh_default(
    expr: ScheduleExpr,
    hold_duration: float,
    time_unit: str | None,
) -> ScheduleExpr:
    """Apply program-level LH default to all leaf base_schedules."""
    match expr:
        case LimitedHold():
            # Already has explicit LH; don't override
            return expr

        case Compound(combinator=comb, components=components):
            return Compound(
                combinator=comb,
                components=tuple(
                    _apply_lh_default(c, hold_duration, time_unit) for c in components
                ),
            )

        case AnnotatedSchedule(expr=inner, annotations=anns):
            return AnnotatedSchedule(
                expr=_apply_lh_default(inner, hold_duration, time_unit),
                annotations=anns,
            )

        case Atomic() | Special() | Modifier() | SecondOrder():
            return LimitedHold(hold_duration=hold_duration, inner=expr, time_unit=time_unit)

        case _:
            return expr


def _collect_warnings(
    expr: ScheduleExpr, *, has_program_cod: bool = False
) -> list[str]:
    """Collect semantic warnings from the AST."""
    warns: list[str] = []

    match expr:
        case Atomic(schedule_type=st, time_unit=unit):
            if st.domain in (Domain.INTERVAL, Domain.TIME) and unit is None:
                warns.append(
                    f"MISSING_TIME_UNIT: {st} without explicit time unit — "
                    "consider specifying s/ms/min for procedural clarity"
                )

        case LimitedHold(inner=Atomic(schedule_type=st)):
            if st.domain.value == "R":
                warns.append(
                    f"LH on ratio schedule ({st}) is vacuous — "
                    "ratio schedules are satisfied on the response itself"
                )
            warns.extend(
                _collect_warnings(expr.inner, has_program_cod=has_program_cod)
            )

        case Compound(combinator=Combinator.CONC):
            has_expr_cod = (
                getattr(expr, "params", None) and "COD" in expr.params
            )
            if not has_expr_cod and not has_program_cod:
                warns.append(
                    "MISSING_COD: Conc without COD specification — "
                    "consider adding COD for procedural completeness "
                    "(Herrnstein, 1961)"
                )
            for comp in expr.components:
                warns.extend(
                    _collect_warnings(comp, has_program_cod=has_program_cod)
                )

        case Compound(components=components):
            for comp in components:
                warns.extend(
                    _collect_warnings(comp, has_program_cod=has_program_cod)
                )

        case LimitedHold(inner=inner):
            warns.extend(
                _collect_warnings(inner, has_program_cod=has_program_cod)
            )

        case Modifier(inner=inner) if inner is not None:
            warns.extend(
                _collect_warnings(inner, has_program_cod=has_program_cod)
            )

        case AnnotatedSchedule(expr=inner):
            warns.extend(
                _collect_warnings(inner, has_program_cod=has_program_cod)
            )

    return warns
