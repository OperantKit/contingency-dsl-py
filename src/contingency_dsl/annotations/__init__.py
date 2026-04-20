"""Core recommended annotation implementations.

These implement the core vocabulary of `@`-prefixed annotations defined in
`contingency-dsl/annotations/`:

- stimulus:    @reinforcer, @sd, @operandum, @brief
- temporal:    temporal boundaries and intervals
- subjects:    subject characteristics and establishing operations
- apparatus:   physical apparatus binding
- composed:    composed operant x respondent markers (@omission, @avoidance)
- measurement: dependent measure quantification
"""

from .apparatus import ApparatusExtension
from .composed import ComposedExtension
from .measurement import MeasurementExtension
from .stimulus import StimulusExtension
from .subjects import SubjectsExtension
from .temporal import TemporalExtension

__all__ = [
    "ApparatusExtension",
    "ComposedExtension",
    "MeasurementExtension",
    "StimulusExtension",
    "SubjectsExtension",
    "TemporalExtension",
]
