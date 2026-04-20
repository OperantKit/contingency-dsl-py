"""Annotation dataclasses for stimulus-ext.

These frozen dataclasses represent the parsed and validated annotation data
extracted from DSL source. They bridge the gap between DSL declarations and
runtime objects (StimulusManager, SessionEventAdapter).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping


@dataclass(frozen=True)
class ReinforcerAnnotation:
    """Parsed @reinforcer annotation.

    Examples:
        @reinforcer("food")
        @reinforcer("food", type="unconditioned", power=1.0)
        @reinforcer("tone", type="conditioned", backup="food", alpha0=0.3)
    """

    name: str
    reinforcer_type: Literal["unconditioned", "conditioned", "generalized"] = "unconditioned"
    backup_ids: tuple[str, ...] = ()
    innate_power: float = 1.0
    initial_alpha: float = 0.5


@dataclass(frozen=True)
class SDAnnotation:
    """Parsed @sd annotation.

    Examples:
        @sd("red_light")
        @sd("red_light", component=1)
    """

    name: str
    component: int | None = None


@dataclass(frozen=True)
class OperandumAnnotation:
    """Parsed @operandum annotation.

    Examples:
        @operandum("left_lever")
        @operandum("right_lever")
    """

    name: str


@dataclass(frozen=True)
class BriefAnnotation:
    """Parsed @brief annotation for second-order schedules.

    Examples:
        @brief("light", duration=2)
        @brief("none")  -- explicit opt-out (Issue #17)
    """

    name: str
    duration: float | None = None
    time_unit: str | None = None


@dataclass(frozen=True)
class StimulusDeclarationSet:
    """All stimulus declarations extracted from a single DSL program.

    This is the bridge between DSL-level declarations and runtime objects.
    It replaces the hardcoded operandum_to_stimulus mapping that was
    previously required by SessionEventAdapter.
    """

    reinforcers: Mapping[str, ReinforcerAnnotation] = field(default_factory=dict)
    operandum_bindings: Mapping[str, OperandumAnnotation] = field(default_factory=dict)
    sd_bindings: Mapping[str, SDAnnotation] = field(default_factory=dict)
    brief_specs: Mapping[str, BriefAnnotation] = field(default_factory=dict)

    def to_operandum_stimulus_mapping(self) -> dict[int, str]:
        """Derive the operandum_to_stimulus mapping for SessionEventAdapter.

        Assigns integer indices to operanda in declaration order.
        This replaces the hardcoded dict that was previously required.
        """
        return {i: ann.name for i, ann in enumerate(self.operandum_bindings.values())}
