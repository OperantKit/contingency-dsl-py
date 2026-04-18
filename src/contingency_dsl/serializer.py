"""Serializer: AST <-> dict (JSON-compatible).

Produces dicts matching the conformance test suite format (ast-schema.json).
"""

from __future__ import annotations

from .ast import (
    AnnotatedSchedule,
    Annotation,
    Atomic,
    AversiveSchedule,
    Binding,
    CombinatorParamValue,
    Compound,
    CompoundParam,
    DirectionalCOD,
    DirectionalEntry,
    IdentifierRef,
    LimitedHold,
    Modifier,
    ParamDecl,
    Program,
    ScheduleExpr,
    ScheduleType,
    SecondOrder,
    Special,
    AdjustingSchedule,
    InterlockingSchedule,
    ResponseCost,
    ResponseCostWrapped,
    Timeout,
    TimeoutWrapped,
    TrialBased,
)
from .enums import Combinator, Distribution, Domain
from .experiment import (
    Criterion,
    CumulativeReinforcements,
    Experiment,
    ExperimenterJudgment,
    FixedSessions,
    Paper,
    PerformanceCriterion,
    Phase,
    PhaseRef,
    PhaseSchedule,
    PhaseSequence,
    Stability,
)
from .respondent import (
    CSOnly,
    Compound as RespondentCompound,
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


def to_dict(program: Program | PhaseSequence | Paper) -> dict:
    """Serialize a Program, PhaseSequence, or Paper AST to a dict."""
    if isinstance(program, Paper):
        return _paper_to_dict(program)
    if isinstance(program, PhaseSequence):
        return _phase_sequence_to_dict(program)
    # Hoist annotations attached directly to the top-level schedule to a
    # Program-level `annotations` field, matching the fixture convention
    # (schema/operant/ast.schema.json: schedule-level annotations attach to
    # the leaf, but the top-level DSL expression's trailing annotations are
    # program-scoped).
    schedule = program.schedule
    hoisted_annotations: list = []
    # Only hoist when the wrapped schedule is a stateful / trial-based /
    # modifier leaf. Simple Atomic / Compound / LimitedHold / AversiveSchedule
    # / ResponseCostWrapped / Respondent primitives keep the inline leaf-
    # annotations convention per their respective fixtures.
    _HOISTABLE = (
        AdjustingSchedule, InterlockingSchedule, Modifier, TrialBased,
    )
    if isinstance(schedule, AnnotatedSchedule) and isinstance(schedule.expr, _HOISTABLE):
        inner = schedule.expr
        # Declaration-mode MTS (with `samples`) keeps annotations inline on
        # the schedule — training/testing fixtures attach to the declared
        # stimulus structure, not to the program.
        if isinstance(inner, TrialBased) and "samples" in inner.params:
            pass
        else:
            hoisted_annotations = [_annotation_to_dict(a) for a in schedule.annotations]
            schedule = inner
    d: dict = {
        "type": "Program",
        "program_annotations": [_annotation_to_dict(a) for a in program.program_annotations],
        "param_decls": [_param_decl_to_dict(x) for x in program.param_decls],
        "bindings": [_binding_to_dict(b) for b in program.bindings],
        "schedule": _expr_to_dict(schedule),
    }
    if hoisted_annotations:
        d["annotations"] = hoisted_annotations
    return d


def _phase_sequence_to_dict(seq: PhaseSequence) -> dict:
    d: dict = {
        "type": "PhaseSequence",
        "shared_annotations": [
            _annotation_to_dict(a) for a in seq.shared_annotations
        ],
        "shared_param_decls": [],
        "phases": [_phase_to_dict(p) for p in seq.phases],
    }
    return d


def _paper_to_dict(paper: Paper) -> dict:
    d: dict = {
        "type": "Paper",
        "shared_annotations": [
            _annotation_to_dict(a) for a in paper.shared_annotations
        ],
        "experiments": [_experiment_to_dict(e) for e in paper.experiments],
    }
    return d


def _experiment_to_dict(exp: Experiment) -> dict:
    body = exp.body
    if isinstance(body, PhaseSequence):
        body_dict = _phase_sequence_to_dict(body)
    else:
        body_dict = to_dict(body)
    return {
        "type": "Experiment",
        "label": exp.label,
        "body": body_dict,
    }


def _phase_to_dict(phase: Phase) -> dict:
    d: dict = {"type": "Phase", "label": phase.label}
    if phase.criterion is not None:
        d["criterion"] = _criterion_to_dict(phase.criterion)
    d["schedule"] = _phase_schedule_to_dict(phase.schedule)
    if phase.phase_annotations:
        d["phase_annotations"] = [
            _annotation_to_dict(a) for a in phase.phase_annotations
        ]
    return d


def _phase_schedule_to_dict(sched: PhaseSchedule) -> dict | None:
    if sched is None:
        return None
    if isinstance(sched, PhaseRef):
        return {"type": "PhaseRef", "ref": sched.ref}
    return _expr_to_dict(sched)


def _criterion_to_dict(criterion: Criterion) -> dict:
    if isinstance(criterion, FixedSessions):
        return {"type": "FixedSessions", "count": criterion.count}
    if isinstance(criterion, Stability):
        d: dict = {"type": "Stability", "method": criterion.method}
        if criterion.min_sessions is not None:
            d["min_sessions"] = criterion.min_sessions
        if criterion.window_sessions is not None:
            d["window_sessions"] = criterion.window_sessions
        if criterion.max_change_pct is not None:
            d["max_change_pct"] = criterion.max_change_pct
        if criterion.measure is not None:
            d["measure"] = criterion.measure
        return d
    if isinstance(criterion, ExperimenterJudgment):
        return {"type": "ExperimenterJudgment"}
    if isinstance(criterion, CumulativeReinforcements):
        return {"type": "CumulativeReinforcements", "count": criterion.count}
    if isinstance(criterion, PerformanceCriterion):
        d = {
            "type": "PerformanceCriterion",
            "measure": criterion.measure,
            "threshold": criterion.threshold,
            "op": criterion.op,
        }
        if criterion.window_sessions is not None:
            d["window_sessions"] = criterion.window_sessions
        return d
    raise ValueError(f"unknown criterion: {criterion!r}")


def _expr_to_dict(expr: ScheduleExpr) -> dict:
    """Serialize a ScheduleExpr to dict."""
    match expr:
        case Atomic(schedule_type=st, value=val, time_unit=unit):
            d: dict = {
                "type": "Atomic",
                "dist": st.distribution.value,
                "domain": st.domain.value,
                "value": val,
            }
            if unit is not None:
                d["time_unit"] = unit
            return d

        case Special(kind=kind):
            return {"type": "Special", "kind": kind}

        case Compound(combinator=comb, components=components, params=params):
            d: dict = {
                "type": "Compound",
                "combinator": comb.value,
                "components": [_expr_to_dict(c) for c in components],
            }
            if params:
                d["params"] = {
                    k: _param_value_to_dict(v) for k, v in params.items()
                }
            return d

        case Modifier(modifier=mod):
            d = {"type": "Modifier", "modifier": mod}
            if expr.value is not None:
                d["value"] = expr.value
            if expr.time_unit is not None:
                d["time_unit"] = expr.time_unit
            if expr.inner is not None:
                d["inner"] = _expr_to_dict(expr.inner)
            if expr.pr_step is not None:
                d["pr_step"] = expr.pr_step
            if expr.pr_start is not None:
                d["pr_start"] = expr.pr_start
            if expr.pr_increment is not None:
                d["pr_increment"] = expr.pr_increment
            if expr.pr_ratio is not None:
                d["pr_ratio"] = expr.pr_ratio
            if expr.pctl_target is not None:
                d["pctl_target"] = expr.pctl_target
            if expr.pctl_rank is not None:
                d["pctl_rank"] = expr.pctl_rank
            if expr.pctl_window is not None:
                d["pctl_window"] = expr.pctl_window
            if expr.pctl_dir is not None:
                d["pctl_dir"] = expr.pctl_dir
            if expr.length is not None:
                d["length"] = expr.length
            return d

        case LimitedHold(hold_duration=dur, inner=inner, time_unit=unit):
            # Per schema/operant/ast.schema.json, LimitedHold is a leaf-level
            # attribute (`limitedHold`, `limitedHoldUnit`) rather than a
            # wrapper node. Flatten when the inner expression is a leaf that
            # the schema admits.
            inner_dict = _expr_to_dict(inner)
            if isinstance(
                inner,
                (Atomic, Special, Modifier, SecondOrder, AdjustingSchedule,
                 InterlockingSchedule, AversiveSchedule, TrialBased),
            ):
                inner_dict["limitedHold"] = dur
                if unit is not None:
                    inner_dict["limitedHoldUnit"] = unit
                return inner_dict
            # Fallback: wrapper node for non-leaf inners (e.g. Compound).
            d = {
                "type": "LimitedHold",
                "hold_duration": dur,
                "inner": inner_dict,
            }
            if unit is not None:
                d["time_unit"] = unit
            return d

        case SecondOrder(overall=overall, unit=unit):
            return {
                "type": "SecondOrder",
                "overall": _expr_to_dict(overall),
                "unit": _expr_to_dict(unit),
            }

        case IdentifierRef(name=name):
            return {"type": "IdentifierRef", "name": name}

        case AversiveSchedule(kind=kind, params=params):
            return {
                "type": "AversiveSchedule",
                "kind": kind,
                "params": dict(params),
            }

        case AdjustingSchedule(
            adj_target=target, adj_start=start, adj_step=step,
            adj_min=mn, adj_max=mx,
        ):
            return {
                "type": "AdjustingSchedule",
                "adj_target": target,
                "adj_start": start,
                "adj_step": step,
                "adj_min": mn,
                "adj_max": mx,
            }

        case InterlockingSchedule(interlock_R0=r0, interlock_T=t):
            return {
                "type": "InterlockingSchedule",
                "interlock_R0": r0,
                "interlock_T": t,
            }

        case TrialBased(trial_type=tt, params=p):
            # Declaration-mode MTS (stimulus-class / training / testing
            # contexts) uses `MTS(samples=N, comparisons=M)` shape and
            # serialises with `type: "MTS"` and a nested `params` object.
            if tt == "MTS" and "samples" in p:
                return {
                    "type": "MTS",
                    "params": {
                        k: (_expr_to_dict(v) if hasattr(v, "__dataclass_fields__") else v)
                        for k, v in p.items()
                        if k in ("samples", "comparisons")
                    },
                }
            out: dict = {"type": "TrialBased", "trial_type": tt}
            for k, v in p.items():
                if hasattr(v, "__dataclass_fields__"):
                    out[k] = _expr_to_dict(v)  # type: ignore[arg-type]
                else:
                    out[k] = v
            return out

        case TimeoutWrapped(inner=inner, timeout=t):
            # Flatten onto leaf per ast.schema.json §timeout.
            inner_dict = _expr_to_dict(inner)
            timeout_dict: dict = {"duration": t.duration}
            if t.duration_unit is not None:
                timeout_dict["durationUnit"] = t.duration_unit
            timeout_dict["resetOnResponse"] = t.reset_on_response
            inner_dict["timeout"] = timeout_dict
            return inner_dict

        case ResponseCostWrapped(inner=inner, response_cost=rc):
            # Flatten onto leaf per ast.schema.json §responseCost.
            inner_dict = _expr_to_dict(inner)
            inner_dict["responseCost"] = {"amount": rc.amount, "unit": rc.unit}
            return inner_dict

        case AnnotatedSchedule(expr=inner, annotations=anns):
            # Per schema/operant/ast.schema.json, schedule-level annotations
            # attach as an `annotations` property on the leaf schedule node
            # rather than wrapping it. Flatten into supported leaf shapes.
            inner_dict = _expr_to_dict(inner)
            if isinstance(
                inner,
                (Atomic, Special, Modifier, SecondOrder, LimitedHold, Compound,
                 AdjustingSchedule, InterlockingSchedule, AversiveSchedule,
                 TrialBased, TimeoutWrapped, ResponseCostWrapped),
            ):
                ann_list = [_annotation_to_dict(a) for a in anns]
                existing = inner_dict.get("annotations")
                if existing:
                    inner_dict["annotations"] = ann_list + existing
                else:
                    inner_dict["annotations"] = ann_list
                return inner_dict
            return {
                "type": "AnnotatedSchedule",
                "expr": inner_dict,
                "annotations": [_annotation_to_dict(a) for a in anns],
            }

        case PairForwardDelay(cs=cs, us=us, isi=isi, cs_duration=csd):
            return {
                "type": "PairForwardDelay",
                "cs": cs,
                "us": us,
                "isi": _duration_to_dict(isi),
                "cs_duration": _duration_to_dict(csd),
            }

        case PairForwardTrace(cs=cs, us=us, trace_interval=ti, cs_duration=csd):
            d = {
                "type": "PairForwardTrace",
                "cs": cs,
                "us": us,
                "trace_interval": _duration_to_dict(ti),
            }
            if csd is not None:
                d["cs_duration"] = _duration_to_dict(csd)
            return d

        case PairSimultaneous(cs=cs, us=us):
            return {"type": "PairSimultaneous", "cs": cs, "us": us}

        case PairBackward(us=us, cs=cs, isi=isi):
            return {
                "type": "PairBackward",
                "us": us,
                "cs": cs,
                "isi": _duration_to_dict(isi),
            }

        case Extinction(cs=cs):
            return {"type": "Extinction", "cs": cs}

        case CSOnly(cs=cs, trials=trials):
            return {"type": "CSOnly", "cs": cs, "trials": trials}

        case USOnly(us=us, trials=trials):
            return {"type": "USOnly", "us": us, "trials": trials}

        case Contingency(p_us_given_cs=p1, p_us_given_no_cs=p2):
            return {
                "type": "Contingency",
                "p_us_given_cs": p1,
                "p_us_given_no_cs": p2,
            }

        case TrulyRandom(cs=cs, us=us, p=p):
            d = {"type": "TrulyRandom", "cs": cs, "us": us}
            if p is not None:
                d["p"] = p
            return d

        case ExplicitlyUnpaired(cs=cs, us=us, min_separation=ms):
            d = {"type": "ExplicitlyUnpaired", "cs": cs, "us": us}
            if ms is not None:
                d["min_separation"] = _duration_to_dict(ms)
            return d

        case RespondentCompound(cs_list=cs_list, mode=mode):
            return {
                "type": "Compound",
                "cs_list": list(cs_list),
                "mode": mode,
            }

        case Serial(cs_list=cs_list, isi=isi):
            return {
                "type": "Serial",
                "cs_list": list(cs_list),
                "isi": _duration_to_dict(isi),
            }

        case ITI(distribution=dist, mean=mean):
            return {
                "type": "ITI",
                "distribution": dist,
                "mean": _duration_to_dict(mean),
            }

        case Differential(cs_positive=pos, cs_negative=neg, us=us):
            d = {
                "type": "Differential",
                "cs_positive": pos,
                "cs_negative": neg,
            }
            if us is not None:
                d["us"] = us
            return d

        case _:
            raise ValueError(f"unknown AST node: {expr!r}")


def _duration_to_dict(dur: Duration) -> dict:
    return {"value": dur.value, "unit": dur.unit}


def _param_value_to_dict(param):
    if isinstance(param, DirectionalCOD):
        d: dict = {}
        if param.base is not None:
            d["base"] = _compound_param_to_dict(param.base)
        d["directional"] = [_directional_entry_to_dict(e) for e in param.directional]
        return d
    if isinstance(param, dict):
        # PUNISH payload or Overlay raw values. Recurse through dict /
        # list values, rewriting schedule AST nodes to their dict form.
        return _serialize_raw_payload(param)
    if isinstance(param, str):
        # Overlay target=<identifier>
        return param
    return _compound_param_to_dict(param)


def _serialize_raw_payload(value):
    """Recursively convert a raw dict/list payload: pass scalars through
    and serialise any embedded ScheduleExpr-like dataclass nodes."""
    if hasattr(value, "__dataclass_fields__"):
        return _expr_to_dict(value)
    if isinstance(value, dict):
        return {k: _serialize_raw_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_raw_payload(v) for v in value]
    return value


def _compound_param_to_dict(param: CompoundParam) -> dict:
    d: dict = {"value": param.value}
    if param.time_unit is not None:
        d["time_unit"] = param.time_unit
    return d


def _directional_entry_to_dict(entry: DirectionalEntry) -> dict:
    d: dict = {
        "from": entry.from_ref if isinstance(entry.from_ref, int) else entry.from_ref,
        "to": entry.to_ref if isinstance(entry.to_ref, int) else entry.to_ref,
        "value": entry.value,
    }
    if entry.time_unit is not None:
        d["time_unit"] = entry.time_unit
    return d


def _param_decl_to_dict(decl: ParamDecl) -> dict:
    d: dict = {"type": "ParamDecl", "name": decl.name, "value": decl.value}
    if decl.time_unit is not None:
        d["time_unit"] = decl.time_unit
    return d


def _binding_to_dict(binding: Binding) -> dict:
    return {
        "type": "Binding",
        "name": binding.name,
        "value": _expr_to_dict(binding.value),
    }


def _annotation_to_dict(ann: Annotation) -> dict:
    d: dict = {"type": "Annotation", "keyword": ann.keyword}
    if ann.positional is not None:
        d["positional"] = ann.positional
    # @probe_policy emits `params: {}` even when empty (the schema treats
    # the parenthesised form as meaningful); other annotations only emit
    # `params` when non-empty to keep output concise. `kwargs` is the
    # paper-layer alias expected by `schema/experiment/experiment.schema.json`
    # fixtures; it mirrors `params` for dual-convention compatibility.
    if ann.params:
        payload = dict(ann.params)  # time_value dicts pass through as-is
        d["params"] = payload
        d["kwargs"] = payload
    elif ann.keyword == "probe_policy":
        d["params"] = {}
        d["kwargs"] = {}
    if ann.label is not None:
        d["label"] = ann.label
    return d


def from_dict(d: dict) -> Program:
    """Deserialize a dict to a Program AST."""
    schedule = _expr_from_dict(d["schedule"])
    # Re-attach hoisted Program-level annotations as an AnnotatedSchedule so
    # a subsequent to_dict roundtrip produces the same serialized form.
    if d.get("annotations"):
        schedule = AnnotatedSchedule(
            expr=schedule,
            annotations=tuple(
                _annotation_from_dict(a) for a in d["annotations"]
            ),
        )
    return Program(
        program_annotations=tuple(
            _annotation_from_dict(a) for a in d.get("program_annotations", [])
        ),
        param_decls=tuple(_param_decl_from_dict(pd) for pd in d.get("param_decls", [])),
        bindings=tuple(_binding_from_dict(b) for b in d.get("bindings", [])),
        schedule=schedule,
    )


def _annotation_from_dict(d: dict) -> Annotation:
    return Annotation(
        keyword=d["keyword"],
        positional=d.get("positional"),
        params=d.get("params"),
    )


def _expr_from_dict(d: dict) -> ScheduleExpr:
    """Deserialize a dict to a ScheduleExpr.

    Schedule-level annotations are stored by the serializer directly on the
    leaf node's dict (an ``annotations`` key alongside ``type``, ``dist``,
    etc.) for leaf types that the schema treats as annotation-capable
    (Atomic, Special, Modifier, SecondOrder, LimitedHold, Compound). When
    present, the returned value is wrapped in ``AnnotatedSchedule`` so
    that ``to_dict(from_dict(d)) == d`` round-trips.
    """
    return _maybe_wrap_annotations(_expr_from_dict_inner(d), d)


def _maybe_wrap_annotations(
    expr: ScheduleExpr, d: dict
) -> ScheduleExpr:
    """If *d* carries schedule-level annotations, wrap *expr* in AnnotatedSchedule."""
    annotations_list = d.get("annotations")
    if not annotations_list or isinstance(expr, AnnotatedSchedule):
        return expr
    return AnnotatedSchedule(
        expr=expr,
        annotations=tuple(
            _annotation_from_dict(a) for a in annotations_list
        ),
    )


def _expr_from_dict_inner(d: dict) -> ScheduleExpr:
    """Inner deserializer without AnnotatedSchedule wrapping."""
    t = d["type"]

    if t == "Atomic":
        return Atomic(
            schedule_type=ScheduleType(Distribution(d["dist"]), Domain(d["domain"])),
            value=d["value"],
            time_unit=d.get("time_unit"),
        )

    if t == "Special":
        return Special(kind=d["kind"])

    if t == "Compound":
        # Disambiguate operant vs respondent Compound by payload shape.
        if "cs_list" in d:
            return RespondentCompound(
                cs_list=tuple(d["cs_list"]),
                mode=d.get("mode", "Simultaneous"),
            )
        params = None
        if "params" in d:
            params = {}
            for k, v in d["params"].items():
                if "directional" in v:
                    base = CompoundParam(value=v["base"]["value"], time_unit=v["base"].get("time_unit")) if "base" in v else None
                    entries = tuple(
                        DirectionalEntry(from_ref=e["from"], to_ref=e["to"], value=e["value"], time_unit=e.get("time_unit"))
                        for e in v["directional"]
                    )
                    params[k] = DirectionalCOD(base=base, directional=entries)
                else:
                    params[k] = CompoundParam(value=v["value"], time_unit=v.get("time_unit"))
        return Compound(
            combinator=Combinator(d["combinator"]),
            components=tuple(_expr_from_dict(c) for c in d["components"]),
            params=params,
        )

    if t == "Modifier":
        return Modifier(
            modifier=d["modifier"],
            value=d.get("value"),
            time_unit=d.get("time_unit"),
            inner=_expr_from_dict(d["inner"]) if "inner" in d else None,
            pr_step=d.get("pr_step"),
            pr_start=d.get("pr_start"),
            pr_increment=d.get("pr_increment"),
        )

    if t == "LimitedHold":
        return LimitedHold(
            hold_duration=d["hold_duration"],
            inner=_expr_from_dict(d["inner"]),
            time_unit=d.get("time_unit"),
        )

    if t == "SecondOrder":
        overall = _expr_from_dict(d["overall"])
        unit = _expr_from_dict(d["unit"])
        if not isinstance(overall, Atomic) or not isinstance(unit, Atomic):
            raise ValueError("SecondOrder overall and unit must be Atomic")
        return SecondOrder(overall=overall, unit=unit)

    if t == "IdentifierRef":
        return IdentifierRef(name=d["name"])

    if t == "PairForwardDelay":
        return PairForwardDelay(
            cs=d["cs"],
            us=d["us"],
            isi=_duration_from_dict(d["isi"]),
            cs_duration=_duration_from_dict(d["cs_duration"]),
        )

    if t == "PairForwardTrace":
        return PairForwardTrace(
            cs=d["cs"],
            us=d["us"],
            trace_interval=_duration_from_dict(d["trace_interval"]),
            cs_duration=_duration_from_dict(d["cs_duration"]) if "cs_duration" in d else None,
        )

    if t == "PairSimultaneous":
        return PairSimultaneous(cs=d["cs"], us=d["us"])

    if t == "PairBackward":
        return PairBackward(us=d["us"], cs=d["cs"], isi=_duration_from_dict(d["isi"]))

    if t == "Extinction":
        return Extinction(cs=d["cs"])

    if t == "CSOnly":
        return CSOnly(cs=d["cs"], trials=int(d["trials"]))

    if t == "USOnly":
        return USOnly(us=d["us"], trials=int(d["trials"]))

    if t == "Contingency":
        return Contingency(
            p_us_given_cs=float(d["p_us_given_cs"]),
            p_us_given_no_cs=float(d["p_us_given_no_cs"]),
        )

    if t == "TrulyRandom":
        return TrulyRandom(
            cs=d["cs"],
            us=d["us"],
            p=float(d["p"]) if "p" in d else None,
        )

    if t == "ExplicitlyUnpaired":
        return ExplicitlyUnpaired(
            cs=d["cs"],
            us=d["us"],
            min_separation=_duration_from_dict(d["min_separation"]) if "min_separation" in d else None,
        )

    if t == "Serial":
        return Serial(
            cs_list=tuple(d["cs_list"]),
            isi=_duration_from_dict(d["isi"]),
        )

    if t == "ITI":
        return ITI(
            distribution=d["distribution"],
            mean=_duration_from_dict(d["mean"]),
        )

    if t == "Differential":
        return Differential(
            cs_positive=d["cs_positive"],
            cs_negative=d["cs_negative"],
            us=d.get("us"),
        )

    if t == "AnnotatedSchedule":
        return AnnotatedSchedule(
            expr=_expr_from_dict(d["expr"]),
            annotations=tuple(
                _annotation_from_dict(a)
                for a in d.get("annotations", [])
            ),
        )

    raise ValueError(f"unknown AST type: {t}")


def _param_decl_from_dict(d: dict) -> ParamDecl:
    return ParamDecl(name=d["name"], value=d["value"], time_unit=d.get("time_unit"))


def _duration_from_dict(d: dict) -> Duration:
    return Duration(value=float(d["value"]), unit=d["unit"])


def _binding_from_dict(d: dict) -> Binding:
    return Binding(name=d["name"], value=_expr_from_dict(d["value"]))
