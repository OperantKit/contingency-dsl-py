"""Pretty-printer: AST -> canonical DSL text.

Produces compact form (FR5, not FR 5) with preserved time units.
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
    SecondOrder,
    Special,
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


def format_program(program: Program) -> str:
    """Format a complete Program to DSL text."""
    parts: list[str] = []

    for decl in program.param_decls:
        parts.append(f"{decl.name} = {_fmt_value(decl.value, decl.time_unit)}")

    for binding in program.bindings:
        parts.append(f"let {binding.name} = {format_expr(binding.value)}")

    parts.append(format_expr(program.schedule))
    return "\n".join(parts)


def format_expr(expr: ScheduleExpr) -> str:
    """Format a single schedule expression to DSL text."""
    match expr:
        case Atomic(schedule_type=st, value=val, time_unit=unit):
            return f"{st}{_fmt_value(val, unit)}"

        case Special(kind=kind):
            return kind

        case Compound(combinator=comb, components=components, params=params):
            parts = [format_expr(c) for c in components]
            if params:
                for k, p in params.items():
                    parts.append(f"{k}={_fmt_value(p.value, p.time_unit)}")
            return f"{comb.value}({', '.join(parts)})"

        case Modifier(modifier="PR", pr_step=step, pr_start=start, pr_increment=inc):
            if step and (start is not None or inc is not None):
                params = [step]
                if start is not None:
                    params.append(f"start={_fmt_num(start)}")
                if inc is not None:
                    params.append(f"increment={_fmt_num(inc)}")
                return f"PR({', '.join(params)})"
            if step and step != "hodos":
                return f"PR({step})"
            return "PR"

        case Modifier(modifier="Repeat", value=count, inner=inner) if inner is not None and count is not None:
            return f"Repeat({_fmt_num(count)}, {format_expr(inner)})"

        case Modifier(modifier=mod, value=val, time_unit=unit) if val is not None:
            return f"{mod}{_fmt_value(val, unit)}"

        case LimitedHold(hold_duration=dur, inner=inner, time_unit=unit):
            return f"{format_expr(inner)} LH{_fmt_value(dur, unit)}"

        case SecondOrder(overall=overall, unit=unit):
            return f"{format_expr(overall)}({format_expr(unit)})"

        case IdentifierRef(name=name):
            return name

        case AnnotatedSchedule(expr=inner, annotations=anns):
            parts = [format_expr(inner)]
            for ann in anns:
                parts.append(_fmt_annotation(ann))
            return " ".join(parts)

        case PairForwardDelay(cs=cs, us=us, isi=isi, cs_duration=csd):
            return (
                f"Pair.ForwardDelay({cs}, {us}, "
                f"isi={_fmt_duration(isi)}, cs_duration={_fmt_duration(csd)})"
            )

        case PairForwardTrace(cs=cs, us=us, trace_interval=ti, cs_duration=csd):
            inner = f"Pair.ForwardTrace({cs}, {us}, trace_interval={_fmt_duration(ti)}"
            if csd is not None:
                inner += f", cs_duration={_fmt_duration(csd)}"
            return inner + ")"

        case PairSimultaneous(cs=cs, us=us):
            return f"Pair.Simultaneous({cs}, {us})"

        case PairBackward(us=us, cs=cs, isi=isi):
            return f"Pair.Backward({us}, {cs}, isi={_fmt_duration(isi)})"

        case Extinction(cs=cs):
            return f"Extinction({cs})"

        case CSOnly(cs=cs, trials=trials):
            return f"CSOnly({cs}, trials={trials})"

        case USOnly(us=us, trials=trials):
            return f"USOnly({us}, trials={trials})"

        case Contingency(p_us_given_cs=p1, p_us_given_no_cs=p2):
            return f"Contingency({_fmt_num(p1)}, {_fmt_num(p2)})"

        case TrulyRandom(cs=cs, us=us, p=p):
            if p is None:
                return f"TrulyRandom({cs}, {us})"
            return f"TrulyRandom({cs}, {us}, p={_fmt_num(p)})"

        case ExplicitlyUnpaired(cs=cs, us=us, min_separation=ms):
            if ms is None:
                return f"ExplicitlyUnpaired({cs}, {us})"
            return f"ExplicitlyUnpaired({cs}, {us}, min_separation={_fmt_duration(ms)})"

        case RespondentCompound(cs_list=cs_list, mode=mode):
            items = ", ".join(cs_list)
            if mode == "Simultaneous":
                return f"Compound(cs_list=[{items}])"
            return f"Compound(cs_list=[{items}], mode={mode})"

        case Serial(cs_list=cs_list, isi=isi):
            items = ", ".join(cs_list)
            return f"Serial(cs_list=[{items}], isi={_fmt_duration(isi)})"

        case ITI(distribution=dist, mean=mean):
            return f"ITI({dist}, mean={_fmt_duration(mean)})"

        case Differential(cs_positive=pos, cs_negative=neg, us=us):
            if us is None:
                return f"Differential(cs_positive={pos}, cs_negative={neg})"
            return f"Differential(cs_positive={pos}, cs_negative={neg}, us={us})"

        case _:
            return repr(expr)


def _fmt_duration(dur: Duration) -> str:
    return f"{_fmt_num(dur.value)}{dur.unit}"


def _fmt_annotation(ann: Annotation) -> str:
    """Format a single annotation."""
    if not ann.args:
        return f"@{ann.name}"
    parts: list[str] = []
    for arg in ann.args:
        if arg.key is not None:
            parts.append(f"{arg.key}={_fmt_ann_value(arg.value)}")
        else:
            parts.append(_fmt_ann_value(arg.value))
    return f"@{ann.name}({', '.join(parts)})"


def _fmt_ann_value(val: str | float) -> str:
    """Format an annotation argument value."""
    if isinstance(val, str):
        return f'"{val}"'
    return _fmt_num(val)


def _fmt_value(val: float, unit: str | None) -> str:
    """Format a numeric value with optional time unit."""
    return f"{_fmt_num(val)}{unit or ''}"


def _fmt_num(val: float) -> str:
    """Format a number, dropping .0 for integers."""
    if val == int(val):
        return str(int(val))
    return str(val)
