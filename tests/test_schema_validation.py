"""JSON Schema validation tests for serialized AST outputs.

Validates that the output of :func:`contingency_dsl.to_dict` conforms to
``schema/operant/ast.schema.json`` for the subset of node types that are
declared in the schema. Nodes not present in the schema
(``AdjustingSchedule``, ``InterlockingSchedule``, ``TrialBased``,
``TimeoutWrapped``, ``ResponseCostWrapped``) are excluded via a
pre-filter — a known schema-implementation gap tracked separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from contingency_dsl import parse, to_dict

SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "contingency-dsl"
    / "schema"
    / "operant"
    / "ast.schema.json"
)


if not SCHEMA_PATH.exists():
    pytest.skip(f"schema not found: {SCHEMA_PATH}", allow_module_level=True)


_SCHEMA = json.loads(SCHEMA_PATH.read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA)


_SCHEMA_DRIFT_TYPES: frozenset[str] = frozenset({
    "AdjustingSchedule",
    "InterlockingSchedule",
    "TrialBased",
    "TimeoutWrapped",
    "ResponseCostWrapped",
    "PhaseSequence",
    "Paper",
    "Experiment",
})


def _has_drift_type(payload: object) -> bool:
    if isinstance(payload, dict):
        if payload.get("type") in _SCHEMA_DRIFT_TYPES:
            return True
        return any(_has_drift_type(v) for v in payload.values())
    if isinstance(payload, list):
        return any(_has_drift_type(item) for item in payload)
    return False


_VALID_SAMPLES = [
    "FR5",
    "VI60s",
    "VT30ms",
    "EXT",
    "CRF",
    "DRL5s",
    "DRH2s",
    "DRO10s",
    "Conc(VI30s, VI60s)",
    "Conc(VI30s, VI60s, COD=2s)",
    "Chain(FR5, FI30s)",
    "Alt(FR10, FI5min)",
    "Mult(FR5, EXT)",
    "Mix(FR5, FR10)",
    "Tand(VR20, DRL5s)",
    "Repeat(3, FR10)",
    "VI60s LH10",
    "PR(hodos)",
    "PR(linear, start=1, increment=2)",
    "PR(exponential)",
    "FR5(FI30)",
    "FI120s(FR10)",
    "let baseline = VI60s\nbaseline",
    "let a = FR5\nlet b = Chain(a, VI30s)\nb",
]


@pytest.mark.parametrize("text", _VALID_SAMPLES)
def test_to_dict_matches_ast_schema(text: str) -> None:
    """Surface-language samples serialize to schema-valid Program dicts."""
    program = parse(text)
    payload = to_dict(program)
    if _has_drift_type(payload):
        pytest.skip("output contains known schema-drift node types")
    errors = sorted(
        _VALIDATOR.iter_errors(payload), key=lambda e: (list(e.path), e.message)
    )
    assert not errors, (
        f"schema validation errors for {text!r}:\n"
        + "\n".join(
            f"  - {list(e.path)}: {e.message}" for e in errors[:5]
        )
    )
