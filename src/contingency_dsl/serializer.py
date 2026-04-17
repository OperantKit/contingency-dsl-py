"""Serializer: AST <-> dict (JSON-compatible).

Produces dicts matching the conformance test suite format (ast-schema.json).
"""

from __future__ import annotations

from .ast import (
    AnnotatedSchedule,
    Annotation,
    AnnotationArg,
    Atomic,
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
)
from .enums import Combinator, Distribution, Domain
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


def to_dict(program: Program) -> dict:
    """Serialize a Program AST to a JSON-compatible dict."""
    return {
        "type": "Program",
        "param_decls": [_param_decl_to_dict(d) for d in program.param_decls],
        "bindings": [_binding_to_dict(b) for b in program.bindings],
        "schedule": _expr_to_dict(program.schedule),
    }


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
            return d

        case LimitedHold(hold_duration=dur, inner=inner, time_unit=unit):
            d = {
                "type": "LimitedHold",
                "hold_duration": dur,
                "inner": _expr_to_dict(inner),
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

        case AnnotatedSchedule(expr=inner, annotations=anns):
            return {
                "type": "AnnotatedSchedule",
                "expr": _expr_to_dict(inner),
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


def _param_value_to_dict(param: CombinatorParamValue) -> dict:
    if isinstance(param, DirectionalCOD):
        d: dict = {}
        if param.base is not None:
            d["base"] = _compound_param_to_dict(param.base)
        d["directional"] = [_directional_entry_to_dict(e) for e in param.directional]
        return d
    return _compound_param_to_dict(param)


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
    args = []
    for arg in ann.args:
        a: dict = {"value": arg.value}
        if arg.key is not None:
            a["key"] = arg.key
        args.append(a)
    return {"name": ann.name, "args": args}


def from_dict(d: dict) -> Program:
    """Deserialize a dict to a Program AST."""
    return Program(
        param_decls=tuple(_param_decl_from_dict(pd) for pd in d.get("param_decls", [])),
        bindings=tuple(_binding_from_dict(b) for b in d.get("bindings", [])),
        schedule=_expr_from_dict(d["schedule"]),
    )


def _expr_from_dict(d: dict) -> ScheduleExpr:
    """Deserialize a dict to a ScheduleExpr."""
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
                Annotation(
                    name=a["name"],
                    args=tuple(
                        AnnotationArg(value=arg["value"], key=arg.get("key"))
                        for arg in a.get("args", [])
                    ),
                )
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
