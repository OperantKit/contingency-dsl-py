"""Parser tests for respondent Tier A primitives (R1-R14).

Each test constructs the expected AST by hand and asserts equality with
parse() output. Covers:
    R1-R4  Pair.ForwardDelay / ForwardTrace / Simultaneous / Backward
    R5     Extinction
    R6     CSOnly
    R7     USOnly
    R8     Contingency
    R9     TrulyRandom
    R10    ExplicitlyUnpaired
    R11    Compound
    R12    Serial
    R13    ITI
    R14    Differential
"""

from __future__ import annotations

from contingency_dsl import parse
from contingency_dsl.respondent import (
    CSOnly,
    Compound,
    Contingency,
    Differential,
    Duration,
    ExplicitlyUnpaired,
    Extinction,
    ITI,
    PairBackward,
    PairForwardDelay,
    PairForwardTrace,
    PairSimultaneous,
    Serial,
    TrulyRandom,
    USOnly,
)


# --- R5: Extinction ---------------------------------------------------------


def test_extinction_simple():
    prog = parse("Extinction(tone)")
    assert prog.schedule == Extinction(cs="tone")


def test_extinction_with_kwarg_spelling():
    """Extinction(cs=tone) is a valid alternative spelling."""
    prog = parse("Extinction(cs=tone)")
    assert prog.schedule == Extinction(cs="tone")


# --- R6: CSOnly -------------------------------------------------------------


def test_cs_only_with_trials_kwarg():
    prog = parse("CSOnly(tone, trials=40)")
    assert prog.schedule == CSOnly(cs="tone", trials=40)


def test_cs_only_positional():
    prog = parse("CSOnly(tone, 20)")
    assert prog.schedule == CSOnly(cs="tone", trials=20)


# --- R7: USOnly -------------------------------------------------------------


def test_us_only_with_trials_kwarg():
    prog = parse("USOnly(shock, trials=20)")
    assert prog.schedule == USOnly(us="shock", trials=20)


def test_us_only_positional():
    prog = parse("USOnly(shock, 15)")
    assert prog.schedule == USOnly(us="shock", trials=15)


# --- R13: ITI ---------------------------------------------------------------


def test_iti_exponential():
    prog = parse("ITI(exponential, mean=60s)")
    assert prog.schedule == ITI(
        distribution="exponential",
        mean=Duration(value=60.0, unit="s"),
    )


def test_iti_fixed_minutes():
    prog = parse("ITI(fixed, mean=2min)")
    assert prog.schedule == ITI(
        distribution="fixed",
        mean=Duration(value=2.0, unit="min"),
    )


def test_iti_uniform():
    prog = parse("ITI(uniform, mean=30s)")
    assert prog.schedule == ITI(
        distribution="uniform",
        mean=Duration(value=30.0, unit="s"),
    )


# --- R8: Contingency --------------------------------------------------------


def test_contingency_kwargs():
    prog = parse("Contingency(p_us_given_cs=0.8, p_us_given_no_cs=0.2)")
    assert prog.schedule == Contingency(p_us_given_cs=0.8, p_us_given_no_cs=0.2)


def test_contingency_positional():
    prog = parse("Contingency(0.9, 0.1)")
    assert prog.schedule == Contingency(p_us_given_cs=0.9, p_us_given_no_cs=0.1)


# --- R9: TrulyRandom --------------------------------------------------------


def test_truly_random_no_p():
    prog = parse("TrulyRandom(tone, shock)")
    assert prog.schedule == TrulyRandom(cs="tone", us="shock")


def test_truly_random_with_p():
    prog = parse("TrulyRandom(tone, shock, p=0.3)")
    assert prog.schedule == TrulyRandom(cs="tone", us="shock", p=0.3)


# --- R10: ExplicitlyUnpaired ------------------------------------------------


def test_explicitly_unpaired():
    prog = parse("ExplicitlyUnpaired(tone, shock, min_separation=30s)")
    assert prog.schedule == ExplicitlyUnpaired(
        cs="tone",
        us="shock",
        min_separation=Duration(value=30.0, unit="s"),
    )


def test_explicitly_unpaired_no_min_sep():
    prog = parse("ExplicitlyUnpaired(tone, shock)")
    assert prog.schedule == ExplicitlyUnpaired(cs="tone", us="shock")


# --- R11: Compound ----------------------------------------------------------


def test_compound_default_mode():
    prog = parse("Compound(cs_list=[tone, light])")
    assert prog.schedule == Compound(
        cs_list=("tone", "light"), mode="Simultaneous"
    )


def test_compound_explicit_mode():
    prog = parse("Compound(cs_list=[tone, light], mode=Simultaneous)")
    assert prog.schedule == Compound(
        cs_list=("tone", "light"), mode="Simultaneous"
    )


# --- R12: Serial ------------------------------------------------------------


def test_serial():
    prog = parse("Serial(cs_list=[light, tone], isi=3s)")
    assert prog.schedule == Serial(
        cs_list=("light", "tone"),
        isi=Duration(value=3.0, unit="s"),
    )


# --- R14: Differential ------------------------------------------------------


def test_differential_full():
    prog = parse("Differential(cs_positive=tone_plus, cs_negative=tone_minus, us=shock)")
    assert prog.schedule == Differential(
        cs_positive="tone_plus", cs_negative="tone_minus", us="shock"
    )


def test_differential_short():
    prog = parse("Differential(cs_positive=tone_plus, cs_negative=tone_minus)")
    assert prog.schedule == Differential(
        cs_positive="tone_plus", cs_negative="tone_minus", us=None
    )


# --- R1: Pair.ForwardDelay --------------------------------------------------


def test_pair_forward_delay():
    prog = parse("Pair.ForwardDelay(tone, shock, isi=10s, cs_duration=15s)")
    assert prog.schedule == PairForwardDelay(
        cs="tone",
        us="shock",
        isi=Duration(value=10.0, unit="s"),
        cs_duration=Duration(value=15.0, unit="s"),
    )


# --- R2: Pair.ForwardTrace --------------------------------------------------


def test_pair_forward_trace():
    prog = parse("Pair.ForwardTrace(tone, food, trace_interval=5s)")
    assert prog.schedule == PairForwardTrace(
        cs="tone",
        us="food",
        trace_interval=Duration(value=5.0, unit="s"),
    )


# --- R3: Pair.Simultaneous --------------------------------------------------


def test_pair_simultaneous():
    prog = parse("Pair.Simultaneous(light, airpuff)")
    assert prog.schedule == PairSimultaneous(cs="light", us="airpuff")


# --- R4: Pair.Backward ------------------------------------------------------


def test_pair_backward():
    prog = parse("Pair.Backward(shock, tone, isi=2s)")
    assert prog.schedule == PairBackward(
        us="shock",
        cs="tone",
        isi=Duration(value=2.0, unit="s"),
    )
