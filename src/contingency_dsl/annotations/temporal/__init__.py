"""temporal-ext: Temporal & algorithmic-setup dimension for contingency-dsl.

Adds @clock, @warmup, @algorithm annotations.
Implements the ExtensionModule protocol defined in contingency-dsl.

References:
    Fleshler, M., & Hoffman, H. S. (1962). A progression for generating
        variable-interval schedules. Journal of the Experimental Analysis
        of Behavior, 5(4), 529-530. https://doi.org/10.1901/jeab.1962.5-529
    Hantula, D. A. (1991). A progression for generating variable-interval
        schedules. Journal of the Experimental Analysis of Behavior,
        56(2), 391-392. https://doi.org/10.1901/jeab.1991.56-391
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
