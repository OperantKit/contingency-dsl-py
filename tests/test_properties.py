"""Property-based tests for parser, printer, and serializer invariants.

Uses hypothesis to generate random ASTs and verify structural laws that
must hold across all inputs (not just fixture-specific ones). The goal is
to catch regressions that don't show up in the curated conformance suite.

Laws checked:

* ``parse(format(parse(text))) == parse(text)`` — print roundtrip invariance
* ``from_dict(to_dict(program)) == program`` — serializer roundtrip
* Commutative combinators (Conc / Alt / Conj) accept either component order
* Atomic → text → Atomic preserves all four dimensions
"""

from __future__ import annotations

import string
from typing import Any, ClassVar, Mapping, Sequence

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from contingency_dsl import (
    Atomic,
    Combinator,
    Compound,
    Distribution,
    Domain,
    Program,
    ScheduleType,
    Special,
    format_expr,
    format_program,
    from_dict,
    parse,
    to_dict,
)
from contingency_dsl.extensions import ExtensionRegistry


_DISTS = list(Distribution)
_DOMAINS = list(Domain)
_TIME_UNITS_BY_DOMAIN: dict[Domain, list[str | None]] = {
    Domain.RATIO: [None],
    Domain.INTERVAL: ["s", "ms", "min"],
    Domain.TIME: ["s", "ms", "min"],
}
_SPECIAL_KINDS = ["EXT", "CRF"]
_COMMUTATIVE_COMBINATORS = [Combinator.CONC, Combinator.ALT, Combinator.CONJ]
_NON_COMMUTATIVE_COMBINATORS = [
    Combinator.CHAIN, Combinator.TAND, Combinator.MULT, Combinator.MIX,
]
_RESERVED_KEYWORDS = frozenset({
    "phase", "progressive", "shaping", "experiment",
    "let", "true", "false",
})


@st.composite
def atomics(draw):
    dist = draw(st.sampled_from(_DISTS))
    domain = draw(st.sampled_from(_DOMAINS))
    value = draw(st.integers(min_value=1, max_value=9999))
    unit = draw(st.sampled_from(_TIME_UNITS_BY_DOMAIN[domain]))
    return Atomic(
        schedule_type=ScheduleType(distribution=dist, domain=domain),
        value=float(value),
        time_unit=unit,
    )


@st.composite
def specials(draw):
    return Special(kind=draw(st.sampled_from(_SPECIAL_KINDS)))


@st.composite
def leaf_schedules(draw):
    return draw(st.one_of(atomics(), specials()))


@st.composite
def compound_schedules(draw, combinators):
    n = draw(st.integers(min_value=2, max_value=3))
    components = tuple(draw(leaf_schedules()) for _ in range(n))
    comb = draw(st.sampled_from(combinators))
    return Compound(combinator=comb, components=components)


@st.composite
def any_schedules(draw):
    return draw(
        st.one_of(
            leaf_schedules(),
            compound_schedules(_COMMUTATIVE_COMBINATORS),
            compound_schedules(_NON_COMMUTATIVE_COMBINATORS),
        )
    )


@st.composite
def keyword_strings(draw):
    first = draw(st.sampled_from(list(string.ascii_lowercase)))
    rest = draw(
        st.text(
            alphabet=string.ascii_lowercase + "_",
            min_size=0,
            max_size=10,
        )
    )
    return first + rest


class _SingleKeywordExtension:
    """Minimal ExtensionRegistry plugin exposing one annotation keyword."""

    name: ClassVar[str] = "prop-ext"
    version: ClassVar[str] = "0.1.0"

    def __init__(self, keyword: str) -> None:
        self._kws: frozenset[str] = frozenset({keyword})

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return self._kws

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()


@given(schedule=any_schedules())
@settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_print_roundtrip_is_identity(schedule) -> None:
    program = Program(schedule=schedule)
    text = format_program(program)
    parsed = parse(text)
    assert parsed == program, (
        f"Print roundtrip drift:\n  original: {program!r}\n"
        f"  text:     {text!r}\n  parsed:   {parsed!r}"
    )


@given(schedule=any_schedules())
@settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_serializer_roundtrip_is_identity(schedule) -> None:
    program = Program(schedule=schedule)
    d = to_dict(program)
    recovered = from_dict(d)
    assert recovered == program, (
        f"Serializer roundtrip drift:\n  original: {program!r}\n"
        f"  dict:     {d!r}\n  recovered:{recovered!r}"
    )


@given(
    a=leaf_schedules(),
    b=leaf_schedules(),
    comb=st.sampled_from(_COMMUTATIVE_COMBINATORS),
)
@settings(max_examples=100)
def test_commutative_compound_serializes_with_both_orders(a, b, comb) -> None:
    """Conc/Alt/Conj accept either component order and both parse.

    This is a parseability property — it does not assert semantic
    equivalence at the Python-dataclass level (those remain distinct
    AST nodes); the analyzer performs commutative normalisation.
    """
    c_ab = Compound(combinator=comb, components=(a, b))
    c_ba = Compound(combinator=comb, components=(b, a))
    assert parse(format_expr(c_ab)).schedule == c_ab
    assert parse(format_expr(c_ba)).schedule == c_ba


@given(
    value=st.integers(min_value=1, max_value=100),
    keyword=keyword_strings(),
)
@settings(max_examples=80)
def test_annotation_program_level_roundtrip(value, keyword) -> None:
    assume(keyword not in _RESERVED_KEYWORDS)

    registry = ExtensionRegistry.build(_SingleKeywordExtension(keyword))
    text = f"@{keyword}(n={value})\nFR5"
    p1 = parse(text, extensions=registry)
    p2 = parse(format_program(p1), extensions=registry)
    assert p1 == p2


@given(schedule=leaf_schedules())
@settings(max_examples=50)
def test_atomic_roundtrip_preserves_dimensions(schedule) -> None:
    parsed = parse(format_expr(schedule)).schedule
    if isinstance(schedule, Atomic):
        assert isinstance(parsed, Atomic)
        assert parsed.schedule_type == schedule.schedule_type
        assert parsed.value == schedule.value
        assert parsed.time_unit == schedule.time_unit
    else:
        assert parsed == schedule
