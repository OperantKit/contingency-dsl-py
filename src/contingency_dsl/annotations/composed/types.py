"""Annotation dataclasses for composed-ext.

These frozen dataclasses represent the parsed and validated annotation data
for the composed layer (JEAB preparations that layer Pavlovian contingencies
over operant baselines): omission (negative automaintenance) and
discriminated-avoidance response rules.

Both rules share the response-contingent US-modulation pattern — a specified
response class, emitted within a specified temporal window, alters scheduled
US delivery for that trial.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OmissionAnnotation:
    """Parsed @omission annotation.

    Records the response-contingent US cancellation rule for negative
    automaintenance (Williams & Williams, 1969): emission of ``response``
    during the ``during`` window cancels the scheduled US on that trial.

    Examples:
        @omission(response="key_peck")
        @omission(response="key_peck", during="cs")
    """

    response: str
    during: Literal["cs", "iti", "trial"] = "cs"


@dataclass(frozen=True)
class AvoidanceAnnotation:
    """Parsed @avoidance annotation.

    Records the response-contingent avoidance rule for discriminated
    avoidance (Solomon & Wynne, 1954): emission of ``response`` during the
    CS either cancels the US for that trial (``mode="cancel"``) or
    postpones CS offset / US onset (``mode="postpone"``).

    Examples:
        @avoidance(response="lever_press")
        @avoidance(response="lever_press", mode="cancel")
        @avoidance(response="lever_press", mode="postpone")
    """

    response: str
    mode: Literal["cancel", "postpone"] = "cancel"
