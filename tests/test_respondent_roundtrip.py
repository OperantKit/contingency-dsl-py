"""Round-trip tests for respondent Tier A primitives.

For each representative source string, asserts:
  1. parse(text) → to_dict produces an equivalent dict
  2. parse(text) → from_dict → equals the parsed AST
  3. format_program(parse(text)) → re-parseable equivalent AST
"""

from __future__ import annotations

import pytest

from contingency_dsl import parse, to_dict, from_dict, format_program


RESPONDENT_EXAMPLES = [
    "Extinction(tone)",
    "CSOnly(tone, trials=40)",
    "USOnly(shock, trials=20)",
    "ITI(exponential, mean=60s)",
    "ITI(fixed, mean=30s)",
    "ITI(uniform, mean=2min)",
    "Contingency(0.9, 0.1)",
    "Contingency(0.5, 0.5)",
    "TrulyRandom(tone, shock)",
    "TrulyRandom(tone, shock, p=0.3)",
    "ExplicitlyUnpaired(tone, shock)",
    "ExplicitlyUnpaired(tone, shock, min_separation=30s)",
    "Compound(cs_list=[tone, light])",
    "Compound(cs_list=[tone, light], mode=Simultaneous)",
    "Serial(cs_list=[light, tone], isi=3s)",
    "Differential(cs_positive=tone_plus, cs_negative=tone_minus, us=shock)",
    "Differential(cs_positive=tone_plus, cs_negative=tone_minus)",
    "Pair.ForwardDelay(tone, shock, isi=10s, cs_duration=15s)",
    "Pair.ForwardTrace(tone, food, trace_interval=5s)",
    "Pair.Simultaneous(light, airpuff)",
    "Pair.Backward(shock, tone, isi=2s)",
]


@pytest.mark.parametrize("text", RESPONDENT_EXAMPLES, ids=RESPONDENT_EXAMPLES)
def test_ast_from_dict_roundtrip(text: str) -> None:
    program = parse(text)
    as_dict = to_dict(program)
    reconstructed = from_dict(as_dict)
    assert reconstructed.schedule == program.schedule


@pytest.mark.parametrize("text", RESPONDENT_EXAMPLES, ids=RESPONDENT_EXAMPLES)
def test_format_then_parse_roundtrip(text: str) -> None:
    program = parse(text)
    formatted = format_program(program)
    reparsed = parse(formatted)
    assert reparsed.schedule == program.schedule, (
        f"round-trip mismatch: original={text!r} formatted={formatted!r}"
    )
