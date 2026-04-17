"""Conformance test runner: validates parser against the language-independent test suite.

Reads JSON test cases from ../contingency-dsl/conformance/ and runs them
through the Python parser, comparing output against expected AST dicts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contingency_dsl import parse, analyze, to_dict
from contingency_dsl.errors import DslError, LexError, ParseError, SemanticError

CONFORMANCE_DIR = Path(__file__).parent.parent.parent / "contingency-dsl" / "conformance"

# Map error type strings to exception classes
ERROR_TYPE_MAP = {
    "ParseError": ParseError,
    "LexError": LexError,
    "SemanticError": SemanticError,
}


def _load_test_cases(filename: str) -> list[dict]:
    path = CONFORMANCE_DIR / filename
    if not path.exists():
        pytest.skip(f"conformance file not found: {path}")
    with open(path) as f:
        return json.load(f)


def _collect_conformance_cases():
    """Collect all (file, case) pairs for parametrize.

    Searches subdirectories (foundations/, operant/, operant/stateful/, operant/trial-based/,
    respondent/, composed/, experiment/, annotations/) recursively.
    representations/ is excluded — handled by test_t_tau_conversion.py.
    """
    cases = []
    if not CONFORMANCE_DIR.exists():
        return cases
    for json_file in sorted(CONFORMANCE_DIR.rglob("*.json")):
        # representations/ has its own test module (test_t_tau_conversion.py)
        if "representations" in json_file.relative_to(CONFORMANCE_DIR).parts:
            continue
        rel_path = str(json_file.relative_to(CONFORMANCE_DIR))
        data = json.loads(json_file.read_text())
        for case in data:
            if "id" not in case:
                continue  # skip comment-only entries (e.g. _comment)
            cases.append((rel_path, case))
    return cases


ALL_CASES = _collect_conformance_cases()


@pytest.mark.parametrize(
    "filename,case",
    ALL_CASES,
    ids=[f"{fn}::{c['id']}" for fn, c in ALL_CASES],
)
def test_conformance(filename: str, case: dict) -> None:
    test_id = case["id"]
    input_text = case["input"]

    if "error" in case:
        # Error case
        error_info = case["error"]
        expected_type = ERROR_TYPE_MAP.get(error_info["type"], DslError)

        with pytest.raises(DslError):
            program = parse(input_text)
            # Some errors only surface during analysis
            if error_info["type"] == "SemanticError":
                analyze(program)
        return

    # Success case
    program = parse(input_text)
    actual_dict = to_dict(program)
    analysis_result = None

    if "pre_expansion" in case:
        # Compare pre-expansion AST
        _assert_ast_match(actual_dict, case["pre_expansion"], test_id, "pre_expansion")

    if "expected" in case:
        # If the expected has empty bindings but program has bindings,
        # or if pre_expansion is present, run analyzer for post-expansion
        expected_bindings = case["expected"].get("bindings", [])
        has_bindings = len(program.bindings) > 0
        if "pre_expansion" in case or (has_bindings and len(expected_bindings) == 0):
            analysis_result = analyze(program)
            actual_dict = to_dict(analysis_result.program)
        _assert_ast_match(actual_dict, case["expected"], test_id, "expected")

    if "warnings" in case:
        if analysis_result is None:
            analysis_result = analyze(program)
        for expected_code in case["warnings"]:
            assert any(
                expected_code in w for w in analysis_result.warnings
            ), (
                f"[{test_id}] expected warning containing '{expected_code}', "
                f"got: {analysis_result.warnings}"
            )


def _assert_ast_match(actual: dict, expected: dict, test_id: str, label: str) -> None:
    """Deep-compare two AST dicts, with helpful error messages."""
    _compare(actual, expected, path=f"[{test_id}:{label}]")


def _compare(actual, expected, path: str = "") -> None:
    """Recursively compare values, ignoring key order in dicts."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual).__name__}"
        for key in expected:
            assert key in actual, f"{path}: missing key '{key}' in actual (has: {list(actual.keys())})"
            _compare(actual[key], expected[key], path=f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual).__name__}"
        assert len(actual) == len(expected), f"{path}: list length {len(actual)} != {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected)):
            _compare(a, e, path=f"{path}[{i}]")
    elif isinstance(expected, float):
        assert isinstance(actual, (int, float)), f"{path}: expected number, got {type(actual).__name__}"
        assert float(actual) == expected, f"{path}: {actual} != {expected}"
    elif expected is None:
        assert actual is None, f"{path}: expected None, got {actual!r}"
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
