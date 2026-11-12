"""Program-level BO and BO=0 (grammar constraints 13 and 14).

13: BO=0 is legal on Mult/Mix (explicit no blackout, same as omission).
14: a program-level BO declaration applies to every Mult/Mix; an
    expression-level BO overrides it.
"""

from __future__ import annotations

import pytest

from contingency_dsl import analyze, parse
from contingency_dsl.errors import SemanticError


def _bo(params: dict | None) -> tuple[float, str | None] | None:
    if not params or "BO" not in params:
        return None
    value = params["BO"]
    return (value.value, value.time_unit)


@pytest.mark.parametrize("combinator", ["Mult", "Mix"])
def test_program_level_bo_applies_to_mult_mix(combinator: str) -> None:
    result = analyze(parse(f"BO = 5s\n{combinator}(FR2, FR3)"))
    assert _bo(result.program.schedule.params) == (5.0, "s")


def test_expression_level_bo_overrides_program_level() -> None:
    result = analyze(parse("BO = 5s\nMult(FR2, FR3, BO=1s)"))
    assert _bo(result.program.schedule.params) == (1.0, "s")


def test_program_level_bo_reaches_nested_mult() -> None:
    result = analyze(parse("BO = 2s\nConc(FR1, Mult(FR2, FR3))"))
    conc = result.program.schedule
    assert _bo(conc.params) is None
    assert _bo(conc.components[1].params) == (2.0, "s")


def test_program_level_bo_reaches_mult_through_binding() -> None:
    result = analyze(parse("BO = 2s\nlet m = Mix(FR2, FR3)\nm"))
    assert _bo(result.program.schedule.params) == (2.0, "s")


def test_program_level_bo_reaches_mult_inside_punish() -> None:
    result = analyze(parse("BO = 2s\nConc(FR1, FR2, PUNISH(1)=Mult(FR1, FR2))"))
    punish = result.program.schedule.params["PUNISH"]
    payload = dict(punish.payload) if hasattr(punish, "payload") else punish
    (entry,) = payload["component"]
    assert _bo(entry["schedule"].params) == (2.0, "s")


def test_program_level_bo_without_mult_mix_adds_nothing() -> None:
    result = analyze(parse("BO = 5s\nConc(FR1, FR2, COD=2s)"))
    assert set(result.program.schedule.params) == {"COD"}


@pytest.mark.parametrize("combinator", ["Mult", "Mix"])
def test_zero_bo_is_legal(combinator: str) -> None:
    result = analyze(parse(f"{combinator}(FR2, FR3, BO=0s)"))
    assert _bo(result.program.schedule.params) == (0.0, "s")


def test_zero_frco_is_still_rejected() -> None:
    with pytest.raises(SemanticError, match="FRCO_NONPOSITIVE"):
        analyze(parse("Conc(FR1, FR2, FRCO=0)"))
