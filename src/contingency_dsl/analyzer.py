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
    AdjustingSchedule,
    AnnotatedSchedule,
    Atomic,
    AversiveSchedule,
    Binding,
    Compound,
    CompoundParam,
    DirectionalCOD,
    IdentifierRef,
    InterlockingSchedule,
    LimitedHold,
    Modifier,
    ParamDecl,
    Program,
    ResponseCostWrapped,
    ScheduleExpr,
    SecondOrder,
    Special,
    TimeoutWrapped,
    TrialBased,
)
from .enums import Combinator, Domain
from .errors import SemanticError


@dataclass
class AnalysisResult:
    """Result of semantic analysis."""

    program: Program
    warnings: list[str]


def analyze(program):
    """Run semantic analysis on a parsed Program or PhaseSequence.

    For ``Program`` inputs, returns a new Program with:

    - All IdentifierRef nodes replaced by their bound values
    - Repeat expanded to Tand
    - Same-combinator nesting flattened (Theorem 2: Associativity)
    - Program-level LH default applied
    - Bindings cleared (no longer needed after expansion)

    For ``PhaseSequence`` inputs, the experiment-layer parser's
    ``parse_warnings`` (e.g. ``ADVANCE_SINGLE_STEP``) are surfaced via
    ``AnalysisResult.warnings``. The input AST is returned unchanged.
    """
    from .experiment import PhaseSequence

    if isinstance(program, PhaseSequence):
        return AnalysisResult(
            program=program,
            warnings=list(program.parse_warnings),
        )

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

    # Step 3b: Apply algebraic simplifications (Theorems 3/4/5: identity,
    # annihilator, commutativity).
    schedule = _simplify_algebra(schedule)

    # Step 4: Apply program-level LH default
    preserved_decls: list[ParamDecl] = []
    if program.param_decls:
        for decl in program.param_decls:
            if decl.name == "LH":
                schedule = _apply_lh_default(schedule, decl.value, decl.time_unit)
            elif decl.name == "RD":
                _validate_rd(decl, warns)
                preserved_decls.append(decl)

    # Step 4b: Validate compound params (COD on Conc only, BO on Mult/Mix only)
    _validate_compound_params(schedule, warns)

    # Step 4c: Validate atomic values (must be positive)
    _validate_atomic_values(schedule)

    # Step 4d: Aversive-schedule diagnostic warnings
    _collect_aversive_warnings(schedule, warns)

    # Step 4e: Lag / SecondOrder / ResponseCost diagnostic warnings
    has_reinforcer_annotation = _has_reinforcer_annotation(
        program.program_annotations, schedule
    )
    _collect_misc_warnings(
        schedule, warns, has_reinforcer=has_reinforcer_annotation
    )

    # Step 4f: Trial-based (MTS / GoNoGo) diagnostic warnings
    has_stimulus_classes = any(
        a.keyword == "stimulus_classes" for a in program.program_annotations
    )
    _collect_trial_based_warnings(
        schedule, warns, has_stimulus_classes=has_stimulus_classes
    )

    # Step 4g: Annotation validators (run on both program_annotations and
    # schedule-attached annotations since the schema routes some keywords
    # to the schedule even when written before it).
    def _run_validators(annotations):
        for ann in annotations:
            if ann.keyword == "trial_mix":
                _validate_trial_mix_annotation(ann)
            elif ann.keyword == "cs":
                _validate_cs_annotation(ann)
            elif ann.keyword == "us":
                _validate_us_annotation(ann)
            elif ann.keyword == "iti":
                _validate_iti_annotation(ann)
            elif ann.keyword == "cs_interval":
                _validate_cs_interval_annotation(ann)

    _run_validators(program.program_annotations)
    # Walk schedule for any AnnotatedSchedule wrappers and run validators.
    def _walk_for_annotations(expr):
        if isinstance(expr, AnnotatedSchedule):
            for ann in expr.annotations:
                if ann.keyword == "trial_mix":
                    _validate_trial_mix_against_schedule(ann, expr.expr)
            _run_validators(expr.annotations)
            _walk_for_annotations(expr.expr)
        elif isinstance(expr, Compound):
            for comp in expr.components:
                _walk_for_annotations(comp)
        elif isinstance(expr, LimitedHold):
            _walk_for_annotations(expr.inner)
        elif isinstance(expr, Modifier) and expr.inner is not None:
            _walk_for_annotations(expr.inner)
        elif isinstance(expr, SecondOrder):
            _walk_for_annotations(expr.overall)
            _walk_for_annotations(expr.unit)
        elif isinstance(expr, TimeoutWrapped):
            _walk_for_annotations(expr.inner)
        elif isinstance(expr, ResponseCostWrapped):
            _walk_for_annotations(expr.inner)
    _walk_for_annotations(schedule)

    # Step 5: Generate warnings
    has_program_cod = any(
        d.name in ("COD", "ChangeoverDelay") for d in program.param_decls
    )
    warns.extend(_collect_warnings(schedule, has_program_cod=has_program_cod))

    return AnalysisResult(
        program=Program(
            param_decls=tuple(preserved_decls),
            bindings=(),
            schedule=schedule,
        ),
        warnings=warns,
    )


def _validate_rd(decl: ParamDecl, warns: list[str]) -> None:
    """Validate RD param_decl: time unit required, non-negative, large delay warning."""
    if decl.time_unit is None:
        raise SemanticError(
            "RD_TIME_UNIT_REQUIRED: RD value must include a time unit (s/ms/min)"
        )
    if decl.value < 0:
        raise SemanticError(
            "RD_NEGATIVE_VALUE: RD value must be non-negative"
        )
    if decl.value > 30:
        # Normalize to seconds for comparison
        value_s = decl.value
        if decl.time_unit == "ms":
            value_s = decl.value / 1000
        elif decl.time_unit == "min":
            value_s = decl.value * 60
        if value_s > 30:
            warns.append(
                "RD_LARGE_DELAY: Reinforcement delay exceeds 30s; "
                "most published delay research uses delays <= 30s (Lattal, 2010)"
            )


