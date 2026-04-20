"""measurement-ext: Measurement dimension for contingency-dsl.

Adds @session_end, @baseline, @steady_state annotations (Phase 1).
Registers Phase 2 keywords: @dependent_measure, @training_volume,
@microstructure, @phase_end, @logging, @iri_window, @warmup_exclude.

Implements the ExtensionModule protocol defined in contingency-dsl.

References:
    Baron, A., & Perone, M. (1998). Experimental design and analysis in the
        laboratory study of human operant behavior. Plenum Press.
    Sidman, M. (1960). Tactics of scientific research. Basic Books.
    Skinner, B. F. (1938). The behavior of organisms. Appleton-Century-Crofts.
"""

from .extension import MeasurementExtension
from .types import (
    BaselineAnnotation,
    MeasurementDeclarationSet,
    SessionEndAnnotation,
    SteadyStateAnnotation,
)

__all__ = [
    "MeasurementExtension",
    "SessionEndAnnotation",
    "BaselineAnnotation",
    "SteadyStateAnnotation",
    "MeasurementDeclarationSet",
]
