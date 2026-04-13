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
    Compound,
    CompoundParam,
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
                    k: _compound_param_to_dict(v) for k, v in params.items()
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

        case _:
            raise ValueError(f"unknown AST node: {expr!r}")


def _compound_param_to_dict(param: CompoundParam) -> dict:
    d: dict = {"value": param.value}
    if param.time_unit is not None:
        d["time_unit"] = param.time_unit
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
        params = None
        if "params" in d:
            params = {
                k: CompoundParam(value=v["value"], time_unit=v.get("time_unit"))
                for k, v in d["params"].items()
            }
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


def _binding_from_dict(d: dict) -> Binding:
    return Binding(name=d["name"], value=_expr_from_dict(d["value"]))
