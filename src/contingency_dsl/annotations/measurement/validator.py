"""Validator for measurement annotations.

Enforces constraints defined in measurement.schema.json (v1.2).
Rules are coded directly rather than loaded from JSON at runtime,
matching the pattern used by stimulus_ext.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationDiagnostic:
    """A single validation diagnostic with a code and human-readable message."""

    code: str
    message: str


def validate_session_end(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    """Validate @session_end annotation parameters."""
    diagnostics: list[ValidationDiagnostic] = []
    rule = params.get("rule")

    # rule is required
    if rule is None:
        diagnostics.append(ValidationDiagnostic(
            "SESSION_END_MISSING_PARAM",
            "@session_end requires 'rule' parameter",
        ))
        return diagnostics

    # rule must be a valid enum value
    valid_rules = {"first", "time_only", "reinforcers_only"}
    if rule not in valid_rules:
        diagnostics.append(ValidationDiagnostic(
            "SESSION_END_UNKNOWN_RULE",
            f"@session_end rule must be one of: {', '.join(sorted(valid_rules))}",
        ))
        return diagnostics

    time = params.get("time")
    reinforcers = params.get("reinforcers")

    if rule == "first":
        # required_if rule=first: both time and reinforcers
        if time is None or reinforcers is None:
            diagnostics.append(ValidationDiagnostic(
                "SESSION_END_MISSING_PARAM",
                "@session_end rule='first' requires both 'time' and 'reinforcers'",
            ))
    elif rule == "time_only":
        # required: time; forbidden: reinforcers
        if time is None:
            diagnostics.append(ValidationDiagnostic(
                "SESSION_END_MISSING_PARAM",
                "@session_end rule='time_only' requires 'time'",
            ))
        if reinforcers is not None:
            diagnostics.append(ValidationDiagnostic(
                "SESSION_END_INVALID_COMBO",
                "@session_end rule='time_only' forbids 'reinforcers'",
            ))
    elif rule == "reinforcers_only":
        # required: reinforcers; forbidden: time
        if reinforcers is None:
            diagnostics.append(ValidationDiagnostic(
                "SESSION_END_MISSING_PARAM",
                "@session_end rule='reinforcers_only' requires 'reinforcers'",
            ))
        if time is not None:
            diagnostics.append(ValidationDiagnostic(
                "SESSION_END_INVALID_COMBO",
                "@session_end rule='reinforcers_only' forbids 'time'",
            ))

    return diagnostics


def validate_baseline(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    """Validate @baseline annotation parameters."""
    diagnostics: list[ValidationDiagnostic] = []
    sessions = params.get("pre_training_sessions")

    if sessions is None:
        diagnostics.append(ValidationDiagnostic(
            "BASELINE_INVALID_SESSIONS",
            "@baseline requires 'pre_training_sessions'",
        ))
    elif not isinstance(sessions, (int, float)) or sessions < 1:
        diagnostics.append(ValidationDiagnostic(
            "BASELINE_INVALID_SESSIONS",
            "@baseline pre_training_sessions must be a positive integer",
        ))

    measure = params.get("measure")
    if measure is not None:
        valid_measures = {"operant_level", "no_training", "custom"}
        if measure not in valid_measures:
            diagnostics.append(ValidationDiagnostic(
                "BASELINE_UNKNOWN_MEASURE",
                f"@baseline measure must be one of: {', '.join(sorted(valid_measures))}",
            ))

    return diagnostics


def validate_steady_state(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    """Validate @steady_state annotation parameters."""
    diagnostics: list[ValidationDiagnostic] = []

    window = params.get("window_sessions")
    if window is None:
        diagnostics.append(ValidationDiagnostic(
            "STEADY_STATE_INVALID_WINDOW",
            "@steady_state requires 'window_sessions'",
        ))
    elif not isinstance(window, (int, float)) or window < 2:
        diagnostics.append(ValidationDiagnostic(
            "STEADY_STATE_INVALID_WINDOW",
            "@steady_state window_sessions must be >= 2",
        ))

    max_change = params.get("max_change_pct")
    if max_change is None:
        diagnostics.append(ValidationDiagnostic(
            "STEADY_STATE_NEGATIVE_CHANGE",
            "@steady_state requires 'max_change_pct'",
        ))
    elif not isinstance(max_change, (int, float)) or max_change < 0:
        diagnostics.append(ValidationDiagnostic(
            "STEADY_STATE_NEGATIVE_CHANGE",
            "@steady_state max_change_pct must be non-negative",
        ))

    min_sessions = params.get("min_sessions")
    if min_sessions is not None and window is not None:
        if isinstance(min_sessions, (int, float)) and isinstance(window, (int, float)):
            if min_sessions < window:
                diagnostics.append(ValidationDiagnostic(
                    "STEADY_STATE_INVALID_MIN_SESSIONS",
                    "@steady_state min_sessions must be >= window_sessions",
                ))

    measure = params.get("measure")
    if measure is not None:
        valid_measures = {"rate", "reinforcers", "iri", "latency", "custom"}
        if measure not in valid_measures:
            diagnostics.append(ValidationDiagnostic(
                "STEADY_STATE_UNKNOWN_MEASURE",
                f"@steady_state measure must be one of: {', '.join(sorted(valid_measures))}",
            ))

    return diagnostics


def _diag(code: str, msg: str) -> ValidationDiagnostic:
    return ValidationDiagnostic(code, msg)


def _is_positive(x: Any) -> bool:
    return isinstance(x, (int, float)) and x > 0


def _is_nonneg(x: Any) -> bool:
    return isinstance(x, (int, float)) and x >= 0


def _duration_value(x: Any) -> float | None:
    """Return the numeric component of a duration literal.

    Accepts plain numbers or `{value, time_unit}` dicts produced by the
    parser's annotation object literal.
    """
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        v = x.get("value")
        if isinstance(v, (int, float)):
            return float(v)
    return None


_UNIT_TO_SECONDS: dict[str, float] = {
    "ms": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
}


def _duration_seconds(x: Any) -> float | None:
    """Return a duration value converted to seconds.

    Accepts plain numbers (interpreted as seconds) or `{value, time_unit}`
    dicts. Returns ``None`` for non-duration inputs.
    """
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        v = x.get("value")
        unit = x.get("time_unit")
        if isinstance(v, (int, float)) and isinstance(unit, str):
            factor = _UNIT_TO_SECONDS.get(unit)
            if factor is not None:
                return float(v) * factor
        if isinstance(v, (int, float)):
            return float(v)
    return None


def validate_dependent_measure(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    variables = params.get("variables")
    valid_vars = {
        "rate", "reinforcers", "response_count", "iri", "latency",
        "irt", "prf_pause", "duration", "preference", "choice_ratio",
        "cumulative_responses",
    }
    if isinstance(variables, list):
        if not variables:
            diagnostics.append(_diag(
                "DEPENDENT_MEASURE_EMPTY_VARIABLES",
                "@dependent_measure requires a non-empty 'variables' list",
            ))
        else:
            for v in variables:
                if v not in valid_vars:
                    diagnostics.append(_diag(
                        "DEPENDENT_MEASURE_UNKNOWN_VARIABLE",
                        f"@dependent_measure variable '{v}' is not recognised",
                    ))
    primary = params.get("primary")
    if primary is not None and isinstance(variables, list) and primary not in variables:
        diagnostics.append(_diag(
            "DEPENDENT_MEASURE_PRIMARY_NOT_IN_VARIABLES",
            f"@dependent_measure primary='{primary}' must appear in variables",
        ))
    return diagnostics


def validate_training_volume(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    track = params.get("track")
    valid_metrics = {"sessions", "reinforcers", "time", "responses"}
    if isinstance(track, list):
        if not track:
            diagnostics.append(_diag(
                "TRAINING_VOLUME_EMPTY_TRACK",
                "@training_volume requires a non-empty 'track' list",
            ))
        else:
            for m in track:
                if m not in valid_metrics:
                    diagnostics.append(_diag(
                        "TRAINING_VOLUME_UNKNOWN_METRIC",
                        f"@training_volume metric '{m}' is not recognised",
                    ))
    for key in ("criterion_sessions", "criterion_reinforcers", "criterion_time", "criterion_responses"):
        if key in params and not _is_positive(_duration_value(params[key]) if "_time" in key else params[key]):
            diagnostics.append(_diag(
                "TRAINING_VOLUME_NONPOSITIVE_CRITERION",
                f"@training_volume {key} must be positive",
            ))
    return diagnostics


def validate_microstructure(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    method = params.get("prf_pause_method")
    valid_methods = {"latency_to_first", "latency_to_nth", "quarter_life", "breakpoint"}
    if method is not None and method not in valid_methods:
        diagnostics.append(_diag(
            "MICROSTRUCTURE_UNKNOWN_METHOD",
            f"@microstructure prf_pause_method '{method}' is not recognised",
        ))
    n_val = params.get("prf_pause_n")
    if method == "latency_to_nth" and n_val is None:
        diagnostics.append(_diag(
            "MICROSTRUCTURE_NTH_MISSING",
            "@microstructure prf_pause_method='latency_to_nth' requires prf_pause_n",
        ))
    if method == "latency_to_first" and n_val is not None:
        diagnostics.append(_diag(
            "MICROSTRUCTURE_NTH_FORBIDDEN",
            "@microstructure prf_pause_method='latency_to_first' forbids prf_pause_n",
        ))
    report = params.get("report")
    valid_reports = {
        "irt_distribution", "response_bout", "burst_pause", "rate_histogram",
    }
    if isinstance(report, list):
        for r in report:
            if r not in valid_reports:
                diagnostics.append(_diag(
                    "MICROSTRUCTURE_UNKNOWN_REPORT",
                    f"@microstructure report '{r}' is not recognised",
                ))
    bin_w = _duration_value(params.get("irt_bin_width"))
    if bin_w is not None and bin_w <= 0:
        diagnostics.append(_diag(
            "MICROSTRUCTURE_NONPOSITIVE_BIN",
            "@microstructure irt_bin_width must be positive",
        ))
    threshold = _duration_value(params.get("burst_threshold"))
    if threshold is not None and threshold <= 0:
        diagnostics.append(_diag(
            "MICROSTRUCTURE_NONPOSITIVE_THRESHOLD",
            "@microstructure burst_threshold must be positive",
        ))
    return diagnostics


def validate_phase_end(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    rule = params.get("rule")
    valid_rules = {"all", "any", "first"}
    if rule is not None and rule not in valid_rules:
        diagnostics.append(_diag(
            "PHASE_END_UNKNOWN_RULE",
            f"@phase_end rule='{rule}' is not recognised",
        ))
    stability = params.get("stability")
    valid_stability = {"steady_state", "moving_average", "none"}
    if stability is not None and stability not in valid_stability:
        diagnostics.append(_diag(
            "PHASE_END_UNKNOWN_STABILITY",
            f"@phase_end stability='{stability}' is not recognised",
        ))
    min_sessions = params.get("min_sessions")
    max_sessions = params.get("max_sessions")
    reinforcers = params.get("reinforcers")
    # No criteria specified (other than rule) — PHASE_END_NO_CRITERIA
    if not any(k in params for k in ("min_sessions", "max_sessions", "reinforcers", "stability", "time")):
        diagnostics.append(_diag(
            "PHASE_END_NO_CRITERIA",
            "@phase_end requires at least one stop criterion",
        ))
    if (
        isinstance(min_sessions, (int, float))
        and isinstance(max_sessions, (int, float))
        and max_sessions < min_sessions
    ):
        diagnostics.append(_diag(
            "PHASE_END_MAX_LESS_THAN_MIN",
            "@phase_end max_sessions must be >= min_sessions",
        ))
    if stability == "steady_state":
        # Require companion @steady_state — at this layer we only see this
        # annotation's params; cross-annotation coordination is flagged as
        # MISSING_STEADY_STATE when no corresponding key appears.
        if "_steady_state_present" not in params:
            diagnostics.append(_diag(
                "PHASE_END_MISSING_STEADY_STATE",
                "@phase_end stability='steady_state' requires a companion "
                "@steady_state annotation in the same scope",
            ))
    return diagnostics


def validate_logging(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    events = params.get("events")
    valid_events = {
        "response", "reinforcer", "stimulus", "session_start", "session_end",
        "trial_start", "trial_end", "phase_start", "phase_end",
        "changeover", "punisher", "brief",
    }
    if isinstance(events, list):
        if not events:
            diagnostics.append(_diag(
                "LOGGING_EMPTY_EVENTS",
                "@logging requires a non-empty 'events' list",
            ))
        else:
            for e in events:
                if e not in valid_events:
                    diagnostics.append(_diag(
                        "LOGGING_UNKNOWN_EVENT",
                        f"@logging event '{e}' is not recognised",
                    ))
    fmt = params.get("format")
    valid_formats = {"json", "jsonl", "csv", "tsv"}
    if fmt is not None and fmt not in valid_formats:
        diagnostics.append(_diag(
            "LOGGING_UNKNOWN_FORMAT",
            f"@logging format='{fmt}' is not recognised",
        ))
    precision = params.get("precision")
    valid_precision = {"s", "ms", "us", "ns"}
    if precision is not None and precision not in valid_precision:
        diagnostics.append(_diag(
            "LOGGING_UNKNOWN_PRECISION",
            f"@logging precision='{precision}' is not recognised",
        ))
    return diagnostics


def validate_iri_window(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    normalize = params.get("normalize")
    valid_normalize = {"none", "mean", "max"}
    if normalize is not None and normalize not in valid_normalize:
        diagnostics.append(_diag(
            "IRI_WINDOW_UNKNOWN_NORMALIZE",
            f"@iri_window normalize='{normalize}' is not recognised",
        ))
    report = params.get("report")
    valid_reports = {"mean", "median", "cv", "sd", "min", "max", "quantiles"}
    if isinstance(report, list):
        for r in report:
            if r not in valid_reports:
                diagnostics.append(_diag(
                    "IRI_WINDOW_UNKNOWN_REPORT",
                    f"@iri_window report '{r}' is not recognised",
                ))
    bin_w = _duration_value(params.get("bin_width"))
    if bin_w is not None and bin_w <= 0:
        diagnostics.append(_diag(
            "IRI_WINDOW_NONPOSITIVE_BIN",
            "@iri_window bin_width must be positive",
        ))
    return diagnostics


def validate_warmup_exclude(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    duration_seconds = _duration_seconds(params.get("duration"))
    if duration_seconds is not None and duration_seconds <= 0:
        diagnostics.append(_diag(
            "WARMUP_EXCLUDE_NONPOSITIVE",
            "@warmup_exclude duration must be positive",
        ))
    scope = params.get("scope")
    valid_scopes = {"first_session", "every_session", "trial"}
    if scope is not None and scope not in valid_scopes:
        diagnostics.append(_diag(
            "WARMUP_EXCLUDE_UNKNOWN_SCOPE",
            f"@warmup_exclude scope='{scope}' is not recognised",
        ))
    # Cross-annotation check — session_end duration context is passed via
    # `_session_end_seconds` injected by the caller when available.
    session_end_s = params.get("_session_end_seconds")
    if duration_seconds is not None and isinstance(session_end_s, (int, float)):
        if duration_seconds >= session_end_s:
            diagnostics.append(_diag(
                "WARMUP_EXCLUDE_EXCEEDS_SESSION",
                "@warmup_exclude duration must be less than @session_end time",
            ))
    return diagnostics


def validate_stimulus_classes(
    params: dict[str, Any], positional: Any = None
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    # Positional integer: minimum class count check (must be >= 2).
    if isinstance(positional, (int, float)) and positional < 2:
        diagnostics.append(_diag(
            "STIMULUS_CLASSES_TOO_FEW",
            "@stimulus_classes requires at least 2 classes",
        ))
    # Keyword form: A=["X1",...], B=["X2",...]. Detect duplicate stimuli
    # across classes. Keys that look like class labels are A..Z.
    class_members: dict[str, list[str]] = {}
    for k, v in params.items():
        if isinstance(k, str) and k.isalpha() and k.isupper() and isinstance(v, list):
            class_members[k] = [str(item) for item in v]
    if class_members:
        if len(class_members) < 2:
            diagnostics.append(_diag(
                "STIMULUS_CLASSES_TOO_FEW",
                "@stimulus_classes requires at least 2 classes",
            ))
        seen: dict[str, str] = {}
        for cls, members in class_members.items():
            for m in members:
                if m in seen and seen[m] != cls:
                    diagnostics.append(_diag(
                        "STIMULUS_CLASSES_DUPLICATE_STIMULUS",
                        f"@stimulus_classes stimulus '{m}' appears in both "
                        f"class '{seen[m]}' and class '{cls}'",
                    ))
                else:
                    seen.setdefault(m, cls)
    return diagnostics


def validate_training(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    relations = params.get("relations")
    if isinstance(relations, list) and not relations:
        diagnostics.append(_diag(
            "TRAINING_EMPTY_RELATIONS",
            "@training requires a non-empty 'relations' list",
        ))
    criterion = params.get("criterion")
    if criterion is not None:
        if isinstance(criterion, (int, float)) and (criterion <= 0 or criterion > 100):
            diagnostics.append(_diag(
                "TRAINING_INVALID_CRITERION",
                "@training criterion must be in (0, 100]",
            ))
    block_size = params.get("block_size")
    if block_size is not None and (not isinstance(block_size, (int, float)) or block_size <= 0):
        diagnostics.append(_diag(
            "TRAINING_NONPOSITIVE_BLOCK_SIZE",
            "@training block_size must be positive",
        ))
    return diagnostics


def validate_testing(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    relations = params.get("relations")
    if isinstance(relations, list) and not relations:
        diagnostics.append(_diag(
            "TESTING_EMPTY_RELATIONS",
            "@testing requires a non-empty 'relations' list",
        ))
    probe_ratio = params.get("probe_ratio")
    if probe_ratio is not None and isinstance(probe_ratio, (int, float)):
        if probe_ratio < 0 or probe_ratio > 1:
            diagnostics.append(_diag(
                "TESTING_INVALID_PROBE_RATIO",
                "@testing probe_ratio must be in [0, 1]",
            ))
    criterion = params.get("criterion")
    if criterion is not None:
        if isinstance(criterion, (int, float)) and (criterion <= 0 or criterion > 100):
            diagnostics.append(_diag(
                "TESTING_INVALID_CRITERION",
                "@testing criterion must be in (0, 100]",
            ))
    block_size = params.get("block_size")
    if block_size is not None and (not isinstance(block_size, (int, float)) or block_size <= 0):
        diagnostics.append(_diag(
            "TESTING_NONPOSITIVE_BLOCK_SIZE",
            "@testing block_size must be positive",
        ))
    return diagnostics


def validate_operandum(
    params: dict[str, Any], positional: Any = None, scope: str | None = None
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    physical_keys = {
        "width", "height", "depth", "distance", "force", "weight",
        "model", "manufacturer", "position", "orientation", "material",
    }
    # Schedule-level annotation with physical parameters is disallowed —
    # physical-parameter keys only make sense at program level.
    has_physical = any(k in params for k in physical_keys)
    if scope == "schedule" and has_physical:
        diagnostics.append(_diag(
            "SCHEDULE_ANNOTATION_PHYSICAL_PARAM",
            "physical parameters on @operandum are only allowed at program scope",
        ))
    if scope == "program" and "component" in params:
        diagnostics.append(_diag(
            "PROGRAM_ANNOTATION_COMPONENT",
            "'component=' on @operandum is only valid at schedule scope",
        ))
    return diagnostics


def validate_clock(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    unit = params.get("unit")
    valid_units = {"s", "ms", "min"}
    if unit is not None and unit not in valid_units:
        diagnostics.append(_diag(
            "CLOCK_UNKNOWN_UNIT",
            f"@clock unit='{unit}' is not recognised (valid: s, ms, min)",
        ))
    return diagnostics


def validate_warmup(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    duration = _duration_value(params.get("duration"))
    if duration is not None and duration <= 0:
        diagnostics.append(_diag(
            "WARMUP_NONPOSITIVE_DURATION",
            "@warmup duration must be positive",
        ))
    return diagnostics


def validate_algorithm(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    n = params.get("n")
    if n is not None and (not isinstance(n, (int, float)) or n <= 0):
        diagnostics.append(_diag(
            "ALGORITHM_NONPOSITIVE_N",
            "@algorithm n must be positive",
        ))
    return diagnostics


def validate_deprivation(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    hours = params.get("hours")
    if hours is not None and isinstance(hours, (int, float)) and hours < 0:
        diagnostics.append(_diag(
            "DEPRIVATION_NEGATIVE_HOURS",
            "@deprivation hours must be non-negative",
        ))
    return diagnostics


def validate_n(
    params: dict[str, Any], positional: Any = None
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    val = positional if positional is not None else params.get("n")
    if val is not None and isinstance(val, (int, float)) and val <= 0:
        diagnostics.append(_diag(
            "N_NONPOSITIVE",
            "@n must be positive",
        ))
    return diagnostics


def validate_reinforcer(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    rtype = params.get("type")
    valid_types = {"food", "water", "drug", "social", "token", "activity"}
    if rtype is not None and rtype not in valid_types:
        diagnostics.append(_diag(
            "REINFORCER_UNKNOWN_TYPE",
            f"@reinforcer type='{rtype}' is not recognised",
        ))
    duration = _duration_value(params.get("duration"))
    if duration is not None and duration < 0:
        diagnostics.append(_diag(
            "REINFORCER_NEGATIVE_DURATION",
            "@reinforcer duration must be non-negative",
        ))
    return diagnostics


def validate_brief(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    duration = _duration_value(params.get("duration"))
    if duration is not None and duration < 0:
        diagnostics.append(_diag(
            "BRIEF_NEGATIVE_DURATION",
            "@brief duration must be non-negative",
        ))
    return diagnostics


def validate_session(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    trials = params.get("trials")
    blocks = params.get("blocks")
    block_size = params.get("block_size")
    if not params:
        diagnostics.append(_diag(
            "SESSION_MISSING_PARAM",
            "@session requires at least one of trials / blocks / block_size",
        ))
        return diagnostics
    if trials is not None and isinstance(trials, (int, float)) and trials <= 0:
        diagnostics.append(_diag(
            "SESSION_NONPOSITIVE_TRIALS",
            "@session trials must be positive",
        ))
    if blocks is not None and isinstance(blocks, (int, float)) and blocks <= 0:
        diagnostics.append(_diag(
            "SESSION_NONPOSITIVE_BLOCKS",
            "@session blocks must be positive",
        ))
    if blocks is not None and block_size is None and trials is None:
        diagnostics.append(_diag(
            "SESSION_BLOCKS_WITHOUT_BLOCK_SIZE",
            "@session blocks= requires block_size=",
        ))
    if (
        isinstance(trials, (int, float))
        and isinstance(blocks, (int, float))
        and isinstance(block_size, (int, float))
        and trials != blocks * block_size
    ):
        diagnostics.append(_diag(
            "SESSION_BLOCK_TRIALS_MISMATCH",
            f"@session trials ({trials}) != blocks ({blocks}) * "
            f"block_size ({block_size})",
        ))
    return diagnostics


def validate_probe_policy(params: dict[str, Any]) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    ratio = params.get("probe_ratio")
    if ratio is not None and isinstance(ratio, (int, float)):
        if ratio < 0 or ratio > 1:
            diagnostics.append(_diag(
                "PROBE_POLICY_INVALID_RATIO",
                "@probe_policy probe_ratio must be in [0, 1]",
            ))
    order = params.get("order")
    valid_orders = {"random", "blocked", "progressive"}
    if order is not None and order not in valid_orders:
        diagnostics.append(_diag(
            "PROBE_POLICY_UNKNOWN_ORDER",
            f"@probe_policy order='{order}' is not recognised",
        ))
    interspersed = params.get("interspersed")
    if interspersed is True and order == "blocked":
        diagnostics.append(_diag(
            "PROBE_POLICY_INCONSISTENT_INTERSPERSED_ORDER",
            "@probe_policy interspersed=true is inconsistent with order='blocked'",
        ))
    return diagnostics


# Dispatch table: keyword -> validator function. Positional-accepting
# validators are wrapped at dispatch time so the common
# `validator(params)` signature is preserved for legacy callers.
KEYWORD_VALIDATORS: dict[str, Any] = {
    "session_end": validate_session_end,
    "baseline": validate_baseline,
    "steady_state": validate_steady_state,
    "dependent_measure": validate_dependent_measure,
    "training_volume": validate_training_volume,
    "microstructure": validate_microstructure,
    "phase_end": validate_phase_end,
    "logging": validate_logging,
    "iri_window": validate_iri_window,
    "warmup_exclude": validate_warmup_exclude,
    "training": validate_training,
    "testing": validate_testing,
    "clock": validate_clock,
    "warmup": validate_warmup,
    "algorithm": validate_algorithm,
    "deprivation": validate_deprivation,
    "reinforcer": validate_reinforcer,
    "brief": validate_brief,
    "session": validate_session,
    "probe_policy": validate_probe_policy,
}


def validate_measurement_annotation(
    keyword: str,
    params: dict[str, Any],
    *,
    positional: Any = None,
    scope: str | None = None,
) -> list[ValidationDiagnostic]:
    """Validate a single annotation by keyword.

    `positional` is the positional argument of the annotation (e.g., the
    label in `@n(5)`); `scope` is `"program"` / `"schedule"` / `None` for
    scope-sensitive keywords like `@operandum`.
    """
    # Keywords needing positional or scope information.
    if keyword == "stimulus_classes":
        return validate_stimulus_classes(params, positional=positional)
    if keyword == "n":
        return validate_n(params, positional=positional)
    if keyword == "operandum":
        return validate_operandum(params, positional=positional, scope=scope)

    validator = KEYWORD_VALIDATORS.get(keyword)
    if validator is None:
        return []
    return validator(params)