_CONC_ONLY_PARAMS = frozenset({"COD", "FRCO"})
_MULT_MIX_ONLY_PARAMS = frozenset({"BO"})


def _collect_aversive_warnings(expr: ScheduleExpr, warns: list[str]) -> None:
    """Emit RSI_EXCEEDS_SSI / ESCAPE_MAX_TOO_SHORT warnings for aversive
    schedules (Sidman, Escape) whose parameters produce degenerate
    experimental arrangements.
    """
    if isinstance(expr, AversiveSchedule):
        if expr.kind == "Sidman":
            ssi = _seconds(expr.params.get("SSI"))
            rsi = _seconds(expr.params.get("RSI"))
            if ssi is not None and rsi is not None and rsi > ssi:
                warns.append(
                    f"RSI_EXCEEDS_SSI: Sidman RSI ({rsi}s) exceeds SSI ({ssi}s); "
                    "responses cannot postpone shocks below the SSI baseline "
                    "(Hineline, 1977)"
                )
        elif expr.kind == "Escape":
            safe = _seconds(expr.params.get("SafeDuration"))
            max_shock = _seconds(expr.params.get("MaxShock"))
            if "MaxShock" not in expr.params:
                warns.append(
                    "MISSING_ESCAPE_MAXSHOCK: Escape without MaxShock leaves "
                    "an unresponsive subject exposed indefinitely "
                    "(constraint §103)"
                )
            if safe is not None and max_shock is not None and max_shock <= safe:
                warns.append(
                    f"ESCAPE_MAX_TOO_SHORT: Escape MaxShock ({max_shock}s) "
                    f"is not greater than SafeDuration ({safe}s); the safety "
                    "cutoff triggers before any safe period can complete"
                )
        return
    if isinstance(expr, Compound):
        for component in expr.components:
            _collect_aversive_warnings(component, warns)
    elif isinstance(expr, LimitedHold):
        _collect_aversive_warnings(expr.inner, warns)
    elif isinstance(expr, Modifier) and expr.inner is not None:
        _collect_aversive_warnings(expr.inner, warns)
    elif isinstance(expr, SecondOrder):
        _collect_aversive_warnings(expr.overall, warns)
        _collect_aversive_warnings(expr.unit, warns)
    elif isinstance(expr, AnnotatedSchedule):
        _collect_aversive_warnings(expr.expr, warns)


_TRIAL_MIX_ROLE_BY_TYPE: dict[str, set[str]] = {
    "peak": {"reinforced", "probe"},
    "reinstatement": {"extinction", "reinstatement"},
    "temporal_bisection": {"short_anchor", "long_anchor", "probe"},
}

_TRIAL_MIX_REQUIRED_ROLES: dict[str, set[str]] = {
    "peak": {"reinforced", "probe"},
    "reinstatement": {"extinction", "reinstatement"},
    "temporal_bisection": {"short_anchor", "long_anchor"},
}


