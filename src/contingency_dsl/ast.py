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
        return self.schedule_type.distribution

    @property
    def domain(self) -> Domain:
        return self.schedule_type.domain


@dataclass(frozen=True)
class Special:
    """Boundary schedules: EXT (zero element) or CRF (identity = FR1)."""

    kind: str  # "EXT" | "CRF"


@dataclass(frozen=True)
class CompoundParam:
    """A keyword parameter on a compound schedule (COD, FRCO, BO)."""

    value: float
    time_unit: str | None = None  # None for dimensionless (e.g., FRCO)


@dataclass(frozen=True)
class Compound:
    """Compound schedule: combinator applied to 2+ sub-schedules."""

    combinator: Combinator
    components: tuple[ScheduleExpr, ...]
    params: dict[str, CompoundParam] | None = None  # COD, FRCO, BO


@dataclass(frozen=True)
class Modifier:
    """Modifier schedule: DR, PR, or Repeat.

    - DR (DRL/DRH/DRO): modifier + value + optional time_unit
    - PR: modifier + pr_step + optional pr_start/pr_increment
    - Repeat: modifier + value (count) + inner schedule
    """

    modifier: str  # "DRL" | "DRH" | "DRO" | "PR" | "Repeat"
    value: float | None = None
    time_unit: str | None = None
    inner: ScheduleExpr | None = None  # for Repeat
    pr_step: str | None = None  # "hodos" | "exponential" | "linear"
    pr_start: float | None = None
    pr_increment: float | None = None


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
    Overall must be Atomic (no EXT/CRF). Unit must be simple (v1.0).
    """

    overall: Atomic
    unit: Atomic


@dataclass(frozen=True)
class IdentifierRef:
    """Reference to a let-bound name.

    Present only in pre-expansion AST; removed after semantic analysis.
    """

    name: str


# Union type for all schedule expressions (without annotations)
ScheduleExpr = Union[Atomic, Special, Compound, Modifier, LimitedHold, SecondOrder, IdentifierRef]


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
    """A single @-prefixed annotation on a schedule expression.

    Example: @reinforcer("food", type="conditioned", alpha0=0.3)
    """

    name: str  # e.g. "reinforcer", "sd", "operandum", "brief"
    args: tuple[AnnotationArg, ...] = ()


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
    """Top-level AST node: param_decls + bindings + schedule."""

    param_decls: tuple[ParamDecl, ...] = ()
    bindings: tuple[Binding, ...] = ()
    schedule: ScheduleExpr = field(default_factory=lambda: Special("EXT"))
