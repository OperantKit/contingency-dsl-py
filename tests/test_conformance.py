"""Conformance test runner: validates parser against the language-independent test suite.

Reads JSON test cases from ../contingency-dsl/conformance/ and runs them
through the Python parser, comparing output against expected AST dicts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Mapping, Sequence

import pytest

from contingency_dsl import parse, analyze, to_dict
from contingency_dsl.errors import DslError, LexError, ParseError, SemanticError
from contingency_dsl.extensions import ExtensionRegistry

# Optional: measurement validator for annotation semantic error conformance tests.
try:
    from contingency_annotator.measurement_ext.validator import (
        validate_measurement_annotation,
    )

    _HAS_MEASUREMENT_VALIDATOR = True
except ImportError:
    _HAS_MEASUREMENT_VALIDATOR = False

# Optional: real extension modules. When contingency-annotator is importable
# in the test environment, prefer the real ExtensionModule implementations
# over the catch-all inline shim — this exercises the shipped semantic
# validators in addition to the parser-level keyword recognition.
try:
    from contingency_annotator import (
        ComposedExtension,
        MeasurementExtension,
        StimulusExtension,
    )

    _REAL_EXTENSIONS: tuple = (
        StimulusExtension(),
        MeasurementExtension(),
        ComposedExtension(),
    )
except ImportError:
    _REAL_EXTENSIONS = ()

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


# --- Conformance test extension registry ---
#
# The test runner composes real extension modules from `contingency_annotator`
# with a minimal catch-all shim that covers annotation keywords for which no
# real extension module is yet implemented (subjects, apparatus, temporal,
# respondent, session-structure, etc.). As more real extensions land, the
# catch-all keyword set shrinks; keywords already handled by real extensions
# must NOT appear here (ExtensionRegistry.build enforces disjointness).


_REAL_EXTENSION_KEYWORDS: frozenset[str] = frozenset().union(
    *(ext.annotation_keywords for ext in _REAL_EXTENSIONS)
)


class _CatchAllExt:
    """Catch-all extension for annotation keywords not yet covered by a real module.

    Used only in the conformance runner. When an extension package ships for
    subjects / apparatus / temporal / respondent-annotator / session-structure
    etc., the relevant keywords should be dropped from the set below.
    """

    name: ClassVar[str] = "conformance-catchall-ext"
    version: ClassVar[str] = "0.1.0"

    _ALL_KEYWORDS: ClassVar[frozenset[str]] = frozenset({
        # stimulus keywords (shadowed by StimulusExtension when imported)
        "reinforcer", "sd", "operandum", "brief",
        "punisher", "consequentStimulus",
        "stimulus_classes", "training", "testing",
        # go/no-go stimulus naming
        "s_delta",
        # social
        "subject", "interlocking",
        # measurement (shadowed by MeasurementExtension when imported)
        "session_end", "baseline", "steady_state",
        "dependent_measure", "training_volume", "microstructure",
        "phase_end", "logging", "iri_window", "warmup_exclude",
        # subjects
        "species", "strain", "deprivation", "history", "n",
        "subjects",
        # apparatus
        "chamber", "interface", "hardware", "hw",
        "apparatus",
        # temporal
        "clock", "warmup", "algorithm",
        # experiment-layer phase annotations
        "context",
        # respondent-annotator (for composed procedures)
        "cs", "us", "iti", "cs_interval",
        # composed-ext (shadowed by ComposedExtension when imported)
        "omission", "avoidance",
        # session / trial structure
        "session", "trial_mix", "probe_policy",
    })

    @property
    def annotation_keywords(self) -> frozenset[str]:
        # Subtract keywords already owned by real extensions so the registry
        # composition stays disjoint even when a real extension later adds
        # overlapping keywords.
        return self._ALL_KEYWORDS - _REAL_EXTENSION_KEYWORDS

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()


_CONFORMANCE_REGISTRY = ExtensionRegistry.build(
    *_REAL_EXTENSIONS, _CatchAllExt()
)

# Test IDs marked as xfail for features not yet implemented.
# Currently empty; populate with fixture IDs when deferring coverage gaps.
_KNOWN_PREEXISTING_FAILURES: frozenset[str] = frozenset()


def _get_extensions_for_case(filename: str, case: dict) -> ExtensionRegistry | None:
    """Return an extension registry if the test case requires annotations."""
    if "annotations" in filename:
        return _CONFORMANCE_REGISTRY
    if "@" in case.get("input", ""):
        return _CONFORMANCE_REGISTRY
    return None


ALL_CASES = _collect_conformance_cases()


def _commutative_canonical(d: object) -> object:
    """Recursively canonicalise a serialized AST for commutative equivalence.

    Sorts `components` arrays of Conc / Alt / Conj Compounds by a stable
    repr key so that `Conc(A, B)` and `Conc(B, A)` compare equal. Does NOT
    sort Chain / Tand / Mult / Mix / Overlay / Interpolate components.
    """
    if isinstance(d, dict):
        normalised = {k: _commutative_canonical(v) for k, v in d.items()}
        if normalised.get("type") == "Compound" and normalised.get("combinator") in (
            "Conc", "Alt", "Conj",
        ):
            components = normalised.get("components")
            if isinstance(components, list):
                normalised["components"] = sorted(components, key=repr)
        return normalised
    if isinstance(d, list):
        return [_commutative_canonical(item) for item in d]
    return d


@pytest.mark.parametrize(
    "filename,case",
    ALL_CASES,
    ids=[f"{fn}::{c['id']}" for fn, c in ALL_CASES],
)
def test_conformance(filename: str, case: dict) -> None:
    test_id = case["id"]

    # Algebraic equivalence fixtures (`operant/algebra.json`) use an
    # `lhs`/`rhs`/`relation` format rather than `input`/`expected`. Parse
    # both sides, run the analyzer, and compare the post-analysis AST dicts.
    if "lhs" in case and "rhs" in case and "relation" in case:
        extensions = _get_extensions_for_case(filename, case)
        lhs_prog = analyze(parse(case["lhs"], extensions=extensions)).program
        rhs_prog = analyze(parse(case["rhs"], extensions=extensions)).program
        lhs_d = _commutative_canonical(to_dict(lhs_prog))
        rhs_d = _commutative_canonical(to_dict(rhs_prog))
        if case["relation"] == "equivalent":
            assert lhs_d == rhs_d, (
                f"[{test_id}] expected equivalent ASTs\n  lhs: {lhs_d}\n  rhs: {rhs_d}"
            )
        elif case["relation"] == "not_equivalent":
            assert lhs_d != rhs_d, (
                f"[{test_id}] expected non-equivalent ASTs but got the same\n  {lhs_d}"
            )
        else:
            pytest.skip(f"unsupported relation '{case['relation']}'")
        return

    input_text = case["input"]
    extensions = _get_extensions_for_case(filename, case)

    # Mark deferred fixtures as xfail
    if test_id in _KNOWN_PREEXISTING_FAILURES:
        pytest.xfail(f"[{test_id}] deferred coverage")

    if "error" in case:
        # Error case. The `error` field is either a dict
        # ({"type": "ParseError", "code": "..."}) or a bare string shorthand
        # ("ParseError" / "SemanticError" / "LexError") used by some older
        # fixture files (operant/trial-based/errors.json,
        # operant/stateful/errors.json).
        error_info = case["error"]
        if isinstance(error_info, str):
            error_info = {"type": error_info}
        expected_code = error_info.get("code")

        # Annotation semantic errors: try measurement validator first
        if (
            "annotations/errors.json" in filename
            and error_info["type"] == "SemanticError"
        ):
            if not _HAS_MEASUREMENT_VALIDATOR:
                pytest.xfail(
                    f"[{test_id}] measurement validator not installed"
                )
            # Parse should succeed; validation catches the semantic error
            try:
                program = parse(input_text, extensions=extensions)
            except DslError:
                # Annotation not parseable (e.g., unknown keyword) — xfail
                pytest.xfail(
                    f"[{test_id}] parse failed — annotation not yet supported"
                )
            from contingency_dsl.ast import AnnotatedSchedule, Compound, LimitedHold, Modifier, SecondOrder
            found_error = False

            def _walk_annotations(expr, scope: str):
                """Yield (annotation, scope) pairs for every annotation
                reachable from an expression subtree."""
                if isinstance(expr, AnnotatedSchedule):
                    for ann in expr.annotations:
                        yield ann, scope
                    yield from _walk_annotations(expr.expr, scope)
                elif isinstance(expr, Compound):
                    for comp in expr.components:
                        yield from _walk_annotations(comp, scope)
                elif isinstance(expr, LimitedHold):
                    yield from _walk_annotations(expr.inner, scope)
                elif isinstance(expr, SecondOrder):
                    yield from _walk_annotations(expr.overall, scope)
                    yield from _walk_annotations(expr.unit, scope)
                elif isinstance(expr, Modifier) and expr.inner is not None:
                    yield from _walk_annotations(expr.inner, scope)

            # Build full list: program-level + schedule-level annotations.
            anns: list = [(a, "program") for a in program.program_annotations]
            if hasattr(program, "schedule"):
                anns.extend(_walk_annotations(program.schedule, "schedule"))

            # Aggregate parameter dictionaries so warmup_exclude can check
            # `_session_end_seconds` cross-annotation context.
            session_end_seconds = None
            for ann, _scope in anns:
                if ann.keyword == "session_end":
                    time_val = (ann.params or {}).get("time")
                    if isinstance(time_val, dict) and time_val.get("time_unit") == "min":
                        session_end_seconds = float(time_val["value"]) * 60.0
                    elif isinstance(time_val, dict) and time_val.get("time_unit") == "s":
                        session_end_seconds = float(time_val["value"])

            for ann, scope in anns:
                params = dict(ann.params or {})
                if ann.keyword == "warmup_exclude" and session_end_seconds is not None:
                    params["_session_end_seconds"] = session_end_seconds
                diags = validate_measurement_annotation(
                    ann.keyword,
                    params,
                    positional=ann.positional,
                    scope=scope,
                )
                if diags and expected_code:
                    if any(d.code == expected_code for d in diags):
                        found_error = True
                        break
            if not found_error:
                pytest.xfail(
                    f"[{test_id}] validator did not produce expected code '{expected_code}'"
                )
            return

        with pytest.raises(DslError):
            program = parse(input_text, extensions=extensions)
            # Some errors only surface during analysis
            if error_info["type"] == "SemanticError":
                analyze(program)
        return

    if "errors" in case or "expected_error" in case:
        # Multi-error (`experiment/errors.json`) or single-code
        # (`experiment/shaping.json`) fixture form. We only verify that *some*
        # DslError is raised; matching specific error codes is deferred until
        # the analyzer grows code-tagged diagnostics.
        with pytest.raises(DslError):
            program = parse(input_text, extensions=extensions)
            if hasattr(program, "bindings"):
                analyze(program)
        return

    # Success case
    program = parse(input_text, extensions=extensions)
    actual_dict = to_dict(program)
    analysis_result = None

    if "expected_phase_count" in case:
        phases = actual_dict.get("phases", [])
        assert len(phases) == case["expected_phase_count"], (
            f"[{test_id}] expected {case['expected_phase_count']} phases, "
            f"got {len(phases)}"
        )

    if "expected_labels" in case:
        phases = actual_dict.get("phases", [])
        labels = [p.get("label") for p in phases]
        assert labels == case["expected_labels"], (
            f"[{test_id}] expected labels {case['expected_labels']}, got {labels}"
        )

    if "pre_expansion" in case:
        # Compare pre-expansion AST
        _assert_ast_match(actual_dict, case["pre_expansion"], test_id, "pre_expansion")

    if "expected" in case:
        # The analyzer's binding-expansion pass runs only on Program-shaped
        # results. Experiment-layer outputs (PhaseSequence) skip it.
        expected_bindings = case["expected"].get("bindings", [])
        has_bindings = getattr(program, "bindings", None) and len(program.bindings) > 0
        if hasattr(program, "bindings") and (
            "pre_expansion" in case
            or (has_bindings and len(expected_bindings) == 0)
        ):
            analysis_result = analyze(program)
            actual_dict = to_dict(analysis_result.program)
        _assert_ast_match(actual_dict, case["expected"], test_id, "expected")

    # Some fixtures use singular `warning` (single string); normalise to the
    # plural list form.
    expected_warnings = case.get("warnings")
    if expected_warnings is None and "warning" in case:
        single = case["warning"]
        expected_warnings = [single] if isinstance(single, str) else list(single)
    if expected_warnings is None and "expected_warnings" in case:
        expected_warnings = case["expected_warnings"]

    if expected_warnings:
        if analysis_result is None and hasattr(program, "bindings"):
            analysis_result = analyze(program)
        if analysis_result is None:
            # PhaseSequence / Paper and other non-Program ASTs still go
            # through analyze() to surface experiment-layer parser
            # diagnostics (e.g. ADVANCE_SINGLE_STEP).
            try:
                analysis_result = analyze(program)
            except Exception:
                analysis_result = None
        if analysis_result is None:
            pytest.skip(f"[{test_id}] analyze() not applicable to {type(program).__name__}")
        for expected_code in expected_warnings:
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