def _annot_seconds(v) -> float | None:
    """Convert a `{value, time_unit}` dict to seconds, else None."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        val = v.get("value")
        unit = v.get("time_unit")
        if not isinstance(val, (int, float)):
            return None
        if unit == "s" or unit is None:
            return float(val)
        if unit == "ms":
            return float(val) / 1000.0
        if unit == "min":
            return float(val) * 60.0
    return None


def _validate_cs_annotation(ann) -> None:
    params = ann.params or {}
    if "label" not in params and ann.positional is None:
        raise SemanticError(
            "CS_LABEL_REQUIRED: @cs requires a 'label' parameter"
        )
    if "duration" in params:
        dur = _annot_seconds(params["duration"])
        if dur is not None and dur <= 0:
            raise SemanticError(
                f"CS_DURATION_NONPOSITIVE: @cs duration must be positive (got {dur}s)"
            )


def _validate_us_annotation(ann) -> None:
    params = ann.params or {}
    if "label" not in params and ann.positional is None:
        raise SemanticError(
            "US_LABEL_REQUIRED: @us requires a 'label' parameter"
        )


def _validate_iti_annotation(ann) -> None:
    params = ann.params or {}
    mean_s = _annot_seconds(params.get("mean"))
    if mean_s is not None and mean_s <= 0:
        raise SemanticError(
            f"ITI_MEAN_NONPOSITIVE: @iti mean must be positive (got {mean_s}s)"
        )
    jitter_s = _annot_seconds(params.get("jitter"))
    if jitter_s is not None and jitter_s < 0:
        raise SemanticError(
            f"ITI_JITTER_NEGATIVE: @iti jitter must be non-negative (got {jitter_s}s)"
        )


def _validate_cs_interval_annotation(ann) -> None:
    params = ann.params or {}
    onset_s = _annot_seconds(params.get("cs_onset"))
    offset_s = _annot_seconds(params.get("cs_offset"))
    if onset_s is not None and onset_s < 0:
        raise SemanticError(
            f"CS_INTERVAL_ONSET_NEGATIVE: @cs_interval cs_onset must be "
            f"non-negative (got {onset_s}s)"
        )
    if (
        onset_s is not None
        and offset_s is not None
        and offset_s <= onset_s
    ):
        raise SemanticError(
            f"CS_INTERVAL_OFFSET_NOT_AFTER_ONSET: @cs_interval cs_offset "
            f"({offset_s}s) must be greater than cs_onset ({onset_s}s)"
        )


def _validate_trial_mix_against_schedule(ann, schedule) -> None:
    """Validate @trial_mix references against its enclosing schedule.

    Constraints (schema/annotations/procedure-trial-structure.schema.json):
    * WRONG_PRIMITIVE: @trial_mix applies to a Compound (Mix / Mult / Conc
      ...) — not to MTS / GoNoGo / other TrialBased primitives.
    * INVALID_REF: component.ref must be a valid 0-based index into the
      Compound's components.
    """
    if isinstance(schedule, TrialBased):
        raise SemanticError(
            f"TRIAL_MIX_WRONG_PRIMITIVE: @trial_mix cannot apply to "
            f"{schedule.trial_type} — use a Compound (Mix/Mult/Conc) "
            "or @testing for discrete-trial primitives"
        )
    if not isinstance(schedule, Compound):
        return
    params = ann.params or {}
    components = params.get("components")
    if not isinstance(components, list):
        return
    n_components = len(schedule.components)
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ref = comp.get("ref")
        if isinstance(ref, int) and ref >= n_components:
            raise SemanticError(
                f"TRIAL_MIX_INVALID_REF: ref={ref} exceeds component "
                f"count ({n_components})"
            )


def _validate_trial_mix_annotation(ann) -> None:
    """Validate a @trial_mix annotation per schema/annotations/
    procedure-trial-structure.schema.json.

    Raises SemanticError for each rule violation. The error message carries
    a canonical code as its prefix (TRIAL_MIX_*) so downstream consumers can
    dispatch on it.
    """
    params = ann.params or {}
    if "type" not in params:
        raise SemanticError(
            "TRIAL_MIX_MISSING_TYPE: @trial_mix requires 'type=\"peak\"' "
            "(or 'reinstatement' / 'temporal_bisection')"
        )
    mix_type = params["type"]
    if not isinstance(mix_type, str) or mix_type not in _TRIAL_MIX_ROLE_BY_TYPE:
        raise SemanticError(
            f"TRIAL_MIX_UNKNOWN_TYPE: '{mix_type}' is not a known @trial_mix "
            "type"
        )
    if "components" not in params:
        raise SemanticError(
            "TRIAL_MIX_MISSING_COMPONENTS: @trial_mix requires a "
            "'components=[...]' array"
        )
    components = params["components"]
    if not isinstance(components, list) or not components:
        raise SemanticError(
            "TRIAL_MIX_MISSING_COMPONENTS: components must be a non-empty array"
        )
    valid_roles = _TRIAL_MIX_ROLE_BY_TYPE[mix_type]
    seen_refs: set = set()
    roles_seen: set[str] = set()
    for comp in components:
        if not isinstance(comp, dict):
            raise SemanticError(
                "TRIAL_MIX_COMPONENT_MALFORMED: each component must be an "
                "object literal"
            )
        if "role" not in comp:
            raise SemanticError(
                "TRIAL_MIX_COMPONENT_MISSING_ROLE: component is missing 'role'"
            )
        role = comp["role"]
        if role not in _TRIAL_MIX_ROLE_BY_TYPE:
            # `role` is valid if it belongs to this type's role set.
            pass
        if role not in valid_roles:
            raise SemanticError(
                f"TRIAL_MIX_UNEXPECTED_ROLE_FOR_TYPE: role '{role}' is not "
                f"valid for type='{mix_type}'"
            )
        roles_seen.add(role)
        if "ref" not in comp:
            raise SemanticError(
                "TRIAL_MIX_COMPONENT_MISSING_REF: component is missing 'ref'"
            )
        ref = comp["ref"]
        if not isinstance(ref, int):
            raise SemanticError(
                "TRIAL_MIX_COMPONENT_INVALID_REF: 'ref' must be an integer"
            )
        if ref < 0:
            raise SemanticError(
                f"TRIAL_MIX_COMPONENT_INVALID_REF: ref={ref} must be >= 0"
            )
        if ref in seen_refs:
            raise SemanticError(
                f"TRIAL_MIX_DUPLICATE_REF: ref={ref} appears in more than "
                "one component"
            )
        seen_refs.add(ref)
        if mix_type == "peak" and role == "probe" and "duration" not in comp:
            raise SemanticError(
                "TRIAL_MIX_PEAK_PROBE_DURATION: peak 'probe' component "
                "requires a 'duration' attribute"
            )
    required = _TRIAL_MIX_REQUIRED_ROLES[mix_type]
    missing = required - roles_seen
    if missing:
        raise SemanticError(
            f"TRIAL_MIX_MISSING_REQUIRED_ROLE: type='{mix_type}' requires "
            f"role(s) {sorted(missing)}"
        )

    if mix_type == "temporal_bisection":
        _validate_temporal_bisection_probe_durations(components)


_TIME_UNIT_TO_SECONDS: dict[str, float] = {
    "ms": 0.001,
    "s": 1.0,
    "min": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
}


def _parse_duration_string(text: str) -> float:
    """Parse `"2s"` / `"500ms"` / `"1.5min"` into seconds.

    Raises ValueError on malformed input.
    """
    if not isinstance(text, str):
        raise ValueError(f"duration must be a string, got {type(text).__name__}")
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty duration string")
    for unit in ("ms", "min", "hr", "h", "s"):
        if stripped.endswith(unit):
            number_part = stripped[: -len(unit)].strip()
            if not number_part:
                raise ValueError(f"missing number in duration '{text}'")
            try:
                value = float(number_part)
            except ValueError as exc:
                raise ValueError(f"invalid number in duration '{text}'") from exc
            return value * _TIME_UNIT_TO_SECONDS[unit]
    raise ValueError(f"duration '{text}' is missing a recognised time unit")


def _component_duration_seconds(comp: dict) -> float | None:
    """Return the component's `duration` attribute converted to seconds, or None."""
    dur = comp.get("duration")
    if dur is None:
        return None
    if isinstance(dur, dict):
        val = dur.get("value")
        unit = dur.get("time_unit")
        if isinstance(val, (int, float)) and isinstance(unit, str) and unit in _TIME_UNIT_TO_SECONDS:
            return float(val) * _TIME_UNIT_TO_SECONDS[unit]
        return None
    if isinstance(dur, (int, float)):
        return float(dur)
    if isinstance(dur, str):
        try:
            return _parse_duration_string(dur)
        except ValueError:
            return None
    return None


