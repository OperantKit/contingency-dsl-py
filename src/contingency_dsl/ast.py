"""Abstract Syntax Tree nodes for contingency-dsl.

All nodes are frozen dataclasses (immutable value types).
The AST is language-independent; it mirrors ast-schema.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from .enums import Combinator, Distribution, Domain


@dataclass(frozen=True)
class ScheduleType:
    """2D type: Distribution x Domain."""

    distribution: Distribution
    domain: Domain

    def __str__(self) -> str:
        return f"{self.distribution.value}{self.domain.value}"


# --- Schedule expression nodes ---


@dataclass(frozen=True)
class Atomic:
    """Parametric atomic schedule: dist x domain with a numeric value.

    Examples: FR5, VI60s, RT20ms
    """

    schedule_type: ScheduleType
    value: float
    time_unit: str | None = None  # "s", "ms", "min", or None

    @property
    def dist(self) -> Distribution:
        """Distribution component of the schedule type (FIXED / VARIABLE / RANDOM)."""
        return self.schedule_type.distribution

    @property
    def domain(self) -> Domain:
        """Domain component of the schedule type (RATIO / INTERVAL / TIME)."""
        return self.schedule_type.domain


@dataclass(frozen=True)
class Special:
    """Boundary schedules: EXT (zero element) or CRF (identity = FR1)."""

    kind: str  # "EXT" | "CRF"


@dataclass(frozen=True)
class CompoundParam:
    """A scalar keyword parameter on a compound schedule (COD, FRCO, BO)."""

    value: float
    time_unit: str | None = None  # None for dimensionless (e.g., FRCO)


@dataclass(frozen=True)
class DirectionalEntry:
    """A single direction-specific override: COD(from->to)=value.

    from_ref/to_ref are int (1-indexed) when parsed from numeric indices,
    or str when parsed from identifiers (resolved to int by the analyzer).
    """

    from_ref: int | str  # 1-indexed int, or identifier name (pre-resolution)
    to_ref: int | str  # 1-indexed int, or identifier name (pre-resolution)
    value: float
    time_unit: str | None = None


@dataclass(frozen=True)
class DirectionalCOD:
    """Directional COD: optional base + direction-specific overrides.

    Pliskoff (1971); Williams & Bell (1999).
    """

    base: CompoundParam | None = None
    directional: tuple[DirectionalEntry, ...] = ()


@dataclass(frozen=True)
class PunishParam:
    """PUNISH(...)=<schedule> keyword value on Conc.

    Carries a pre-built JSON-shaped payload so that the three punishment
    forms (directional / changeover / component) share the same wrapper
    without dataclass-per-variant proliferation. See
    conformance/operant/compound.json for canonical shapes.
    """

    payload: tuple  # frozen key-value pairs; serialised via dict(payload)


# Union for compound schedule parameter values
CombinatorParamValue = CompoundParam | DirectionalCOD | PunishParam


@dataclass(frozen=True)
class Compound:
    """Compound schedule: combinator applied to 2+ sub-schedules."""

    combinator: Combinator
    components: tuple[ScheduleExpr, ...]
    params: dict[str, CombinatorParamValue] | None = None  # COD, FRCO, BO


@dataclass(frozen=True)
class Modifier:
    """Modifier schedule: DR, PR, Repeat, or Pctl.

    - DR (DRL/DRH/DRO): modifier + value + optional time_unit
    - PR: modifier + pr_step + optional pr_start/pr_increment
    - Repeat: modifier + value (count) + inner schedule
    - Pctl (percentile-shaped schedules, Platt 1973; Galbicka 1994):
      modifier + pctl_target + pctl_rank + window + dir
    """

    modifier: str  # "DRL" | "DRH" | "DRO" | "PR" | "Repeat" | "Pctl"
    value: float | None = None
    time_unit: str | None = None
    inner: ScheduleExpr | None = None  # for Repeat
    pr_step: str | None = None  # "hodos" | "exponential" | "linear" | "geometric"
    pr_start: float | None = None
    pr_increment: float | None = None
    pr_ratio: float | None = None  # geometric multiplier
    pctl_target: str | None = None  # force, latency, duration, IRT, rate, location
    pctl_rank: int | None = None  # 0..100
    pctl_window: int | None = None  # sample count for percentile window
    pctl_dir: str | None = None  # "below" | "above"
    length: int | None = None  # Lag sequence length (Page & Neuringer, 1985)


@dataclass(frozen=True)
class LimitedHold:
    """Temporal availability window.

    FI30 LH10 = FI 30s with 10s hold.
    """

    hold_duration: float
    inner: ScheduleExpr
    time_unit: str | None = None


@dataclass(frozen=True)
class SecondOrder:
    """Second-order schedule.

    FR5(FI30) = 5 completions of FI30 produce reinforcement.
    Overall must be Atomic (no EXT/CRF). Unit must be simple.
    """

    overall: Atomic
    unit: Atomic


@dataclass(frozen=True)
class Timeout:
    """Per-schedule timeout parameters (Leitenberg, 1965).

    Flattened by the serializer onto the enclosing leaf node's `timeout`
    property rather than materialising as a wrapper in the output AST.
    """

    duration: float
    duration_unit: str | None = None
    reset_on_response: bool = False


@dataclass(frozen=True)
class TimeoutWrapped:
    """AST wrapper that carries a postfix `TO(...)` on an inner schedule."""

    inner: "ScheduleExpr"
    timeout: Timeout


@dataclass(frozen=True)
class ResponseCost:
    """Response-cost parameters (Weiner, 1962; Hackenberg, 2009).

    Flattened by the serializer onto the enclosing leaf schedule's
    `responseCost` property. Default unit is ``"token"`` when unspecified.
    """

    amount: float
    unit: str = "token"


@dataclass(frozen=True)
class ResponseCostWrapped:
    """AST wrapper that carries a postfix `ResponseCost(...)` on an inner schedule."""

    inner: "ScheduleExpr"
    response_cost: ResponseCost


@dataclass(frozen=True)
class AdjustingSchedule:
    """Adjusting schedule (Mazur, 1987 style): the adjusted parameter moves
    up or down after each reinforcer depending on the subject's choices.

    ``adj_target`` is one of ``"delay"`` / ``"ratio"`` / ``"amount"`` /
    ``"interval"``. ``adj_start``, ``adj_step``, ``adj_min``, ``adj_max`` are
    dict payloads of shape ``{"value": <number>, "time_unit": <unit or None>}``.
    """

    adj_target: str
    adj_start: dict
    adj_step: dict
    adj_min: dict | None = None
    adj_max: dict | None = None


@dataclass(frozen=True)
class InterlockingSchedule:
    """Interlocking schedule (Ferster & Skinner, 1957): a fixed-ratio
    requirement ``R0`` decays linearly over time ``T``.
    """

    interlock_R0: int
    interlock_T: dict  # {"value": X, "time_unit": Y}


@dataclass(frozen=True)
class TrialBased:
    """Trial-based schedule primitive (MTS, GoNoGo, ...).

    `params` is a dict keyed by the canonical parameter name. Values may be
    primitives (int/float/str), ``{value, time_unit}`` dicts for temporal
    parameters, or nested `ScheduleExpr` instances for `consequence` /
    `incorrect` / `falseAlarm` slots.
    """

    trial_type: str  # "MTS" | "GoNoGo"
    params: dict


@dataclass(frozen=True)
class AversiveSchedule:
    """Parameterized aversive schedule: Sidman, DiscrimAv, or Escape.

    `params` is a dict keyed by the canonical parameter name. Values are
    either a `CompoundParam`-like dict (`{value, time_unit}`) for temporal
    parameters or a plain string (e.g. `mode="escape"`).
    """

    kind: str  # "Sidman" | "DiscrimAv" | "Escape"
    params: dict  # canonical-named parameter map


@dataclass(frozen=True)
class IdentifierRef:
    """Reference to a let-bound name.

    Present only in pre-expansion AST; removed after semantic analysis.
    """

    name: str


# Union type for all schedule expressions (without annotations)
ScheduleExpr = Union[Atomic, Special, Compound, Modifier, LimitedHold, SecondOrder, IdentifierRef, AversiveSchedule, TimeoutWrapped, ResponseCostWrapped, TrialBased, AdjustingSchedule, InterlockingSchedule]


# --- Annotation nodes (extension mechanism, §4.7) ---


@dataclass(frozen=True)
class AnnotationArg:
    """A single annotation argument: positional string or keyword=value pair.

    Positional: AnnotationArg(value="food")
    Keyword:    AnnotationArg(value="conditioned", key="type")
    Numeric:    AnnotationArg(value=0.3, key="alpha0")
    """

    value: str | float
    key: str | None = None


@dataclass(frozen=True)
class Annotation:
    """A single @-prefixed annotation on a schedule expression or program.

    Example: @reinforcer("food", type="conditioned", alpha0=0.3)
    Example: @session_end(rule="first", time=60min, reinforcers=60)

    When the source uses an aliased keyword (e.g. `@punisher` for the
    canonical `@reinforcer`, or `@hw` for `@hardware`), ``keyword`` holds the
    canonical name and ``label`` preserves the original source spelling for
    pragmatic reporting. Otherwise ``label`` is None.
    """

    keyword: str  # canonical, e.g. "reinforcer", "sd", "session_end"
    positional: str | float | int | None = None  # first unnamed arg
    params: dict | None = None  # named key=value pairs
    label: str | None = None  # original alias, if an alias was used


@dataclass(frozen=True)
class AnnotatedSchedule:
    """A schedule expression with one or more annotations.

    Wraps any ScheduleExpr (including LimitedHold).
    Annotations are postfix: FR5 @reinforcer("food") @sd("light")
    """

    expr: ScheduleExpr
    annotations: tuple[Annotation, ...]


# Extended union that includes annotated schedules
AnnotatedScheduleExpr = Union[ScheduleExpr, AnnotatedSchedule]


# --- Top-level program nodes ---


@dataclass(frozen=True)
class ParamDecl:
    """Program-level parameter declaration (e.g., LH = 10s)."""

    name: str  # "LH"
    value: float
    time_unit: str | None = None


@dataclass(frozen=True)
class Binding:
    """Let binding: let <name> = <schedule>."""

    name: str
    value: ScheduleExpr


@dataclass(frozen=True)
class Program:
    """Top-level AST node: program_annotations + param_decls + bindings + schedule."""

    program_annotations: tuple[Annotation, ...] = ()
    param_decls: tuple[ParamDecl, ...] = ()
    bindings: tuple[Binding, ...] = ()
    schedule: ScheduleExpr = field(default_factory=lambda: Special("EXT"))
