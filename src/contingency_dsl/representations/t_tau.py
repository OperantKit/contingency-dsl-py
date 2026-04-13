"""T-τ Representation — Bidirectional conversion with the 3×3 lattice.

The T-τ system (Schoenfeld & Cole, 1972) parameterizes time-dependent
reinforcement schedules as recurring cycles of length T seconds, within
which a window of τ seconds permits reinforcement.

Conversion domain:
    - Interval (FI, VI, RI) and Time (FT, VT, RT) schedules are convertible.
    - Ratio (FR, VR, RR) schedules are outside the T-tau domain (type error).

See contingency-dsl/representations/t-tau/README.md for the formal specification.

References
----------
Schoenfeld, W. N., & Cole, B. K. (1972). Stimulus schedules: The t-τ systems.
    Harper & Row.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ast import Atomic, LimitedHold, ScheduleExpr, ScheduleType
from ..enums import Distribution, Domain


class RatioScheduleError(TypeError):
    """Raised when attempting to convert a Ratio schedule to T-tau.

    Ratio schedules define reinforcement as a function of response count,
    which cannot be expressed in the time-based T-tau coordinate system
    without assuming a response rate (a dependent variable).
    """

    def __init__(self, schedule: Atomic) -> None:
        self.schedule = schedule
        super().__init__(
            f"Ratio schedule {schedule.schedule_type} cannot be converted to T-tau: "
            f"response count is not reducible to time without assuming a response rate"
        )


@dataclass(frozen=True)
class TTauParams:
    """T-τ schedule parameters.

    Attributes
    ----------
    T : float
        Cycle duration (must be > 0).
    tau : float
        Reinforcement window duration (0 < tau ≤ T).
    """

    T: float
    tau: float

    def __post_init__(self) -> None:
        if self.T <= 0:
            raise ValueError(f"T must be > 0, got {self.T}")
        if self.tau <= 0 or self.tau > self.T:
            raise ValueError(
                f"tau must be in (0, T], got tau={self.tau}, T={self.T}"
            )

    @property
    def duty_cycle(self) -> float:
        """τ/T — the fundamental reinforcement density parameter."""
        return self.tau / self.T


@dataclass(frozen=True)
class IRTAssumption:
    """Assumed mean inter-response time (seconds).

    This is a dependent variable (organism behavior), not an independent
    variable (schedule definition). It is explicitly separated from TTauParams
    to prevent conflation of schedule specification with schedule performance.
    """

    irt: float


@dataclass(frozen=True)
class TTauApprox:
    """T-tau approximation with explicit assumptions.

    Distinct from TTauParams — the two types cannot be mixed in type-safe code.
    The assumption is preserved for traceability.
    """

    T: float
    tau: float
    assumption: IRTAssumption

    @property
    def duty_cycle(self) -> float:
        """τ/T — approximate reinforcement density."""
        return self.tau / self.T


# ---------------------------------------------------------------------------
# Lattice → T-tau
# ---------------------------------------------------------------------------

_TTAU_CONVERTIBLE_DOMAINS: frozenset[Domain] = frozenset(
    {Domain.INTERVAL, Domain.TIME}
)


def to_ttau(schedule: Atomic) -> TTauParams:
    """Convert a lattice Atomic schedule to T-tau parameters.

    Parameters
    ----------
    schedule : Atomic
        An atomic schedule from the 3×3 lattice. Must have
        domain ∈ {INTERVAL, TIME}.

    Returns
    -------
    TTauParams
        The T-tau representation. For all convertible schedules,
        T = schedule.value and τ = schedule.value (duty_cycle = 1.0).

    Raises
    ------
    RatioScheduleError
        If ``schedule.domain == Domain.RATIO``.
    ValueError
        If ``schedule.value <= 0``.
    """
    if schedule.domain == Domain.RATIO:
        raise RatioScheduleError(schedule)
    if schedule.value <= 0:
        raise ValueError(
            f"Schedule value must be positive for T-tau conversion, "
            f"got {schedule.value}"
        )
    return TTauParams(T=schedule.value, tau=schedule.value)


# ---------------------------------------------------------------------------
# T-tau → Lattice
# ---------------------------------------------------------------------------


def from_ttau(
    params: TTauParams,
    domain: Domain,
    distribution: Distribution,
) -> ScheduleExpr:
    """Convert T-tau parameters back to a lattice schedule expression.

    Parameters
    ----------
    params : TTauParams
        The T-tau parameters to convert.
    domain : Domain
        The target domain (INTERVAL or TIME). Required because T-tau
        does not distinguish response-dependent from response-independent.
    distribution : Distribution
        The target distribution (FIXED, VARIABLE, or RANDOM). Required
        because T-tau does not encode distribution shape.

    Returns
    -------
    ScheduleExpr
        An ``Atomic`` when τ = T (duty_cycle = 1.0), or a ``LimitedHold``
        wrapping an ``Atomic`` when τ < T.

    Raises
    ------
    RatioScheduleError
        If ``domain == Domain.RATIO``.
    """
    if domain == Domain.RATIO:
        raise RatioScheduleError(
            Atomic(ScheduleType(distribution, domain), params.T)
        )

    inner = Atomic(ScheduleType(distribution, domain), params.T)

    if params.tau < params.T:
        return LimitedHold(hold_duration=params.tau, inner=inner)

    return inner


# ---------------------------------------------------------------------------
# Approximate conversion (separated layer)
# ---------------------------------------------------------------------------


def approximate_ttau(schedule: Atomic, irt: float) -> TTauApprox:
    """Approximate a Ratio schedule in T-tau coordinates.

    This function is the **only** path for Ratio → T-tau conversion.
    It requires an explicit IRT (inter-response time) assumption.

    Parameters
    ----------
    schedule : Atomic
        A Ratio schedule (FR, VR, RR).
    irt : float
        Assumed mean inter-response time in seconds (must be > 0).

    Returns
    -------
    TTauApprox
        Approximate T-tau parameters with the IRT assumption preserved.
        T = schedule.value * irt, τ = schedule.value * irt.

    Raises
    ------
    ValueError
        If ``irt <= 0`` or ``schedule.value <= 0``.
    """
    if irt <= 0:
        raise ValueError(f"irt must be > 0, got {irt}")
    if schedule.value <= 0:
        raise ValueError(
            f"Schedule value must be positive, got {schedule.value}"
        )
    t_approx = schedule.value * irt
    return TTauApprox(
        T=t_approx,
        tau=t_approx,
        assumption=IRTAssumption(irt=irt),
    )