def _validate_temporal_bisection_probe_durations(components: list) -> None:
    """Check probe.durations are well-formed and within the anchor range.

    Raises SemanticError with canonical codes:
    * TRIAL_MIX_INVALID_DURATION_LIST — any item in probe.durations fails
      to parse as a time literal.
    * TRIAL_MIX_PROBE_OUT_OF_ANCHOR_RANGE — at least one parsed probe
      duration lies outside [short_anchor.duration, long_anchor.duration].
    """
    short_s: float | None = None
    long_s: float | None = None
    probe: dict | None = None
    for comp in components:
        role = comp.get("role")
        if role == "short_anchor":
            short_s = _component_duration_seconds(comp)
        elif role == "long_anchor":
            long_s = _component_duration_seconds(comp)
        elif role == "probe":
            probe = comp

    if probe is None:
        return

    durations = probe.get("durations")
    if durations is None:
        return
    if not isinstance(durations, list) or not durations:
        raise SemanticError(
            "TRIAL_MIX_INVALID_DURATION_LIST: probe.durations must be a "
            "non-empty list"
        )

    parsed: list[float] = []
    for item in durations:
        try:
            parsed.append(_parse_duration_string(item) if isinstance(item, str)
                          else float(item) if isinstance(item, (int, float))
                          else (_ for _ in ()).throw(ValueError("not a number or string")))
        except ValueError:
            raise SemanticError(
                f"TRIAL_MIX_INVALID_DURATION_LIST: probe.durations item "
                f"{item!r} is not a valid duration literal"
            )

    if short_s is not None and long_s is not None:
        lo, hi = (short_s, long_s) if short_s <= long_s else (long_s, short_s)
        for raw, seconds in zip(durations, parsed):
            if seconds < lo or seconds > hi:
                raise SemanticError(
                    f"TRIAL_MIX_PROBE_OUT_OF_ANCHOR_RANGE: probe duration "
                    f"{raw!r} ({seconds}s) lies outside the anchor range "
                    f"[{lo}s, {hi}s]"
                )


def _has_reinforcer_annotation(
    program_annotations: tuple, schedule: ScheduleExpr
) -> bool:
    """Return True if any `@reinforcer` / alias annotation is reachable from
    the program or any schedule-level wrapper visible in `schedule`.
    """
    for ann in program_annotations:
        if ann.keyword == "reinforcer":
            return True

    def walk(expr: ScheduleExpr) -> bool:
        if isinstance(expr, AnnotatedSchedule):
            for ann in expr.annotations:
                if ann.keyword == "reinforcer":
                    return True
            return walk(expr.expr)
        if isinstance(expr, Compound):
            return any(walk(c) for c in expr.components)
        if isinstance(expr, LimitedHold):
            return walk(expr.inner)
        if isinstance(expr, Modifier) and expr.inner is not None:
            return walk(expr.inner)
        if isinstance(expr, SecondOrder):
            return walk(expr.overall) or walk(expr.unit)
        if isinstance(expr, TimeoutWrapped):
            return walk(expr.inner)
        if isinstance(expr, ResponseCostWrapped):
            return walk(expr.inner)
        return False

    return walk(schedule)


