"""Targeted tests that close line-coverage gaps in uncommonly-exercised
branches of the serializer, parser, and respondent parser.

These tests don't correspond to any conformance fixture — they exercise
defensive branches so a regression touching an error path surfaces in CI
immediately rather than the next time a user hits it.
"""

from __future__ import annotations

import pytest

from contingency_dsl import (
    Annotation,
    AnnotatedSchedule,
    Atomic,
    Binding,
    Combinator,
    Compound,
    IdentifierRef,
    LimitedHold,
    Modifier,
    ParamDecl,
    Program,
    Special,
    format_program,
    from_dict,
    parse,
    to_dict,
)
from contingency_dsl.errors import ParseError


def _atomic(text: str) -> Atomic:
    """Return the Atomic produced by parsing a single-schedule string."""
    schedule = parse(text).schedule
    assert isinstance(schedule, Atomic)
    return schedule


def _roundtrip(program: Program) -> Program:
    return from_dict(to_dict(program))


def test_roundtrip_annotated_schedule_wrapping_compound() -> None:
    inner = Compound(
        combinator=Combinator.CONC,
        components=(_atomic("VI30s"), _atomic("VI60s")),
    )
    program = Program(
        schedule=AnnotatedSchedule(
            expr=inner,
            annotations=(
                Annotation(keyword="reinforcer", positional="pellet"),
                Annotation(keyword="clock", params={"unit": "s"}),
            ),
        )
    )
    assert _roundtrip(program) == program


def test_roundtrip_limited_hold_wrapping_compound() -> None:
    inner = Compound(
        combinator=Combinator.CHAIN,
        components=(_atomic("FR5"), _atomic("FI30s")),
    )
    program = Program(
        schedule=LimitedHold(hold_duration=10.0, inner=inner, time_unit="s")
    )
    assert _roundtrip(program) == program


def test_roundtrip_identifier_ref_binding() -> None:
    program = Program(
        bindings=(Binding(name="x", value=_atomic("VI60s")),),
        schedule=IdentifierRef(name="x"),
    )
    assert _roundtrip(program) == program


def test_roundtrip_param_decl() -> None:
    program = Program(
        param_decls=(ParamDecl(name="LH", value=10.0, time_unit="s"),),
        schedule=_atomic("FI30s"),
    )
    assert _roundtrip(program) == program


@pytest.mark.parametrize("kind", ["EXT", "CRF"])
def test_roundtrip_special_schedules(kind: str) -> None:
    program = Program(schedule=Special(kind=kind))
    assert _roundtrip(program) == program
    assert parse(format_program(program)) == program


def test_roundtrip_modifier_nested_inner() -> None:
    compound_inner = Compound(
        combinator=Combinator.TAND,
        components=(_atomic("FR5"), _atomic("VI60s")),
    )
    program = Program(
        schedule=Modifier(modifier="Repeat", value=3.0, inner=compound_inner)
    )
    assert _roundtrip(program) == program


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("PR", "PR_BARE|PR"),
        ("PR(linear, start=1.5, increment=2)", "PR_NON_INTEGER_START"),
        ("PR(linear, start=1, increment=2.5)", "PR_NON_INTEGER_INCREMENT"),
        ("PR(geometric, ratio=0.5)", "PR_GEOMETRIC_RATIO_NOT_PROGRESSIVE"),
        ("PR(linear, whatever=5)", "unknown PR kwarg"),
    ],
)
def test_pr_parse_errors(text: str, code: str) -> None:
    with pytest.raises(ParseError, match=code):
        parse(text)


def test_pr_shorthand_step_alias() -> None:
    """`PR(step=N, start=M)` is shorthand for `PR(linear, start=M, increment=N)`."""
    mod = parse("PR(step=5, start=1)").schedule
    assert isinstance(mod, Modifier)
    assert mod.modifier == "PR"
    assert mod.pr_step == "linear"
    assert mod.pr_start == 1
    assert mod.pr_increment == 5


def test_pr_shorthand_keyword_order_independent() -> None:
    assert parse("PR(start=1, step=5)") == parse("PR(step=5, start=1)")
