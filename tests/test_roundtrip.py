"""Roundtrip tests: parse(format(parse(x))) == parse(x) for all example expressions."""

import pytest

from contingency_dsl import parse, format_program, to_dict, from_dict


EXAMPLES = [
    "FR5",
    "FR 5",
    "VI60s",
    "VI3000ms",
    "FI5min",
    "RR20",
    "RI10s",
    "FT30s",
    "VT60s",
    "RT15s",
    "VR10",
    "EXT",
    "CRF",
    "Conc(VI30s, VI60s)",
    "Chain(FR5, FI30s)",
    "Alt(FR10, FI5min)",
    "Conj(FR5, FI30s)",
    "Tand(VR20, DRL5s)",
    "Mult(FR5, EXT)",
    "Mix(FR5, FR10)",
    "Conc(VI30s, VI60s, VI120s)",
    "Conc(Chain(FR5, VI60s), Alt(FR10, FT30s))",
    "DRL5s",
    "DRO10s",
    "DRH2s",
    "PR(hodos)",
    "PR(linear, start=1, increment=5)",
    "PR(exponential)",
    "PR",
    "Repeat(3, FR10)",
    "Repeat(1, FR10)",
    "Repeat(2, Repeat(3, FR5))",
    "Tand(Repeat(3, FR10), VI60s)",
    "FI30 LH10",
    "VI60 LH5",
    "DRL3 LH8",
    "FI30s LH10s",
    "Chain(FR5, FI30) LH10",
    "FR5(FI30)",
    "FI120(FR10)",
    "VI60(FR10)",
    "FI120s(FI30s)",
    "FR5 -- comment",
]


@pytest.mark.parametrize("text", EXAMPLES, ids=EXAMPLES)
def test_print_roundtrip(text: str) -> None:
    """parse(format(parse(text))) == parse(text)"""
    p1 = parse(text)
    printed = format_program(p1)
    p2 = parse(printed)
    assert p1 == p2, f"Print roundtrip failed:\n  input:   {text!r}\n  printed: {printed!r}"


@pytest.mark.parametrize("text", EXAMPLES, ids=EXAMPLES)
def test_serializer_roundtrip(text: str) -> None:
    """from_dict(to_dict(parse(text))) == parse(text)"""
    p1 = parse(text)
    d = to_dict(p1)
    p2 = from_dict(d)
    assert p1 == p2, f"Serializer roundtrip failed for {text!r}"


LET_EXAMPLES = [
    "let baseline = VI60s\nbaseline",
    "let baseline = VI60s\nlet probe = Conc(VI30s, VI60s)\nConc(baseline, probe)",
    "let a = FR5\nlet b = Chain(a, VI30s)\nb",
]


@pytest.mark.parametrize("text", LET_EXAMPLES, ids=LET_EXAMPLES)
def test_binding_print_roundtrip(text: str) -> None:
    """Programs with bindings survive parse -> print -> parse."""
    p1 = parse(text)
    printed = format_program(p1)
    p2 = parse(printed)
    assert p1 == p2