def _collect_misc_warnings(
    expr: ScheduleExpr, warns: list[str], *, has_reinforcer: bool
) -> None:
    """Emit LAG_LARGE_N, MISSING_BRIEF, MISSING_REINFORCER diagnostics."""
    if isinstance(expr, Modifier):
        if expr.modifier == "Lag" and expr.value is not None and expr.value > 50:
            warns.append(
                f"LAG_LARGE_N: Lag n={int(expr.value)} exceeds 50; unusual "
                "for published work"
            )
        if expr.modifier == "Pctl":
            if expr.pctl_rank in (0, 100):
                warns.append(
                    f"PCTL_EXTREME_RANK: rank={expr.pctl_rank} collapses to "
                    "CRF/EXT equivalent"
                )
            if expr.pctl_window is not None:
                if expr.pctl_window < 5:
                    warns.append(
                        f"PCTL_SMALL_WINDOW: window={expr.pctl_window} < 5 "
                        "has poor distributional stability"
                    )
                if expr.pctl_window > 100:
                    warns.append(
                        f"PCTL_LARGE_WINDOW: window={expr.pctl_window} > 100 "
                        "degrades adaptiveness"
                    )
        if expr.inner is not None:
            _collect_misc_warnings(expr.inner, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, InterlockingSchedule):
        if expr.interlock_R0 == 1:
            warns.append(
                "INTERLOCK_TRIVIAL_RATIO: R0=1 reduces Interlock to CRF (FT)"
            )
        if expr.interlock_R0 > 500:
            warns.append(
                f"INTERLOCK_LARGE_RATIO: R0={expr.interlock_R0} > 500 may "
                "produce ratio strain"
            )
        return
    if isinstance(expr, AdjustingSchedule):
        start_v = expr.adj_start.get("value") if isinstance(expr.adj_start, dict) else None
        step_v = expr.adj_step.get("value") if isinstance(expr.adj_step, dict) else None
        mn_v = expr.adj_min.get("value") if isinstance(expr.adj_min, dict) else None
        if expr.adj_target == "ratio" and isinstance(mn_v, (int, float)) and mn_v < 1:
            warns.append(
                f"ADJ_SUBUNIT_RATIO: ratio min ({mn_v}) is < 1; sub-unit "
                "ratio is undefined"
            )
        if expr.adj_target == "delay" and expr.adj_max is None:
            warns.append(
                "ADJ_UNBOUNDED_DELAY: delay target without max bound allows "
                "unbounded drift"
            )
        if (
            expr.adj_target == "delay"
            and expr.adj_min is not None
            and isinstance(expr.adj_min, dict)
            and expr.adj_min.get("value") == 0
        ):
            warns.append(
                "ADJ_ZERO_MIN_DELAY: min=0 with delay target collapses to CRF"
            )
        if (
            isinstance(start_v, (int, float))
            and isinstance(step_v, (int, float))
            and step_v > start_v
        ):
            warns.append(
                f"ADJ_LARGE_STEP: step ({step_v}) exceeds start ({start_v})"
            )
        return
    if isinstance(expr, SecondOrder):
        # Constraint §74 (Kelleher, 1966): SecondOrder without a @brief
        # annotation is procedurally ambiguous. Detect by checking the
        # enclosing AnnotatedSchedule; a bare SecondOrder (no wrapper) is
        # the default missing-brief case.
        warns.append(
            "MISSING_BRIEF: SecondOrder schedule without a @brief annotation "
            "is procedurally ambiguous (constraint §74)"
        )
        _collect_misc_warnings(expr.overall, warns, has_reinforcer=has_reinforcer)
        _collect_misc_warnings(expr.unit, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, TimeoutWrapped):
        if isinstance(expr.inner, Special) and expr.inner.kind == "EXT":
            warns.append(
                "TO_ON_EXT: TO on EXT is semantically vacuous (no "
                "reinforcement schedule to interrupt)"
            )
        _collect_misc_warnings(expr.inner, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, ResponseCostWrapped):
        if not has_reinforcer:
            warns.append(
                "RC_WITHOUT_TOKEN_CONTEXT: ResponseCost without a "
                "@reinforcer annotation leaves the token/point currency "
                "unspecified"
            )
        elif expr.response_cost.unit == "token":
            # If the program-level @reinforcer did not name a unit matching the
            # RC unit the analyzer cannot verify the linkage; emit a softer
            # warning. (For now we treat the presence of @reinforcer as
            # sufficient and skip.)
            pass
        _collect_misc_warnings(expr.inner, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, AnnotatedSchedule):
        # A @brief on the wrapper suppresses MISSING_BRIEF for the inner
        # SecondOrder; detect and recurse with a filtered subtree.
        if isinstance(expr.expr, SecondOrder) and any(
            a.keyword == "brief" for a in expr.annotations
        ):
            _collect_misc_warnings(expr.expr.overall, warns, has_reinforcer=has_reinforcer)
            _collect_misc_warnings(expr.expr.unit, warns, has_reinforcer=has_reinforcer)
            return
        _collect_misc_warnings(expr.expr, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, Compound):
        for c in expr.components:
            _collect_misc_warnings(c, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, LimitedHold):
        _collect_misc_warnings(expr.inner, warns, has_reinforcer=has_reinforcer)
        return
    if isinstance(expr, TimeoutWrapped):
        _collect_misc_warnings(expr.inner, warns, has_reinforcer=has_reinforcer)
        return


def _collect_trial_based_warnings(
    expr: ScheduleExpr, warns: list[str], *, has_stimulus_classes: bool
) -> None:
    """Emit MTS/GoNoGo diagnostic warnings based on parameter patterns."""
    if isinstance(expr, TrialBased):
        p = expr.params
        if expr.trial_type == "GoNoGo" and "limitedHold" in p:
            warns.append(
                "GONOGO_LH_REDUNDANT: GoNoGo already bounds response time "
                "via responseWindow; LH is redundant"
            )
        if expr.trial_type == "MTS":
            mts_type = p.get("mts_type", "arbitrary")
            if mts_type == "identity" and has_stimulus_classes:
                warns.append(
                    "MTS_IDENTITY_WITH_CLASSES: identity MTS uses physical "
                    "identity, not class membership — @stimulus_classes is "
                    "redundant"
                )
            if mts_type == "arbitrary" and not has_stimulus_classes:
                warns.append(
                    "MTS_ARBITRARY_WITHOUT_CLASSES: arbitrary MTS typically "
                    "accompanies @stimulus_classes to define the classes"
                )
            comparisons = p.get("comparisons", 0)
            if comparisons == 2:
                warns.append(
                    "MTS_TWO_COMPARISONS_WEAK: 2 comparisons gives 50% chance "
                    "accuracy — consider >= 3"
                )
            if comparisons > 9:
                warns.append(
                    f"MTS_MANY_COMPARISONS: {comparisons} comparisons is "
                    "unusually many"
                )
            delay_s = _seconds({"value": p.get("delay", 0), "time_unit": p.get("delay_unit", "s")})
            if delay_s is not None and delay_s > 60:
                warns.append(
                    f"MTS_LONG_DELAY: delay {delay_s}s is unusually long"
                )
            correction = p.get("correction")
            if (
                delay_s is not None and delay_s > 0
                and isinstance(correction, dict)
                and correction.get("mode") != "disabled"
            ):
                warns.append(
                    "DMTS_WITH_CORRECTION: DMTS (delay > 0) combined with "
                    "correction confounds retention with acquisition"
                )
            iti_s = _seconds({"value": p.get("ITI", 0), "time_unit": p.get("ITI_unit", "s")})
            if iti_s is not None and iti_s < 1:
                warns.append(
                    f"MTS_SHORT_ITI: ITI {iti_s}s is very short"
                )
            consequence = p.get("consequence")
            if isinstance(consequence, Special) and consequence.kind == "EXT":
                warns.append(
                    "MTS_NO_REINFORCEMENT: consequence=EXT leaves no "
                    "reinforcement signal"
                )
        return
    if isinstance(expr, AnnotatedSchedule):
        # A schedule-level @stimulus_classes on the MTS also counts.
        local_sc = has_stimulus_classes or any(
            a.keyword == "stimulus_classes" for a in expr.annotations
        )
        _collect_trial_based_warnings(expr.expr, warns, has_stimulus_classes=local_sc)
        return
    if isinstance(expr, Compound):
        for c in expr.components:
            _collect_trial_based_warnings(c, warns, has_stimulus_classes=has_stimulus_classes)
        return
    if isinstance(expr, LimitedHold):
        if isinstance(expr.inner, TrialBased):
            if expr.inner.trial_type == "MTS":
                lh_s = _seconds({"value": expr.hold_duration, "time_unit": expr.time_unit or "s"})
                if lh_s is not None and lh_s > 5 * 60:
                    warns.append(
                        f"MTS_LONG_LH: LH {lh_s}s (> 5min) effectively "
                        "removes the time constraint"
                    )
            if expr.inner.trial_type == "GoNoGo":
                warns.append(
                    "GONOGO_LH_REDUNDANT: GoNoGo already bounds response "
                    "time via responseWindow; LH is redundant"
                )
        _collect_trial_based_warnings(expr.inner, warns, has_stimulus_classes=has_stimulus_classes)
        return
    if isinstance(expr, Modifier) and expr.inner is not None:
        _collect_trial_based_warnings(expr.inner, warns, has_stimulus_classes=has_stimulus_classes)
        return
    if isinstance(expr, TimeoutWrapped):
        _collect_trial_based_warnings(expr.inner, warns, has_stimulus_classes=has_stimulus_classes)
        return
    if isinstance(expr, ResponseCostWrapped):
        _collect_trial_based_warnings(expr.inner, warns, has_stimulus_classes=has_stimulus_classes)
        return


