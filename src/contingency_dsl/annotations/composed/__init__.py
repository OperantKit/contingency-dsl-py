"""composed-ext: Composed-layer execution-semantics dimension for contingency-dsl.

Adds @omission, @avoidance annotations that record response-contingent
US modulation rules for composed preparations (negative automaintenance,
discriminated avoidance).

Implements the ExtensionModule protocol defined in contingency-dsl.
"""

from .analyzer import (
    AnalysisResult,
    ComposedAnalysisError,
    ExecutionPlan,
    analyze,
)
from .extension import ComposedExtension
from .types import AvoidanceAnnotation, OmissionAnnotation

__all__ = [
    "ComposedExtension",
    "OmissionAnnotation",
    "AvoidanceAnnotation",
    "AnalysisResult",
    "ComposedAnalysisError",
    "ExecutionPlan",
    "analyze",
]
