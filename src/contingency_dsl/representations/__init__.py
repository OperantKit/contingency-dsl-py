"""Alternative representations for the contingency-dsl type system.

Representations are bidirectional coordinate transformations between the
3×3 lattice (Distribution × Domain) and alternative parameterizations
of the same behavioral space.

See contingency-dsl/representations/DESIGN.md for design principles.
"""

from .t_tau import (
    IRTAssumption,
    RatioScheduleError,
    TTauApprox,
    TTauParams,
    approximate_ttau,
    from_ttau,
    to_ttau,
)

__all__ = [
    "TTauParams",
    "TTauApprox",
    "IRTAssumption",
    "RatioScheduleError",
    "to_ttau",
    "from_ttau",
    "approximate_ttau",
]