def _seconds(param: object) -> float | None:
    """Normalise a `{value, time_unit}` aversive parameter to seconds."""
    if not isinstance(param, dict):
        return None
    v = param.get("value")
    u = param.get("time_unit")
    if not isinstance(v, (int, float)) or not isinstance(u, str):
        return None
    if u == "s":
        return float(v)
    if u == "ms":
        return float(v) / 1000.0
    if u == "min":
        return float(v) * 60.0
    return None


def _simplify_algebra(expr: ScheduleExpr) -> ScheduleExpr:
    """Apply identity / annihilator / commutativity rewrites.

    Rules (from theory.md §2.2):
      R1/R2 — Identity:   Alt(S, EXT) = S, Conj(S, CRF) = S, Chain(S, CRF) = S
      R3/R4 — Annihilator: Conj(S, EXT) = EXT, Alt(S, CRF) = CRF
      Commutativity:       Conc/Alt/Conj components canonicalised by sort key
    """
    if isinstance(expr, Compound):
        # Recurse first so inner simplifications are visible.
        components = tuple(_simplify_algebra(c) for c in expr.components)
        comb = expr.combinator

        def is_ext(c: ScheduleExpr) -> bool:
            return isinstance(c, Special) and c.kind == "EXT"

        def is_crf(c: ScheduleExpr) -> bool:
            return isinstance(c, Special) and c.kind == "CRF"

        # Identity elements (source order preserved — commutativity is
        # verified by the algebra harness via _commutative_canonical, not by
        # sorting in the analyzer itself, so that let-binding expansion
        # fixtures keep their natural component order).
        if comb == Combinator.ALT:
            filtered = tuple(c for c in components if not is_ext(c))
            if any(is_crf(c) for c in filtered):
                return Special(kind="CRF")  # annihilator
            if len(filtered) == 0:
                return Special(kind="EXT")
            if len(filtered) == 1:
                return filtered[0]
            components = filtered
        elif comb == Combinator.CONJ:
            filtered = tuple(c for c in components if not is_crf(c))
            if any(is_ext(c) for c in filtered):
                return Special(kind="EXT")  # annihilator
            if len(filtered) == 0:
                return Special(kind="CRF")
            if len(filtered) == 1:
                return filtered[0]
            components = filtered
        elif comb == Combinator.CHAIN:
            filtered = tuple(c for c in components if not is_crf(c))
            if len(filtered) == 0:
                return Special(kind="CRF")
            if len(filtered) == 1:
                return filtered[0]
            components = filtered

        return Compound(
            combinator=comb,
            components=components,
            params=expr.params,
        )
    if isinstance(expr, LimitedHold):
        return LimitedHold(
            hold_duration=expr.hold_duration,
            inner=_simplify_algebra(expr.inner),
            time_unit=expr.time_unit,
        )
    if isinstance(expr, Modifier) and expr.inner is not None:
        return Modifier(
            modifier=expr.modifier,
            value=expr.value,
            time_unit=expr.time_unit,
            inner=_simplify_algebra(expr.inner),
            pr_step=expr.pr_step,
            pr_start=expr.pr_start,
            pr_increment=expr.pr_increment,
            pr_ratio=expr.pr_ratio,
            pctl_target=expr.pctl_target,
            pctl_rank=expr.pctl_rank,
            pctl_window=expr.pctl_window,
            pctl_dir=expr.pctl_dir,
            length=expr.length,
        )
    if isinstance(expr, AnnotatedSchedule):
        return AnnotatedSchedule(
            expr=_simplify_algebra(expr.expr),
            annotations=expr.annotations,
        )
    return expr


def _sort_commutative(components: tuple[ScheduleExpr, ...]) -> tuple[ScheduleExpr, ...]:
    """Sort commutative combinator components by a stable string key so that
    `Conc(A, B)` and `Conc(B, A)` produce the same post-analysis AST.
    """
    return tuple(sorted(components, key=lambda c: repr(c)))


