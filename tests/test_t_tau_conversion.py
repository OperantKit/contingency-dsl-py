"""T-tau representation conformance tests.

Validates bidirectional conversion between the 3×3 lattice and the T-tau
coordinate system (Schoenfeld & Cole, 1972) against the language-independent
test suite in contingency-dsl/representations/t-tau/conformance/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contingency_dsl.ast import Atomic, LimitedHold, ScheduleType
from contingency_dsl.enums import Distribution, Domain
from contingency_dsl.representations.t_tau import (
    IRTAssumption,
    RatioScheduleError,
    TTauApprox,
    TTauParams,
    approximate_ttau,
    from_ttau,
    to_ttau,
)

CONFORMANCE_DIR = (
    Path(__file__).parent.parent.parent
    / "contingency-dsl"
    / "conformance"
    / "representations"
    / "t-tau"
)

DIST_MAP = {"F": Distribution.FIXED, "V": Distribution.VARIABLE, "R": Distribution.RANDOM}
DOMAIN_MAP = {"R": Domain.RATIO, "I": Domain.INTERVAL, "T": Domain.TIME}


def _load_cases(filename: str) -> list[dict]:
    path = CONFORMANCE_DIR / filename
    if not path.exists():
        pytest.skip(f"conformance file not found: {path}", allow_module_level=True)
    with open(path) as f:
        return json.load(f)


def _atomic_from_dict(d: dict) -> Atomic:
    """Reconstruct an Atomic AST node from a conformance JSON dict."""
    return Atomic(
        schedule_type=ScheduleType(DIST_MAP[d["dist"]], DOMAIN_MAP[d["domain"]]),
        value=d["value"],
        time_unit=d.get("time_unit"),
    )


# ---------------------------------------------------------------------------
# to_ttau conformance
# ---------------------------------------------------------------------------

_TO_TTAU_CASES = _load_cases("to_ttau.json")
_TO_TTAU_SUCCESS = [c for c in _TO_TTAU_CASES if "expected" in c]
_TO_TTAU_ERRORS = [c for c in _TO_TTAU_CASES if "expected_error" in c]


@pytest.mark.parametrize("case", _TO_TTAU_SUCCESS, ids=[c["id"] for c in _TO_TTAU_SUCCESS])
def test_to_ttau_success(case: dict) -> None:
    schedule = _atomic_from_dict(case["input"])
    result = to_ttau(schedule)

    assert isinstance(result, TTauParams)
    assert result.T == pytest.approx(case["expected"]["T"])
    assert result.tau == pytest.approx(case["expected"]["tau"])
    assert result.duty_cycle == pytest.approx(case["expected"]["duty_cycle"])


@pytest.mark.parametrize("case", _TO_TTAU_ERRORS, ids=[c["id"] for c in _TO_TTAU_ERRORS])
def test_to_ttau_ratio_error(case: dict) -> None:
    schedule = _atomic_from_dict(case["input"])
    with pytest.raises(RatioScheduleError, match=case["expected_error"]["message_contains"]):
        to_ttau(schedule)


# ---------------------------------------------------------------------------
# from_ttau conformance
# ---------------------------------------------------------------------------

_FROM_TTAU_CASES = _load_cases("from_ttau.json")
_FROM_TTAU_SUCCESS = [c for c in _FROM_TTAU_CASES if "expected" in c]
_FROM_TTAU_ERRORS = [c for c in _FROM_TTAU_CASES if "expected_error" in c]


@pytest.mark.parametrize("case", _FROM_TTAU_SUCCESS, ids=[c["id"] for c in _FROM_TTAU_SUCCESS])
def test_from_ttau_success(case: dict) -> None:
    params = TTauParams(T=case["input"]["T"], tau=case["input"]["tau"])
    domain = DOMAIN_MAP[case["disambiguation"]["domain"]]
    distribution = DIST_MAP[case["disambiguation"]["distribution"]]

    result = from_ttau(params, domain=domain, distribution=distribution)
    expected = case["expected"]

    if expected["type"] == "Atomic":
        assert isinstance(result, Atomic)
        assert result.dist == DIST_MAP[expected["dist"]]
        assert result.domain == DOMAIN_MAP[expected["domain"]]
        assert result.value == pytest.approx(expected["value"])
    elif expected["type"] == "LimitedHold":
        assert isinstance(result, LimitedHold)
        assert result.hold_duration == pytest.approx(expected["hold_duration"])
        inner = result.inner
        assert isinstance(inner, Atomic)
        assert inner.dist == DIST_MAP[expected["inner"]["dist"]]
        assert inner.domain == DOMAIN_MAP[expected["inner"]["domain"]]
        assert inner.value == pytest.approx(expected["inner"]["value"])


@pytest.mark.parametrize("case", _FROM_TTAU_ERRORS, ids=[c["id"] for c in _FROM_TTAU_ERRORS])
def test_from_ttau_ratio_error(case: dict) -> None:
    params = TTauParams(T=case["input"]["T"], tau=case["input"]["tau"])
    domain = DOMAIN_MAP[case["disambiguation"]["domain"]]
    distribution = DIST_MAP[case["disambiguation"]["distribution"]]

    with pytest.raises(RatioScheduleError, match=case["expected_error"]["message_contains"]):
        from_ttau(params, domain=domain, distribution=distribution)


# ---------------------------------------------------------------------------
# roundtrip conformance
# ---------------------------------------------------------------------------

_ROUNDTRIP_CASES = _load_cases("roundtrip.json")


@pytest.mark.parametrize("case", _ROUNDTRIP_CASES, ids=[c["id"] for c in _ROUNDTRIP_CASES])
def test_roundtrip(case: dict) -> None:
    """Lattice → T-tau → Lattice preserves schedule identity."""
    original = _atomic_from_dict(case["input"])

    # Forward: lattice → T-tau
    ttau = to_ttau(original)

    # Reverse: T-tau → lattice (with original's disambiguation)
    recovered = from_ttau(ttau, domain=original.domain, distribution=original.dist)

    assert isinstance(recovered, Atomic)
    assert recovered.dist == original.dist
    assert recovered.domain == original.domain
    assert recovered.value == pytest.approx(original.value)
    # time_unit is not preserved through T-tau (T-tau is unit-agnostic)


# ---------------------------------------------------------------------------
# error conformance
# ---------------------------------------------------------------------------

_ERROR_CASES = _load_cases("errors.json")


@pytest.mark.parametrize("case", _ERROR_CASES, ids=[c["id"] for c in _ERROR_CASES])
def test_errors(case: dict) -> None:
    error_type = case["expected_error"]["type"]

    if "approximate_irt" in case:
        # approximate_ttau error cases
        schedule = _atomic_from_dict(case["input"])
        with pytest.raises(ValueError, match=case["expected_error"]["message_contains"]):
            approximate_ttau(schedule, irt=case["approximate_irt"])
    elif case["input"].get("type") == "Atomic":
        # to_ttau error cases (value=0, etc.)
        schedule = _atomic_from_dict(case["input"])
        with pytest.raises(ValueError, match=case["expected_error"]["message_contains"]):
            to_ttau(schedule)
    else:
        # TTauParams construction error cases
        with pytest.raises(ValueError, match=case["expected_error"]["message_contains"]):
            TTauParams(T=case["input"]["T"], tau=case["input"]["tau"])


# ---------------------------------------------------------------------------
# TTauParams unit tests
# ---------------------------------------------------------------------------


class TestTTauParams:
    def test_duty_cycle_full(self) -> None:
        p = TTauParams(T=30.0, tau=30.0)
        assert p.duty_cycle == pytest.approx(1.0)

    def test_duty_cycle_half(self) -> None:
        p = TTauParams(T=60.0, tau=30.0)
        assert p.duty_cycle == pytest.approx(0.5)

    def test_duty_cycle_small(self) -> None:
        p = TTauParams(T=100.0, tau=10.0)
        assert p.duty_cycle == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# TTauApprox unit tests
# ---------------------------------------------------------------------------


class TestApproximateTTau:
    def test_fr5_irt2(self) -> None:
        """FR(5) with IRT=2s → TTauApprox(T=10, τ=10)."""
        fr5 = Atomic(ScheduleType(Distribution.FIXED, Domain.RATIO), 5.0)
        result = approximate_ttau(fr5, irt=2.0)

        assert isinstance(result, TTauApprox)
        assert result.T == pytest.approx(10.0)
        assert result.tau == pytest.approx(10.0)
        assert result.duty_cycle == pytest.approx(1.0)
        assert result.assumption == IRTAssumption(irt=2.0)

    def test_vr20_irt05(self) -> None:
        """VR(20) with IRT=0.5s → TTauApprox(T=10, τ=10)."""
        vr20 = Atomic(ScheduleType(Distribution.VARIABLE, Domain.RATIO), 20.0)
        result = approximate_ttau(vr20, irt=0.5)

        assert isinstance(result, TTauApprox)
        assert result.T == pytest.approx(10.0)
        assert result.tau == pytest.approx(10.0)
        assert result.assumption.irt == pytest.approx(0.5)

    def test_approx_is_not_exact(self) -> None:
        """TTauApprox and TTauParams are distinct types."""
        fr5 = Atomic(ScheduleType(Distribution.FIXED, Domain.RATIO), 5.0)
        approx = approximate_ttau(fr5, irt=2.0)
        exact = TTauParams(T=10.0, tau=10.0)

        assert type(approx) is not type(exact)

    def test_interval_also_works(self) -> None:
        """approximate_ttau accepts Interval schedules too (for comparison)."""
        fi30 = Atomic(ScheduleType(Distribution.FIXED, Domain.INTERVAL), 30.0)
        result = approximate_ttau(fi30, irt=1.0)
        assert result.T == pytest.approx(30.0)
