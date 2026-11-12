"""temporal-ext: Temporal & algorithmic-setup dimension for contingency-dsl.

Adds @clock, @warmup, @algorithm annotations.
Implements the ExtensionModule protocol defined in contingency-dsl.

References:
    Fleshler, M., & Hoffman, H. S. (1962). A progression for generating
        variable-interval schedules. Journal of the Experimental Analysis
        of Behavior, 5(4), 529-530. https://doi.org/10.1901/jeab.1962.5-529
    Hantula, D. A. (1991). A simple BASIC program to generate values for
        variable-interval schedules of reinforcement. Journal of Applied
        Behavior Analysis, 24(4), 799-801.
        https://doi.org/10.1901/jaba.1991.24-799
"""

from .extension import TemporalExtension
from .types import (
    AlgorithmAnnotation,
    ClockAnnotation,
    TemporalDeclarationSet,
    WarmupAnnotation,
)

__all__ = [
    "TemporalExtension",
    "ClockAnnotation",
    "WarmupAnnotation",
    "AlgorithmAnnotation",
    "TemporalDeclarationSet",
]