def _validate_atomic_values(expr: ScheduleExpr) -> None:
    """Recursively check that Atomic / Modifier / LimitedHold values are positive."""
    if isinstance(expr, Atomic):
        if expr.value <= 0:
            raise SemanticError(
                f"ATOMIC_NONPOSITIVE_VALUE: {expr.schedule_type} must have a "
                f"positive value (got {expr.value}); use EXT for extinction"
            )
    elif isinstance(expr, SecondOrder):
        _validate_atomic_values(expr.overall)
        _validate_atomic_values(expr.unit)
    elif isinstance(expr, Compound):
        for component in expr.components:
            _validate_atomic_values(component)
    elif isinstance(expr, LimitedHold):
        if expr.hold_duration <= 0:
            raise SemanticError(
                f"LH_NONPOSITIVE_VALUE: LimitedHold duration must be positive "
                f"(got {expr.hold_duration})"
            )
        _validate_atomic_values(expr.inner)
    elif isinstance(expr, Modifier):
        if expr.modifier in ("DRL", "DRH", "DRO") and expr.value is not None:
            if expr.value <= 0:
                raise SemanticError(
                    f"DR_NONPOSITIVE_VALUE: {expr.modifier} value must be "
                    f"positive (got {expr.value}); use CRF for unconditional "
                    "reinforcement"
                )
        if expr.modifier == "PR" and expr.pr_start is not None:
            if expr.pr_start <= 0:
                raise SemanticError(
                    f"PR_NONPOSITIVE_START: PR start must be positive "
                    f"(got {expr.pr_start})"
                )
        if expr.modifier == "PR" and expr.pr_increment is not None:
            if expr.pr_increment <= 0:
                raise SemanticError(
                    f"PR_NONPOSITIVE_INCREMENT: PR increment must be positive "
                    f"(got {expr.pr_increment})"
                )
        if expr.inner is not None:
            _validate_atomic_values(expr.inner)
    elif isinstance(expr, AnnotatedSchedule):
        _validate_atomic_values(expr.expr)


def _validate_directional_cod(
    cod: DirectionalCOD, n_components: int, warns: list[str]
) -> None:
    """Validate directional COD entries (grammar §50-59)."""
    seen_pairs: set[tuple[int, int]] = set()

    for entry in cod.directional:
        f = entry.from_ref
        t = entry.to_ref

        # §51: index range check
        if isinstance(f, int) and (f < 1 or f > n_components):
            raise SemanticError(
                f"DIRECTIONAL_INDEX_OUT_OF_RANGE: from={f} "
                f"but Conc has {n_components} components"
            )
        if isinstance(t, int) and (t < 1 or t > n_components):
            raise SemanticError(
                f"DIRECTIONAL_INDEX_OUT_OF_RANGE: to={t} "
                f"but Conc has {n_components} components"
            )

        # §53: self-reference
        if f == t:
            raise SemanticError(
                f"DIRECTIONAL_SELF_REFERENCE: COD({f}->{t}) — "
                "a component cannot have a COD for switching to itself"
            )

        # §54: duplicate direction pair
        pair = (f, t) if isinstance(f, int) and isinstance(t, int) else (f, t)
        if pair in seen_pairs:
            raise SemanticError(
                f"DUPLICATE_DIRECTIONAL_KW: COD({f}->{t}) specified twice"
            )
        seen_pairs.add(pair)

    # §58: all directions identical → redundant
    if len(cod.directional) >= 2 and cod.base is None:
        values = [(e.value, e.time_unit) for e in cod.directional]
        if len(set(values)) == 1:
            # Check if all n*(n-1) directions are covered
            n_possible = n_components * (n_components - 1)
            if len(cod.directional) == n_possible:
                warns.append(
                    "REDUNDANT_DIRECTIONAL_COD: all directional COD values "
                    "are identical — consider using scalar COD instead"
                )


def _validate_compound_params(expr: ScheduleExpr, warns: list[str]) -> None:
    """Validate keyword args on compound schedules (grammar §8, §13, §50-59)."""
    match expr:
        case Compound(combinator=comb, components=components, params=params):
            if params:
                for k, v in params.items():
                    if k in _CONC_ONLY_PARAMS and comb != Combinator.CONC:
                        raise SemanticError(
                            f"INVALID_KEYWORD_ARG: {k} is valid on Conc only, "
                            f"not {comb.value}"
                        )
                    if k in _MULT_MIX_ONLY_PARAMS and comb not in (
                        Combinator.MULT, Combinator.MIX,
                    ):
                        raise SemanticError(
                            f"INVALID_KEYWORD_ARG: {k} is valid on Mult/Mix only, "
                            f"not {comb.value}"
                        )
                    # Directional form validation (§50-59)
                    if isinstance(v, DirectionalCOD):
                        if k != "COD":
                            raise SemanticError(
                                f"INVALID_DIRECTIONAL_KW: directional form is "
                                f"valid for COD only, not {k}"
                            )
                        _validate_directional_cod(v, len(components), warns)
                    elif isinstance(v, CompoundParam):
                        # COD=0 is explicitly valid (disables COD, per §7);
                        # FRCO=0 / BO=0 are invalid (use omission instead).
                        if v.value <= 0 and k not in ("COD",):
                            raise SemanticError(
                                f"{k}_NONPOSITIVE: {k}={v.value} must be positive"
                            )
                        if v.value < 0 and k == "COD":
                            raise SemanticError(
                                f"COD_NEGATIVE: COD={v.value} must be non-negative"
                            )
            # §35-36: Overlay requires exactly 2 components, no keyword args
            if comb == Combinator.OVERLAY:
                if len(components) != 2:
                    raise SemanticError(
                        f"OVERLAY_REQUIRES_TWO: Overlay requires exactly 2 "
                        f"components (baseline + punisher), got {len(components)}"
                    )
                if params and any(k != "target" for k in params):
                    raise SemanticError(
                        "INVALID_KEYWORD_ARG: Overlay accepts only 'target' "
                        "as a keyword argument"
                    )
                if params and params.get("target") == "changeover":
                    baseline = components[0]
                    if not (
                        isinstance(baseline, Compound)
                        and baseline.combinator == Combinator.CONC
                    ):
                        raise SemanticError(
                            "OVERLAY_TARGET_NON_CONC: target=changeover "
                            "requires the baseline to be a Conc schedule"
                        )
            # PUNISH index range check on Conc
            if comb == Combinator.CONC and params:
                punish = params.get("PUNISH")
                if isinstance(punish, dict):
                    n = len(components)
                    for entry in punish.get("directional", []):
                        for key in ("from", "to"):
                            ref = entry.get(key)
                            if isinstance(ref, int) and (ref < 1 or ref > n):
                                raise SemanticError(
                                    f"PUNISH_INDEX_OUT_OF_RANGE: {key}={ref} "
                                    f"but Conc has {n} components"
                                )
                    for entry in punish.get("component", []):
                        ref = entry.get("component")
                        if isinstance(ref, int) and (ref < 1 or ref > n):
                            raise SemanticError(
                                f"PUNISH_INDEX_OUT_OF_RANGE: component={ref} "
                                f"but Conc has {n} components"
                            )
            # §39: Interpolate requires exactly 2 components and `count`.
            if comb == Combinator.INTERPOLATE:
                if len(components) != 2:
                    raise SemanticError(
                        f"INTERPOLATE_REQUIRES_TWO: Interpolate requires exactly "
                        f"2 components (baseline + insertion), got {len(components)}"
                    )
                if not params or "count" not in params:
                    raise SemanticError(
                        "MISSING_INTERPOLATE_COUNT: Interpolate requires a "
                        "'count' keyword argument"
                    )
                count_param = params.get("count")
                if isinstance(count_param, CompoundParam):
                    if count_param.time_unit is not None:
                        raise SemanticError(
                            "INTERPOLATE_COUNT_WITH_TIME_UNIT: 'count' must be "
                            "dimensionless"
                        )
                onset_param = params.get("onset")
                if isinstance(onset_param, CompoundParam):
                    if onset_param.time_unit is None:
                        raise SemanticError(
                            "INTERPOLATE_ONSET_MISSING_TIME_UNIT: 'onset' "
                            "requires a time unit"
                        )
                if onset_param is None:
                    warns.append(
                        "MISSING_INTERPOLATE_ONSET: Interpolate without onset "
                        "is procedurally ambiguous (constraint §39)"
                    )
            for comp in components:
                _validate_compound_params(comp, warns)

        case LimitedHold(inner=inner):
            _validate_compound_params(inner, warns)

        case Modifier(inner=inner) if inner is not None:
            _validate_compound_params(inner, warns)

        case AnnotatedSchedule(expr=inner):
            _validate_compound_params(inner, warns)


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

        case Compound(combinator=comb, components=components, params=params):
            new_components = []
            for comp in components:
                new_comp, comp_refs = _substitute(comp, env)
                new_components.append(new_comp)
                refs.update(comp_refs)
            return Compound(combinator=comb, components=tuple(new_components), params=params), refs

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

        case SecondOrder(overall=overall, unit=unit):
            new_overall, over_refs = _substitute(overall, env)
            new_unit, unit_refs = _substitute(unit, env)
            refs.update(over_refs)
            refs.update(unit_refs)
            # Reject non-Atomic after substitution (Issue #33 pre-expansion
            # allows IdentifierRef in either slot but the resolved form
            # must be a parametric Atomic).
            if not isinstance(new_overall, Atomic):
                raise SemanticError(
                    f"SECOND_ORDER_OVERALL_NOT_ATOMIC: SecondOrder overall "
                    f"must resolve to a parametric Atomic "
                    f"(got {type(new_overall).__name__})"
                )
            if not isinstance(new_unit, Atomic):
                raise SemanticError(
                    f"SECOND_ORDER_UNIT_NOT_ATOMIC: SecondOrder unit must "
                    f"resolve to a parametric Atomic "
                    f"(got {type(new_unit).__name__})"
                )
            return SecondOrder(overall=new_overall, unit=new_unit), refs

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

        case Compound(combinator=comb, components=components, params=params):
            return Compound(
                combinator=comb,
                components=tuple(_expand_repeats(c) for c in components),
                params=params,
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
        case Compound(combinator=comb, components=components, params=params):
            flat: list[ScheduleExpr] = []
            for child in components:
                fc = _flatten_associative(child)
                if isinstance(fc, Compound) and fc.combinator == comb and not fc.params:
                    flat.extend(fc.components)
                else:
                    flat.append(fc)
            return Compound(combinator=comb, components=tuple(flat), params=params)

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

        case Compound(combinator=comb, components=components, params=params):
            return Compound(
                combinator=comb,
                components=tuple(
                    _apply_lh_default(c, hold_duration, time_unit) for c in components
                ),
                params=params,
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
                    f"VACUOUS_LH_RATIO: LH on ratio schedule ({st}) is "
                    "vacuous — ratio schedules are satisfied on the response "
                    "itself"
                )
            warns.extend(
                _collect_warnings(expr.inner, has_program_cod=has_program_cod)
            )

        case Compound(combinator=Combinator.CONC, params=params):
            has_expr_cod = params is not None and "COD" in params
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

        case Modifier(modifier=mod_name, time_unit=tunit, inner=inner):
            # Differential-reinforcement modifiers (DRL, DRH, DRO) carry a
            # time value; without an explicit unit (s/ms/min) the procedural
            # interpretation is ambiguous.
            if mod_name in ("DRL", "DRH", "DRO") and tunit is None:
                warns.append(
                    f"MISSING_TIME_UNIT: {mod_name} without explicit time unit — "
                    "consider specifying s/ms/min for procedural clarity"
                )
            if inner is not None:
                warns.extend(
                    _collect_warnings(inner, has_program_cod=has_program_cod)
                )

        case AnnotatedSchedule(expr=inner):
            warns.extend(
                _collect_warnings(inner, has_program_cod=has_program_cod)
            )

    return warns
