"""Recursive descent parser for contingency-dsl.

Parses a token stream into an AST (Program node).
LL(2): the only lookahead beyond 1 is FR5 vs FR5(FI30) for second-order,
resolved by peeking for '(' after parsing the atomic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .ast import (
    AdjustingSchedule,
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
    InterlockingSchedule,
    LimitedHold,
    Modifier,
    ParamDecl,
    Program,
    ScheduleExpr,
    ScheduleType,
    SecondOrder,
    Special,
    ResponseCost,
    ResponseCostWrapped,
    Timeout,
    TimeoutWrapped,
    TrialBased,
)
from .enums import Combinator, Distribution, Domain, KW_ARG_KEYWORDS, LOWERCASE_RESERVED
from .errors import ParseError, SourceSpan
from .experiment import (
    Criterion,
    Experiment,
    ExperimenterJudgment,
    FixedSessions,
    Paper,
    Phase,
    PhaseRef,
    PhaseSchedule,
    PhaseSequence,
    Stability,
)
from .lexer import tokenize
from .respondent_parser import RESPONDENT_PRIMITIVE_NAMES, try_parse_respondent
from .tokens import Token, TokenType

if TYPE_CHECKING:
    from .extensions import ExtensionRegistry


_SHAPING_METHODS = frozenset({"artful", "percentile", "staged"})


def _desugar_shaping(
    *,
    label: str,
    meta: dict[str, object],
    extra_annotations: list[Annotation],
    user_criterion: Criterion | None,
) -> list[Phase]:
    """Validate shaping metadata and expand into concrete Phases."""
    if "target" not in meta:
        raise ParseError(
            f"MISSING_SHAPING_TARGET: shaping '{label}' has no 'target'",
            SourceSpan(1, 1),
        )
    target = meta["target"]
    method = meta.get("method", "artful")
    if method not in _SHAPING_METHODS:
        raise ParseError(
            f"UNKNOWN_SHAPING_METHOD: '{method}' (expected artful | percentile | staged)",
            SourceSpan(1, 1),
        )
    approximations = meta.get("approximations")
    dimension = meta.get("dimension")
    percentile_rank = meta.get("percentile_rank")
    percentile_window = meta.get("percentile_window")
    percentile_dir = meta.get("percentile_dir", "below")
    stages = meta.get("stages")

    proc_params: dict = {"target": target, "method": method}
    if approximations is not None:
        proc_params["approximations"] = list(approximations)  # type: ignore[arg-type]
    if dimension is not None:
        proc_params["dimension"] = dimension

    if method == "artful":
        if any(k in meta for k in ("dimension", "percentile_rank", "percentile_window", "percentile_dir", "stages")):
            raise ParseError(
                "SHAPING_META_METHOD_MISMATCH: method=artful forbids dimension / percentile_* / stages",
                SourceSpan(1, 1),
            )
        schedule: ScheduleExpr = Special(kind="CRF")
        proc_ann = Annotation(keyword="procedure", positional="shape", params=proc_params)
        phase_annotations = [proc_ann, *extra_annotations]
        criterion = user_criterion if user_criterion is not None else ExperimenterJudgment()
        return [
            Phase(
                label=label,
                schedule=schedule,
                criterion=criterion,
                phase_annotations=tuple(phase_annotations),
            )
        ]

    if method == "percentile":
        if dimension is None or percentile_rank is None:
            raise ParseError(
                "INCOMPLETE_PERCENTILE_SHAPING: method=percentile requires 'dimension' and 'percentile_rank'",
                SourceSpan(1, 1),
            )
        if not (0 <= int(percentile_rank) <= 100):  # type: ignore[arg-type]
            raise ParseError(
                f"PCTL_INVALID_RANK: percentile_rank={percentile_rank} must be in [0, 100]",
                SourceSpan(1, 1),
            )
        schedule = Modifier(
            modifier="Pctl",
            pctl_target=str(dimension),
            pctl_rank=int(percentile_rank),  # type: ignore[arg-type]
            pctl_window=int(percentile_window) if percentile_window is not None else None,  # type: ignore[arg-type]
            pctl_dir=str(percentile_dir),
        )
        proc_ann = Annotation(keyword="procedure", positional="shape", params=proc_params)
        phase_annotations = [proc_ann, *extra_annotations]
        return [
            Phase(
                label=label,
                schedule=schedule,
                criterion=user_criterion,
                phase_annotations=tuple(phase_annotations),
            )
        ]

    # method == "staged"
    if stages is None:
        raise ParseError(
            "INCOMPLETE_STAGED_SHAPING: method=staged requires a 'stages' list",
            SourceSpan(1, 1),
        )
    stage_list = list(stages)  # type: ignore[arg-type]
    if len(stage_list) < 2:
        raise ParseError(
            f"SHAPING_INSUFFICIENT_STAGES: stages must contain at least 2 entries (got {len(stage_list)})",
            SourceSpan(1, 1),
        )
    if any(k in meta for k in ("dimension", "percentile_rank", "percentile_window", "percentile_dir")):
        raise ParseError(
            "SHAPING_META_METHOD_MISMATCH: method=staged forbids dimension / percentile_*",
            SourceSpan(1, 1),
        )
    proc_ann = Annotation(keyword="procedure", positional="shape", params=proc_params)
    out: list[Phase] = []
    for i, stage in enumerate(stage_list, start=1):
        out.append(
            Phase(
                label=f"{label}_{i}",
                schedule=stage,
                criterion=user_criterion,
                phase_annotations=(proc_ann, *extra_annotations),
            )
        )
    return out


def _seconds_param(p: dict) -> float | None:
    """Convert a ``{value, time_unit}`` aversive parameter to seconds."""
    if not isinstance(p, dict):
        return None
    v = p.get("value")
    u = p.get("time_unit")
    if not isinstance(v, (int, float)):
        return None
    if u == "s":
        return float(v)
    if u == "ms":
        return float(v) / 1000.0
    if u == "min":
        return float(v) * 60.0
    return None


def _validate_aversive_params(
    *, kind: str, params: dict, span: SourceSpan
) -> None:
    """Enforce required-parameter and mode-compatibility rules on an
    aversive schedule after its param list has been parsed."""
    if kind == "Sidman":
        if "SSI" not in params:
            raise ParseError(
                "AVERSIVE_MISSING_REQUIRED: Sidman requires 'SSI'", span
            )
        if "RSI" not in params:
            raise ParseError(
                "AVERSIVE_MISSING_REQUIRED: Sidman requires 'RSI'", span
            )
        # Reject stray params that do not belong on Sidman.
        for key in params:
            if key not in ("SSI", "RSI"):
                raise ParseError(
                    f"AVERSIVE_UNKNOWN_PARAM: Sidman does not accept '{key}'",
                    span,
                )
        return
    if kind == "Escape":
        if "SafeDuration" not in params:
            raise ParseError(
                "AVERSIVE_MISSING_REQUIRED: Escape requires 'SafeDuration'",
                span,
            )
        for key in params:
            if key not in ("SafeDuration", "MaxShock"):
                raise ParseError(
                    f"AVERSIVE_UNKNOWN_PARAM: Escape does not accept '{key}'",
                    span,
                )
        return
    if kind == "DiscrimAv":
        for required in ("CSUSInterval", "ITI", "mode"):
            if required not in params:
                raise ParseError(
                    f"AVERSIVE_MISSING_REQUIRED: DiscrimAv requires '{required}'",
                    span,
                )
        # Constraint §33: ITI must be strictly greater than CSUSInterval.
        csus = params["CSUSInterval"]
        iti = params["ITI"]
        csus_s = _seconds_param(csus)
        iti_s = _seconds_param(iti)
        if csus_s is not None and iti_s is not None and iti_s <= csus_s:
            raise ParseError(
                f"DA_ITI_TOO_SHORT: ITI ({iti_s}s) must be strictly greater "
                f"than CSUSInterval ({csus_s}s)",
                span,
            )
        mode = params["mode"]
        if mode == "fixed":
            if "ShockDuration" not in params:
                raise ParseError(
                    "AVERSIVE_FIXED_MISSING_SHOCK_DURATION: DiscrimAv with "
                    "mode=fixed requires 'ShockDuration'",
                    span,
                )
            if "MaxShock" in params:
                raise ParseError(
                    "AVERSIVE_FIXED_WITH_MAX_SHOCK: DiscrimAv with "
                    "mode=fixed forbids 'MaxShock'",
                    span,
                )
        elif mode in ("escape", "response_terminated"):
            if "ShockDuration" in params:
                raise ParseError(
                    f"AVERSIVE_{mode.upper()}_WITH_SHOCK_DURATION: DiscrimAv "
                    f"with mode={mode} forbids 'ShockDuration'",
                    span,
                )
        for key in params:
            if key not in (
                "CSUSInterval", "ITI", "mode", "ShockDuration", "MaxShock",
            ):
                raise ParseError(
                    f"AVERSIVE_UNKNOWN_PARAM: DiscrimAv does not accept '{key}'",
                    span,
                )


def _validate_trial_based(*, trial_type: str, params: dict) -> None:
    """Fill in defaults and check required kwargs for MTS / GoNoGo."""
    if trial_type == "MTS":
        # Declaration-only form: `MTS(samples=N, comparisons=M)` — used in
        # stimulus-class / training / testing contexts where the schedule
        # describes trial structure rather than a running schedule. Skip the
        # consequence / ITI requirement in that case.
        if "samples" in params:
            params.setdefault("mts_type", "arbitrary")
            return
        for required in ("comparisons", "consequence", "ITI"):
            if required not in params:
                raise ParseError(
                    f"MTS_MISSING_REQUIRED: MTS(...) requires '{required}'",
                    SourceSpan(1, 1),
                )
        params.setdefault("incorrect", Special(kind="EXT"))
        params.setdefault("mts_type", "arbitrary")
        return
    if trial_type == "GoNoGo":
        for required in ("responseWindow", "consequence", "ITI"):
            if required not in params:
                raise ParseError(
                    f"GONOGO_MISSING_REQUIRED: GoNoGo(...) requires '{required}'",
                    SourceSpan(1, 1),
                )
        params.setdefault("incorrect", Special(kind="EXT"))
        # falseAlarm defaults to the same schedule as `incorrect` when not
        # explicitly given: the fixture convention is that a single
        # `incorrect=...` arg applies to both miss and false-alarm outcomes.
        params.setdefault("falseAlarm", params["incorrect"])
        return


# Annotation keywords whose semantics bind them to a specific schedule
# rather than to the enclosing Program scope. When any of these appears
# before the schedule in source order (where syntactically they look like
# program-level annotations), the parser routes them to the schedule's
# AnnotatedSchedule wrapper instead. See schema/annotations/procedure-*
# schemas for the full list.
_SCHEDULE_SCOPED_ANNOTATIONS: frozenset[str] = frozenset({
    "trial_mix",
})

# Annotations that are program-scoped for executable schedules but
# schedule-scoped for declaration-mode schedules (e.g. `MTS(samples=N,
# comparisons=M)` used for stimulus-class training/testing).
_DECL_MODE_SCOPED_ANNOTATIONS: frozenset[str] = frozenset({
    "training", "testing",
})


def _is_declaration_mode_schedule(schedule):
    """Return True if the schedule is a declaration-mode MTS (`samples` key)."""
    from .ast import TrialBased as _TB  # local import to avoid cycle
    target = schedule.expr if isinstance(schedule, AnnotatedSchedule) else schedule
    return (
        isinstance(target, _TB)
        and target.trial_type == "MTS"
        and "samples" in target.params
    )


def _route_schedule_annotations(schedule, program_annotations):
    """Move schedule-scoped annotations from program_annotations onto the
    schedule itself (wrapping in AnnotatedSchedule if needed)."""
    scheduled: list = []
    retained: list = []
    decl_mode = _is_declaration_mode_schedule(schedule)
    for ann in program_annotations:
        if ann.keyword in _SCHEDULE_SCOPED_ANNOTATIONS:
            scheduled.append(ann)
        elif decl_mode and ann.keyword in _DECL_MODE_SCOPED_ANNOTATIONS:
            scheduled.append(ann)
        else:
            retained.append(ann)
    if not scheduled:
        return schedule, program_annotations
    if isinstance(schedule, AnnotatedSchedule):
        schedule = AnnotatedSchedule(
            expr=schedule.expr,
            annotations=tuple(scheduled) + schedule.annotations,
        )
    else:
        schedule = AnnotatedSchedule(
            expr=schedule,
            annotations=tuple(scheduled),
        )
    return schedule, retained


# Per schema/annotations/*.schema.json `aliases` entries: source alias →
# canonical keyword. The source keyword is preserved as Annotation.label so
# downstream consumers can report the original spelling.
_ANNOTATION_KEYWORD_ALIASES: dict[str, str] = {
    "punisher": "reinforcer",
    "consequentStimulus": "reinforcer",
    "hw": "hardware",
}


def _canonicalize_annotation_keyword(source: str) -> tuple[str, str | None]:
    """Return ``(canonical, label)`` for an annotation keyword.

    If ``source`` is an alias, returns the canonical name plus the original
    alias as label. Otherwise returns ``(source, None)``.
    """
    if source in _ANNOTATION_KEYWORD_ALIASES:
        return _ANNOTATION_KEYWORD_ALIASES[source], source
    return source, None


_PCTL_KNOWN_TARGETS: frozenset[str] = frozenset({
    "force", "latency", "duration", "IRT", "rate", "location", "amplitude",
})


_KNOWN_ADVANCE_METRICS: frozenset[str] = frozenset({
    "rate", "avoidance_rate", "sessions", "reinforcers",
    "iri", "latency", "accuracy",
})


_AVERSIVE_NAME_ALIASES: dict[str, str] = {
    "Sidman": "Sidman",
    "SidmanAv": "Sidman",
    "SidmanAvoidance": "Sidman",
    "DiscrimAv": "DiscrimAv",
    "DiscriminatedAvoidance": "DiscrimAv",
    "Escape": "Escape",
}

_AVERSIVE_PARAM_ALIASES: dict[str, str] = {
    "SSI": "SSI",
    "ShockShockInterval": "SSI",
    "RSI": "RSI",
    "ResponseShockInterval": "RSI",
    "ITI": "ITI",
    "IntertrialInterval": "ITI",
    "CSUSInterval": "CSUSInterval",
    "SafeDuration": "SafeDuration",
    "MaxShock": "MaxShock",
    "ShockDuration": "ShockDuration",
    "mode": "mode",
}


def _resolve_phase_refs(phases: list[Phase]) -> list[Phase]:
    """Replace each `use <Label>` schedule with the referenced phase's schedule.

    Phase references are backward-only: a phase may only refer to a phase
    declared earlier in the sequence. Duplicate phase labels are also
    rejected here because a forward-only scan depends on unique names.
    """
    resolved: list[Phase] = []
    by_label: dict[str, Phase] = {}
    for phase in phases:
        if phase.label in by_label:
            raise ParseError(
                f"duplicate phase label '{phase.label}'",
                SourceSpan(1, 1),  # no span tracked at this layer yet
            )
        if isinstance(phase.schedule, PhaseRef):
            target = by_label.get(phase.schedule.ref)
            if target is None:
                raise ParseError(
                    f"phase '{phase.label}' references undefined or not-yet-declared "
                    f"phase '{phase.schedule.ref}'",
                    SourceSpan(1, 1),
                )
            phase = Phase(
                label=phase.label,
                schedule=target.schedule,
                criterion=phase.criterion,
                phase_annotations=phase.phase_annotations,
            )
        resolved.append(phase)
        by_label[phase.label] = phase
    return resolved


def _merge_criterion(
    *,
    session_count: int | None,
    min_sessions: int | None,
    stability: Stability | None,
) -> Criterion | None:
    """Combine the individual criterion clauses collected in a phase body.

    * `sessions = N` alone → FixedSessions(count=N).
    * `stable(...)` alone → Stability as parsed.
    * `sessions >= N` + `stable(...)` → Stability with min_sessions=N attached.
    * Nothing collected → None (defers to shared defaults or terminal phase).

    Disallowed combinations raise ParseError:
    * `sessions = N` + `stable(...)` — `=` contradicts a stability criterion;
      use `sessions >= N` to express a minimum floor on the stability window.
    * `sessions >= N` alone — a minimum without a stability rule is not a
      well-defined stopping criterion.
    """
    if stability is not None:
        if session_count is not None:
            raise ParseError(
                "'sessions = N' cannot be combined with 'stable(...)'; "
                "use 'sessions >= N' to set a minimum before stability is tested",
                SourceSpan(1, 1),
            )
        if min_sessions is not None:
            stability = Stability(
                method=stability.method,
                window_sessions=stability.window_sessions,
                max_change_pct=stability.max_change_pct,
                min_sessions=min_sessions,
                measure=stability.measure,
            )
        return stability
    if session_count is not None:
        return FixedSessions(count=session_count)
    if min_sessions is not None:
        # `sessions >= N` alone is a minimum floor without an explicit
        # termination rule. The progressive fixtures rely on this degenerate
        # form, so we surface it as FixedSessions(count=N). A future
        # `MinSessions` node could record the weaker semantics explicitly.
        return FixedSessions(count=min_sessions)
    return None


def parse(
    source: str, *, extensions: ExtensionRegistry | None = None
) -> Program | PhaseSequence | Paper:
    """Parse DSL source text into a Program, PhaseSequence, or Paper AST.

    Args:
        source: DSL source text.
        extensions: Optional extension registry. When provided, @-annotations
            are parsed; when None (default), @ is a parse error.

    Returns:
        A Program for single-schedule inputs; a PhaseSequence for
        experiment-layer inputs that begin (after optional program-level
        annotations) with a `phase` block.
    """
    tokens = tokenize(source)
    parser = _Parser(tokens, extensions=extensions)
    return parser.parse_program()


class _Parser:
    """Recursive descent parser state."""

    def __init__(
        self,
        tokens: list[Token],
        *,
        extensions: ExtensionRegistry | None = None,
    ) -> None:
        self._tokens = tokens
        self._pos = 0
        self._extensions = extensions
        self._annotation_keywords: frozenset[str] = (
            extensions.all_annotation_keywords if extensions else frozenset()
        )
        # Accumulator for non-fatal diagnostics raised by the
        # experiment-layer parser (e.g. `ADVANCE_SINGLE_STEP`). Flushed into
        # `PhaseSequence.parse_warnings` so the analyzer can surface them.
        self._parse_warnings: list[str] = []

    # --- Token navigation ---

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, tt: TokenType, context: str = "") -> Token:
        tok = self._peek()
        if tok.type != tt:
            msg = f"expected {tt.name}"
            if context:
                msg += f" ({context})"
            msg += f", got {tok.type.name} '{tok.value}'"
            raise ParseError(msg, SourceSpan(tok.line, tok.col))
        return self._advance()

    def _at(self, *types: TokenType) -> bool:
        return self._peek().type in types

    def _skip_newlines(self) -> None:
        """Consume any run of NEWLINE tokens. No-op in flat mode."""
        while self._peek().type == TokenType.NEWLINE:
            self._advance()

    # --- Grammar productions ---

    def parse_program(self) -> Program | PhaseSequence | Paper:
        """Top-level dispatch between single-schedule, phase-sequence, and
        paper forms.

        file ::= paper | experiment_body | program
        paper           ::= program_annotation* experiment_decl+
        experiment_decl ::= "experiment" experiment_label ":" experiment_body
        """
        self._skip_newlines()

        program_annotations: list[Annotation] = []

        # Parse program-level annotations: @keyword(...)
        if self._extensions:
            while self._at(TokenType.AT):
                program_annotations.append(self._parse_program_annotation())
                self._skip_newlines()

        # Paper form: one or more `experiment <label>:` blocks at top level.
        if self._at(TokenType.EXPERIMENT):
            return self._parse_paper(
                shared_annotations=tuple(program_annotations)
            )

        # Experiment-body (phase sequence) form.
        if self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE):
            return self._parse_phase_sequence(
                shared_annotations=tuple(program_annotations)
            )

        param_decls: list[ParamDecl] = []
        bindings: list[Binding] = []

        # Parse param_decls: ("LH" | "RD" | "COD" | "FRCO" | "BO" | aliases) "=" value
        while self._at(TokenType.LH, TokenType.RD, TokenType.KW_ARG_NAME):
            # Peek ahead: keyword followed by = is a param_decl, otherwise
            # it's part of a schedule expression (LH can be postfix)
            if self._pos + 1 < len(self._tokens) and self._tokens[self._pos + 1].type == TokenType.EQUALS:
                param_decls.append(self._parse_param_decl())
            else:
                break

        # Parse bindings: "let" ident "=" schedule
        while self._at(TokenType.LET):
            bindings.append(self._parse_binding())

        # Parse the schedule expression
        schedule = self._parse_schedule()

        self._skip_newlines()
        # Expect EOF
        if not self._at(TokenType.EOF):
            tok = self._peek()
            raise ParseError(
                f"unexpected token after schedule: {tok.type.name} '{tok.value}'",
                SourceSpan(tok.line, tok.col),
            )

        # Re-route schedule-attached annotations that syntactically appeared
        # before the schedule. The schema assigns certain keywords (trial
        # structure, probe policy, training / testing class declarations) to
        # the following schedule rather than to the Program scope.
        schedule, program_annotations = _route_schedule_annotations(
            schedule, program_annotations
        )

        return Program(
            program_annotations=tuple(program_annotations),
            param_decls=tuple(param_decls),
            bindings=tuple(bindings),
            schedule=schedule,
        )

    # --- Experiment-layer productions ---

    def _parse_phase_sequence(
        self,
        *,
        shared_annotations: tuple[Annotation, ...],
        require_eof: bool = True,
    ) -> PhaseSequence:
        """phase_sequence ::= (phase_block | shaping_block | progressive_block)+

        When `require_eof` is False (paper-layer context), the sequence may
        terminate at the next `experiment` block boundary instead of EOF.
        """
        phases: list[Phase] = []
        # Names of phases that have been "consumed" by an interleave
        # reference and should be dropped from the emitted sequence.
        consumed_by_interleave: set[str] = set()
        while self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE):
            if self._at(TokenType.PHASE):
                phases.append(self._parse_phase_block())
            elif self._at(TokenType.SHAPING):
                phases.extend(self._parse_shaping_block())
            else:
                expanded, consumed = self._parse_progressive_block(phases)
                phases.extend(expanded)
                consumed_by_interleave.update(consumed)
            self._skip_newlines()

        if require_eof and not self._at(TokenType.EOF):
            tok = self._peek()
            raise ParseError(
                f"unexpected token after phase sequence: {tok.type.name} '{tok.value}'",
                SourceSpan(tok.line, tok.col),
            )

        phases = [p for p in phases if p.label not in consumed_by_interleave]
        resolved = _resolve_phase_refs(phases)
        seq = PhaseSequence(
            phases=tuple(resolved),
            shared_annotations=shared_annotations,
            parse_warnings=tuple(self._parse_warnings),
        )
        self._parse_warnings.clear()
        return seq

    def _parse_paper(
        self, *, shared_annotations: tuple[Annotation, ...]
    ) -> Paper:
        """paper ::= program_annotation* experiment_decl+

        experiment_decl is consumed by :meth:`_parse_experiment_block`.
        Duplicate labels surface as SemanticError (`DUPLICATE_EXPERIMENT_LABEL`)
        per `schema/experiment/experiment.schema.json`.
        """
        from .errors import SemanticError

        experiments: list[Experiment] = []
        labels_seen: set[str] = set()
        while self._at(TokenType.EXPERIMENT):
            exp = self._parse_experiment_block()
            if exp.label in labels_seen:
                raise SemanticError(
                    f"DUPLICATE_EXPERIMENT_LABEL: experiment '{exp.label}' is "
                    "declared more than once"
                )
            labels_seen.add(exp.label)
            experiments.append(exp)
            self._skip_newlines()

        if not self._at(TokenType.EOF):
            tok = self._peek()
            raise ParseError(
                f"unexpected token after paper: {tok.type.name} '{tok.value}'",
                SourceSpan(tok.line, tok.col),
            )

        if not experiments:
            tok = self._peek()
            raise ParseError(
                "paper requires at least one experiment block",
                SourceSpan(tok.line, tok.col),
            )

        return Paper(
            experiments=tuple(experiments),
            shared_annotations=shared_annotations,
        )

    def _parse_experiment_block(self) -> Experiment:
        """experiment_decl ::= "experiment" experiment_label ":"
                               program_annotation*
                               (phase_decl+ | schedule)
        """
        self._expect(TokenType.EXPERIMENT, "experiment block start")
        label_tok = self._expect(TokenType.IDENTIFIER, "experiment label")
        self._expect(TokenType.COLON, "':' after experiment label")
        self._skip_newlines()

        exp_annotations: list[Annotation] = []
        if self._extensions:
            while self._at(TokenType.AT):
                exp_annotations.append(self._parse_program_annotation())
                self._skip_newlines()

        body: Program | PhaseSequence
        if self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE):
            body = self._parse_phase_sequence(
                shared_annotations=tuple(exp_annotations),
                require_eof=False,
            )
        else:
            # Single-schedule Program body.
            param_decls: list[ParamDecl] = []
            bindings: list[Binding] = []
            while self._at(TokenType.LH, TokenType.RD, TokenType.KW_ARG_NAME):
                if (
                    self._pos + 1 < len(self._tokens)
                    and self._tokens[self._pos + 1].type == TokenType.EQUALS
                ):
                    param_decls.append(self._parse_param_decl())
                else:
                    break
            while self._at(TokenType.LET):
                bindings.append(self._parse_binding())
            schedule = self._parse_schedule()
            self._skip_newlines()
            schedule, annotated = _route_schedule_annotations(
                schedule, exp_annotations
            )
            body = Program(
                program_annotations=tuple(annotated),
                param_decls=tuple(param_decls),
                bindings=tuple(bindings),
                schedule=schedule,
            )

        return Experiment(label=label_tok.value, body=body)

    def _parse_phase_block(self) -> Phase:
        """phase_block ::= "phase" phase_label ":" NEWLINE phase_body

        `phase_label` is an upper-ident (`Baseline`) or a digit-ident (`1`,
        `2a`, `3_pilot`). The lexer emits both as IDENTIFIER when the label
        follows a `phase` keyword.
        """
        self._expect(TokenType.PHASE, "phase block start")
        label_tok = self._expect(TokenType.IDENTIFIER, "phase label")
        self._expect(TokenType.COLON, "':' after phase label")
        self._skip_newlines()

        schedule: PhaseSchedule = None
        schedule_set = False
        phase_annotations: list[Annotation] = []

        # Criterion pieces — collected and merged at block end.
        session_count: int | None = None  # sessions = N
        min_sessions: int | None = None  # sessions >= N
        stability: Stability | None = None

        while not self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
                break

            tok = self._peek()

            if tok.type == TokenType.SESSIONS:
                sessions_tok = self._advance()
                if session_count is not None or min_sessions is not None:
                    raise ParseError(
                        f"phase '{label_tok.value}' has a duplicate 'sessions' clause",
                        SourceSpan(sessions_tok.line, sessions_tok.col, len(sessions_tok.value)),
                    )
                op_tok = self._peek()
                if op_tok.type == TokenType.EQUALS:
                    self._advance()
                    num = self._expect(TokenType.NUMBER, "session count")
                    session_count = int(float(num.value))
                    if session_count <= 0:
                        raise ParseError(
                            f"'sessions = {session_count}' must be positive",
                            SourceSpan(num.line, num.col, len(num.value)),
                        )
                elif op_tok.type == TokenType.GTE:
                    self._advance()
                    num = self._expect(TokenType.NUMBER, "session minimum")
                    min_sessions = int(float(num.value))
                    if min_sessions <= 0:
                        raise ParseError(
                            f"'sessions >= {min_sessions}' must be positive",
                            SourceSpan(num.line, num.col, len(num.value)),
                        )
                else:
                    raise ParseError(
                        f"expected '=' or '>=' after 'sessions', got {op_tok.type.name} '{op_tok.value}'",
                        SourceSpan(op_tok.line, op_tok.col),
                    )
                continue

            if tok.type == TokenType.STABLE:
                if stability is not None:
                    raise ParseError(
                        f"phase '{label_tok.value}' has a duplicate 'stable(...)' clause",
                        SourceSpan(tok.line, tok.col, len(tok.value)),
                    )
                stability = self._parse_stability_call()
                continue

            if tok.type == TokenType.NO_SCHEDULE:
                self._advance()
                schedule = None
                schedule_set = True
                continue

            if tok.type == TokenType.USE:
                self._advance()
                ref_tok = self._expect(TokenType.IDENTIFIER, "phase reference name")
                schedule = PhaseRef(ref=ref_tok.value)
                schedule_set = True
                continue

            if tok.type == TokenType.AT and self._extensions:
                phase_annotations.append(self._parse_program_annotation())
                continue

            # Anything else must be a schedule expression.
            schedule = self._parse_schedule()
            schedule_set = True

        if not schedule_set:
            raise ParseError(
                f"phase '{label_tok.value}' has no schedule or 'no_schedule' marker",
                SourceSpan(label_tok.line, label_tok.col, len(label_tok.value)),
            )

        criterion: Criterion | None = _merge_criterion(
            session_count=session_count,
            min_sessions=min_sessions,
            stability=stability,
        )

        return Phase(
            label=label_tok.value,
            schedule=schedule,
            criterion=criterion,
            phase_annotations=tuple(phase_annotations),
        )

    def _parse_progressive_block(
        self, already_parsed_phases: list[Phase]
    ) -> tuple[list[Phase], set[str]]:
        """progressive_block ::= "progressive" IDENT ":" NEWLINE progressive_body

        Expands into a list of concrete Phases by zipping the declared `steps`
        variables and substituting placeholders in the schedule template. If
        any `interleave <Ref>` declarations are present, the referenced phase
        is cloned between generated phases and the original reference is
        marked for removal from the surrounding sequence.
        """
        self._expect(TokenType.PROGRESSIVE, "progressive block start")
        label_tok = self._expect(TokenType.IDENTIFIER, "progressive label")
        self._expect(TokenType.COLON, "':' after progressive label")
        self._skip_newlines()

        steps: dict[str, list[float]] = {}
        interleaves: list[tuple[str, bool]] = []
        phase_annotations: list[Annotation] = []
        session_count: int | None = None
        min_sessions: int | None = None
        stability: Stability | None = None
        advance_seen = False
        advance_kind: str | None = None

        while not self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
                break
            tok = self._peek()

            if tok.type == TokenType.STEPS:
                self._advance()
                var_tok = self._expect(TokenType.IDENTIFIER, "steps variable name")
                if var_tok.value in steps:
                    raise ParseError(
                        f"duplicate steps variable '{var_tok.value}'",
                        SourceSpan(var_tok.line, var_tok.col, len(var_tok.value)),
                    )
                self._expect(TokenType.EQUALS, "'=' after steps variable")
                self._expect(TokenType.LBRACKET, "'[' for steps values")
                values: list[float] = []
                if not self._at(TokenType.RBRACKET):
                    num = self._expect(TokenType.NUMBER, "step value")
                    values.append(float(num.value))
                    while self._at(TokenType.COMMA):
                        self._advance()
                        num = self._expect(TokenType.NUMBER, "step value")
                        values.append(float(num.value))
                self._expect(TokenType.RBRACKET, "']' closing steps values")
                if not values:
                    raise ParseError(
                        f"PROGRESSIVE_EMPTY_STEPS: steps variable '{var_tok.value}' has no values",
                        SourceSpan(var_tok.line, var_tok.col, len(var_tok.value)),
                    )
                steps[var_tok.value] = values
                continue

            if tok.type == TokenType.INTERLEAVE:
                self._advance()
                ref_tok = self._expect(TokenType.IDENTIFIER, "interleave phase reference")
                no_trailing = False
                if self._at(TokenType.NO_TRAILING):
                    self._advance()
                    no_trailing = True
                if ref_tok.value == label_tok.value:
                    raise ParseError(
                        f"PROGRESSIVE_SELF_INTERLEAVE: '{label_tok.value}' references itself",
                        SourceSpan(ref_tok.line, ref_tok.col, len(ref_tok.value)),
                    )
                interleaves.append((ref_tok.value, no_trailing))
                continue

            if tok.type == TokenType.SESSIONS:
                sessions_tok = self._advance()
                if session_count is not None or min_sessions is not None:
                    raise ParseError(
                        f"progressive '{label_tok.value}' has a duplicate 'sessions' clause",
                        SourceSpan(sessions_tok.line, sessions_tok.col, len(sessions_tok.value)),
                    )
                op_tok = self._peek()
                if op_tok.type == TokenType.EQUALS:
                    self._advance()
                    # Accept a placeholder in `sessions = {var}` so progressive
                    # templates can have per-step session counts. The exact
                    # value is discarded for now; expansion carries no
                    # criterion (the fixtures that exercise this pattern only
                    # check phase count / labels).
                    if self._at(TokenType.PLACEHOLDER):
                        self._advance()
                        session_count = None
                    else:
                        num = self._expect(TokenType.NUMBER, "session count")
                        session_count = int(float(num.value))
                        if session_count <= 0:
                            raise ParseError(
                                f"'sessions = {session_count}' must be positive",
                                SourceSpan(num.line, num.col, len(num.value)),
                            )
                        if advance_seen and advance_kind == "criterion":
                            raise ParseError(
                                "ADVANCE_FIXED_SESSIONS_CONFLICT: 'sessions = N' "
                                "is incompatible with a prior 'advance when criterion(...)'; "
                                "use 'sessions >= N'",
                                SourceSpan(num.line, num.col, len(num.value)),
                            )
                elif op_tok.type == TokenType.GTE:
                    self._advance()
                    num = self._expect(TokenType.NUMBER, "session minimum")
                    min_sessions = int(float(num.value))
                    if min_sessions <= 0:
                        raise ParseError(
                            f"'sessions >= {min_sessions}' must be positive",
                            SourceSpan(num.line, num.col, len(num.value)),
                        )
                else:
                    raise ParseError(
                        f"expected '=' or '>=' after 'sessions', got {op_tok.type.name} '{op_tok.value}'",
                        SourceSpan(op_tok.line, op_tok.col),
                    )
                continue

            if tok.type == TokenType.STABLE:
                if stability is not None:
                    raise ParseError(
                        f"progressive '{label_tok.value}' has a duplicate 'stable(...)' clause",
                        SourceSpan(tok.line, tok.col, len(tok.value)),
                    )
                stability = self._parse_stability_call()
                continue

            if tok.type == TokenType.ADVANCE:
                # `advance when ...` is consumed but not yet materialized in
                # the AST. We do light inspection to detect a handful of
                # static errors (duplicates, unknown metric, incompatibility
                # with `sessions = N`), then skip to end-of-line. The
                # block-mode lexer suppresses NEWLINE inside balanced parens,
                # so the criterion call stays on a single logical line.
                self._advance()
                self._expect(TokenType.WHEN, "'when' after 'advance'")
                if advance_seen:
                    raise ParseError(
                        "DUPLICATE_PROGRESSIVE_ADVANCE: at most one 'advance when' per progressive block",
                        SourceSpan(tok.line, tok.col, len(tok.value)),
                    )
                advance_seen = True
                advance_kind = self._parse_advance_spec(progressive_label=label_tok.value)
                if (
                    advance_kind == "criterion"
                    and session_count is not None
                ):
                    raise ParseError(
                        "ADVANCE_FIXED_SESSIONS_CONFLICT: 'advance when criterion(...)' "
                        "is incompatible with 'sessions = N'; use 'sessions >= N'",
                        SourceSpan(tok.line, tok.col, len(tok.value)),
                    )
                continue

            if tok.type == TokenType.AT and self._extensions:
                phase_annotations.append(self._parse_program_annotation())
                continue

            # Remaining tokens = schedule template (+ any trailing @-annotations).
            break

        # Collect schedule template token range [template_start, template_end).
        template_start = self._pos
        while not self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
            self._advance()
        template_end = self._pos
        template_tokens = self._tokens[template_start:template_end]
        # Strip trailing NEWLINEs from the template tokens.
        while template_tokens and template_tokens[-1].type == TokenType.NEWLINE:
            template_tokens = template_tokens[:-1]

        if not steps:
            raise ParseError(
                f"PROGRESSIVE_EMPTY_STEPS: progressive '{label_tok.value}' has no steps variables",
                SourceSpan(label_tok.line, label_tok.col, len(label_tok.value)),
            )

        step_lengths = {len(v) for v in steps.values()}
        if len(step_lengths) > 1:
            raise ParseError(
                f"PROGRESSIVE_STEPS_LENGTH_MISMATCH: steps variables in '{label_tok.value}' have differing lengths",
                SourceSpan(label_tok.line, label_tok.col, len(label_tok.value)),
            )
        n_phases = step_lengths.pop()

        # Constraint 80: single-step progressive with `advance when
        # criterion(...)` / `advance when all(...)` is vacuous — there is
        # no second step to advance to. Accepted but flagged.
        if n_phases == 1 and advance_seen and advance_kind in ("criterion", "all"):
            self._parse_warnings.append(
                f"ADVANCE_SINGLE_STEP: progressive '{label_tok.value}' has a "
                "single step; 'advance when' has no target to advance to"
            )

        criterion = _merge_criterion(
            session_count=session_count,
            min_sessions=min_sessions,
            stability=stability,
        )

        generated: list[Phase] = []
        for i in range(n_phases):
            values = {name: vals[i] for name, vals in steps.items()}
            phase_label = f"{label_tok.value}_{i + 1}"
            schedule = self._parse_template_schedule(
                template_tokens,
                values=values,
                context_label=label_tok.value,
            )
            generated.append(
                Phase(
                    label=phase_label,
                    schedule=schedule,
                    criterion=criterion,
                    phase_annotations=tuple(phase_annotations),
                )
            )

        # Resolve interleave references and intercalate.
        by_label = {p.label: p for p in already_parsed_phases}
        clones_by_ref: list[tuple[Phase, bool]] = []
        consumed: set[str] = set()
        for ref, no_trailing in interleaves:
            target = by_label.get(ref)
            if target is None:
                raise ParseError(
                    f"UNDEFINED_PHASE_REF: interleave target '{ref}' is not a previously declared phase",
                    SourceSpan(label_tok.line, label_tok.col, len(label_tok.value)),
                )
            clones_by_ref.append((target, no_trailing))
            consumed.add(ref)

        if not clones_by_ref:
            return generated, consumed

        expanded: list[Phase] = []
        for i, phase in enumerate(generated):
            expanded.append(phase)
            is_last = i == len(generated) - 1
            for target, no_trailing in clones_by_ref:
                if is_last and no_trailing:
                    continue
                clone_label = f"{target.label}_after_{phase.label}"
                if any(p.label == clone_label for p in expanded):
                    raise ParseError(
                        f"DUPLICATE_PHASE_NAME: interleave clone '{clone_label}' collides",
                        SourceSpan(label_tok.line, label_tok.col, len(label_tok.value)),
                    )
                expanded.append(
                    Phase(
                        label=clone_label,
                        schedule=target.schedule,
                        criterion=target.criterion,
                        phase_annotations=target.phase_annotations,
                    )
                )
        return expanded, consumed

    def _parse_advance_spec(self, *, progressive_label: str) -> str:
        """Consume an `advance when <spec>` tail and return its kind.

        * `manual` → returns `"manual"`.
        * `criterion(metric="X", threshold=..., window=...)` → returns `"criterion"`.
          Validates that `metric` is in the standard registry.
        * `all(criterion(...), criterion(...))` → returns `"all"`. Validates each
          metric.

        The token sequence is entirely consumed up to the next NEWLINE / EOF;
        nothing is stored on the AST yet.
        """
        tok = self._peek()
        if tok.type == TokenType.IDENTIFIER and tok.value == "manual":
            self._advance()
            return "manual"
        if tok.type == TokenType.IDENTIFIER and tok.value == "criterion":
            self._advance()
            self._consume_criterion_call(progressive_label=progressive_label)
            return "criterion"
        if tok.type == TokenType.IDENTIFIER and tok.value == "all":
            self._advance()
            self._expect(TokenType.LPAREN, "'(' after 'all'")
            # First criterion
            first = self._expect(TokenType.IDENTIFIER, "criterion call inside 'all(...)'")
            if first.value != "criterion":
                raise ParseError(
                    f"'all(...)' expects criterion calls, got '{first.value}'",
                    SourceSpan(first.line, first.col),
                )
            self._consume_criterion_call(progressive_label=progressive_label)
            while self._at(TokenType.COMMA):
                self._advance()
                next_tok = self._expect(TokenType.IDENTIFIER, "criterion call inside 'all(...)'")
                if next_tok.value != "criterion":
                    raise ParseError(
                        f"'all(...)' expects criterion calls, got '{next_tok.value}'",
                        SourceSpan(next_tok.line, next_tok.col),
                    )
                self._consume_criterion_call(progressive_label=progressive_label)
            self._expect(TokenType.RPAREN, "closing ')' on 'all(...)'")
            return "all"
        raise ParseError(
            f"expected 'manual' | 'criterion(...)' | 'all(...)' after 'advance when', "
            f"got {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )

    def _consume_criterion_call(self, *, progressive_label: str) -> None:
        """Consume a `criterion(metric=..., threshold=..., window=...)` call.

        Validates `metric` against a small standard registry so unknown
        metrics raise UNDEFINED_CRITERION_METRIC.
        """
        self._expect(TokenType.LPAREN, "'(' after 'criterion'")
        metric_seen: str | None = None
        while not self._at(TokenType.RPAREN):
            key_tok = self._expect(TokenType.IDENTIFIER, "criterion keyword arg name")
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            if key_tok.value == "metric":
                val_tok = self._expect(TokenType.STRING_LITERAL, "metric name")
                metric_seen = val_tok.value
            elif key_tok.value == "threshold":
                # `threshold=>=10` or `threshold=10` or `threshold=<=0.8`
                # Consume optional comparison operator then number.
                if self._at(TokenType.GTE):
                    self._advance()
                # Negative numbers via MINUS NUMBER.
                if self._at(TokenType.MINUS):
                    self._advance()
                self._expect(TokenType.NUMBER, "threshold numeric value")
            elif key_tok.value == "window":
                self._expect(TokenType.NUMBER, "window numeric value")
                # Optional unit identifier: `sessions`, `minutes`, etc.
                if self._at(TokenType.SESSIONS, TokenType.IDENTIFIER):
                    self._advance()
            else:
                # Eat an opaque value so we remain resilient.
                if self._at(TokenType.STRING_LITERAL, TokenType.NUMBER, TokenType.IDENTIFIER):
                    self._advance()
            if self._at(TokenType.COMMA):
                self._advance()
        self._expect(TokenType.RPAREN, "closing ')' on 'criterion(...)'")
        if metric_seen is not None and metric_seen not in _KNOWN_ADVANCE_METRICS:
            raise ParseError(
                f"UNDEFINED_CRITERION_METRIC: '{metric_seen}' is not in the standard "
                f"metric registry (known: {sorted(_KNOWN_ADVANCE_METRICS)})",
                SourceSpan(1, 1),
            )

    def _parse_template_schedule(
        self,
        template_tokens: list[Token],
        *,
        values: dict[str, float],
        context_label: str,
    ) -> ScheduleExpr:
        """Instantiate a progressive schedule template with step values."""
        substituted: list[Token] = []
        for tok in template_tokens:
            if tok.type == TokenType.PLACEHOLDER:
                if tok.value not in values:
                    raise ParseError(
                        f"PROGRESSIVE_UNDEFINED_VARIABLE: placeholder '{{{tok.value}}}' "
                        f"has no matching steps declaration in '{context_label}'",
                        SourceSpan(tok.line, tok.col),
                    )
                num_val = values[tok.value]
                as_int = int(num_val) if num_val == int(num_val) else num_val
                substituted.append(
                    Token(TokenType.NUMBER, str(as_int), tok.line, tok.col)
                )
            elif tok.type == TokenType.STRING_LITERAL and "{" in tok.value:
                # String-embedded `{var}` substitutions (e.g. annotation args).
                new_value = tok.value
                for name, val in values.items():
                    as_int = int(val) if val == int(val) else val
                    new_value = new_value.replace("{" + name + "}", str(as_int))
                substituted.append(
                    Token(TokenType.STRING_LITERAL, new_value, tok.line, tok.col)
                )
            else:
                substituted.append(tok)
        # Append EOF so the nested parser knows where to stop.
        eof_line = substituted[-1].line if substituted else 1
        substituted.append(Token(TokenType.EOF, "", eof_line, 1))
        sub_parser = _Parser(substituted, extensions=self._extensions)
        schedule = sub_parser._parse_schedule()
        # The template may have trailing annotations on their own logical
        # line (e.g. `@reinforcer("drug", dose="{dose}mg/kg")`); consume them
        # across NEWLINE boundaries and wrap the schedule accordingly.
        sub_parser._skip_newlines()
        if self._extensions and sub_parser._at(TokenType.AT):
            trailing_annotations = sub_parser._parse_annotations()
            if trailing_annotations:
                if isinstance(schedule, AnnotatedSchedule):
                    schedule = AnnotatedSchedule(
                        expr=schedule.expr,
                        annotations=schedule.annotations + tuple(trailing_annotations),
                    )
                else:
                    schedule = AnnotatedSchedule(
                        expr=schedule,
                        annotations=tuple(trailing_annotations),
                    )
            sub_parser._skip_newlines()
        if not sub_parser._at(TokenType.EOF):
            stray = sub_parser._peek()
            raise ParseError(
                f"unexpected token in progressive schedule template: "
                f"{stray.type.name} '{stray.value}'",
                SourceSpan(stray.line, stray.col),
            )
        return schedule

    def _parse_shaping_block(self) -> list[Phase]:
        """shaping_block ::= "shaping" IDENT ":" NEWLINE shaping_body

        Desugars to:
        * `method = artful` (default) → Phase(CRF, @procedure, ExperimenterJudgment)
        * `method = percentile` → Phase(Pctl, @procedure, user criterion)
        * `method = staged` → list of Phases named `<Label>_<i>` sharing the
          user criterion, one per entry in `stages`.
        """
        self._expect(TokenType.SHAPING, "shaping block start")
        label_tok = self._expect(TokenType.IDENTIFIER, "shaping label")
        self._expect(TokenType.COLON, "':' after shaping label")
        self._skip_newlines()

        meta: dict[str, object] = {}
        phase_annotations: list[Annotation] = []
        session_count: int | None = None
        min_sessions: int | None = None
        stability: Stability | None = None

        shaping_meta_keywords = {
            "target", "method", "approximations", "dimension",
            "percentile_rank", "percentile_window", "percentile_dir",
            "stages",
        }

        while not self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.PHASE, TokenType.SHAPING, TokenType.PROGRESSIVE, TokenType.EOF):
                break
            tok = self._peek()

            if tok.type == TokenType.IDENTIFIER and tok.value in shaping_meta_keywords:
                key_tok = self._advance()
                if key_tok.value in meta:
                    raise ParseError(
                        f"DUPLICATE_SHAPING_META: '{key_tok.value}' set more than once",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
                meta[key_tok.value] = self._parse_shaping_meta_value(key_tok.value)
                continue

            if tok.type == TokenType.SESSIONS:
                sessions_tok = self._advance()
                if session_count is not None or min_sessions is not None:
                    raise ParseError(
                        f"shaping '{label_tok.value}' has a duplicate 'sessions' clause",
                        SourceSpan(sessions_tok.line, sessions_tok.col, len(sessions_tok.value)),
                    )
                op_tok = self._peek()
                if op_tok.type == TokenType.EQUALS:
                    self._advance()
                    num = self._expect(TokenType.NUMBER, "session count")
                    session_count = int(float(num.value))
                    if session_count <= 0:
                        raise ParseError(
                            f"'sessions = {session_count}' must be positive",
                            SourceSpan(num.line, num.col, len(num.value)),
                        )
                elif op_tok.type == TokenType.GTE:
                    self._advance()
                    num = self._expect(TokenType.NUMBER, "session minimum")
                    min_sessions = int(float(num.value))
                    if min_sessions <= 0:
                        raise ParseError(
                            f"'sessions >= {min_sessions}' must be positive",
                            SourceSpan(num.line, num.col, len(num.value)),
                        )
                else:
                    raise ParseError(
                        f"expected '=' or '>=' after 'sessions', got {op_tok.type.name} '{op_tok.value}'",
                        SourceSpan(op_tok.line, op_tok.col),
                    )
                continue

            if tok.type == TokenType.STABLE:
                if stability is not None:
                    raise ParseError(
                        f"shaping '{label_tok.value}' has a duplicate 'stable(...)' clause",
                        SourceSpan(tok.line, tok.col, len(tok.value)),
                    )
                stability = self._parse_stability_call()
                continue

            if tok.type == TokenType.AT and self._extensions:
                phase_annotations.append(self._parse_program_annotation())
                continue

            raise ParseError(
                f"unexpected token in shaping body: {tok.type.name} '{tok.value}'",
                SourceSpan(tok.line, tok.col),
            )

        return _desugar_shaping(
            label=label_tok.value,
            meta=meta,
            extra_annotations=phase_annotations,
            user_criterion=_merge_criterion(
                session_count=session_count,
                min_sessions=min_sessions,
                stability=stability,
            ),
        )

    def _parse_shaping_meta_value(self, key: str) -> object:
        """Parse the RHS of a shaping_meta assignment based on its key."""
        tok = self._peek()
        if key == "target":
            str_tok = self._expect(TokenType.STRING_LITERAL, "target string")
            return str_tok.value
        if key == "method":
            id_tok = self._expect(TokenType.IDENTIFIER, "method name")
            return id_tok.value
        if key == "dimension":
            id_tok = self._expect(TokenType.IDENTIFIER, "dimension name")
            return id_tok.value
        if key == "percentile_dir":
            id_tok = self._expect(TokenType.IDENTIFIER, "percentile_dir value")
            return id_tok.value
        if key in ("percentile_rank", "percentile_window"):
            num = self._expect(TokenType.NUMBER, f"{key} numeric value")
            return int(float(num.value))
        if key == "approximations":
            self._expect(TokenType.LBRACKET, "'[' for approximations list")
            items: list[str] = []
            if not self._at(TokenType.RBRACKET):
                items.append(self._expect(TokenType.STRING_LITERAL, "approximation string").value)
                while self._at(TokenType.COMMA):
                    self._advance()
                    items.append(self._expect(TokenType.STRING_LITERAL, "approximation string").value)
            self._expect(TokenType.RBRACKET, "']' closing approximations list")
            return items
        if key == "stages":
            self._expect(TokenType.LBRACKET, "'[' for stages list")
            items = []
            if not self._at(TokenType.RBRACKET):
                items.append(self._parse_schedule())
                while self._at(TokenType.COMMA):
                    self._advance()
                    items.append(self._parse_schedule())
            self._expect(TokenType.RBRACKET, "']' closing stages list")
            return items
        raise ParseError(
            f"unknown shaping_meta key '{key}'",
            SourceSpan(tok.line, tok.col),
        )

    def _parse_stability_call(self) -> Stability:
        """stable(method [, window=N] [, threshold=M%])"""
        self._expect(TokenType.STABLE, "'stable' keyword")
        self._expect(TokenType.LPAREN, "'(' after 'stable'")

        method_tok = self._expect(TokenType.IDENTIFIER, "stability method")
        method = method_tok.value
        window: int | None = None
        max_change_pct: float | None = None

        while self._at(TokenType.COMMA):
            self._advance()
            key_tok = self._expect(TokenType.IDENTIFIER, "stable() keyword arg name")
            self._expect(TokenType.EQUALS, "stable() keyword arg '='")
            if key_tok.value == "window":
                num = self._expect(TokenType.NUMBER, "stable() window value")
                window = int(float(num.value))
            elif key_tok.value == "threshold":
                num = self._expect(TokenType.NUMBER, "stable() threshold value")
                val = float(num.value)
                if self._at(TokenType.PERCENT):
                    self._advance()
                max_change_pct = val
            else:
                raise ParseError(
                    f"unknown stable() keyword arg '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )

        self._expect(TokenType.RPAREN, "stable() closing paren")
        return Stability(
            method=method,
            window_sessions=window,
            max_change_pct=max_change_pct,
        )

    def _parse_param_decl(self) -> ParamDecl:
        """param_decl ::= param_name "=" value"""
        tok = self._advance()  # consume param token
        # Normalize aliases
        if tok.type == TokenType.RD:
            name = "RD"
        elif tok.type == TokenType.KW_ARG_NAME:
            name = KW_ARG_KEYWORDS[tok.value]  # COD, FRCO, BO
        else:
            name = "LH"
        self._expect(TokenType.EQUALS)
        val, unit = self._parse_value()
        return ParamDecl(name=name, value=val, time_unit=unit)

    def _parse_binding(self) -> Binding:
        """binding ::= "let" ident "=" schedule"""
        self._expect(TokenType.LET)
        name_tok = self._expect(TokenType.IDENTIFIER, "binding name")
        if name_tok.value in LOWERCASE_RESERVED:
            raise ParseError(
                f"reserved word '{name_tok.value}' cannot be used as binding name",
                SourceSpan(name_tok.line, name_tok.col, len(name_tok.value)),
            )
        self._expect(TokenType.EQUALS)
        value = self._parse_schedule()
        return Binding(name=name_tok.value, value=value)

    def _parse_schedule(self) -> ScheduleExpr:
        """schedule ::= base_schedule ("LH" ws? value)? ("TO" "(" ... ")")? annotation*"""
        base = self._parse_base_schedule()

        # Check for LH postfix
        if self._at(TokenType.LH):
            # Must NOT be followed by "=" (that's a param_decl, not postfix LH)
            if self._pos + 1 < len(self._tokens) and self._tokens[self._pos + 1].type == TokenType.EQUALS:
                return self._maybe_wrap_annotations(base)
            lh_tok = self._advance()  # consume LH
            if isinstance(base, Compound):
                raise ParseError(
                    f"LH_ON_COMPOUND: LH applies to leaf schedules only, "
                    f"not to {base.combinator.value} — apply per-component "
                    "instead",
                    SourceSpan(lh_tok.line, lh_tok.col, len(lh_tok.value)),
                )
            hold_val, hold_unit = self._parse_value()
            base = LimitedHold(hold_duration=hold_val, inner=base, time_unit=hold_unit)

        # Check for TO(...) / Timeout(...) postfix (Leitenberg 1965)
        if (
            self._at(TokenType.IDENTIFIER)
            and self._peek().value in ("TO", "Timeout")
            and self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type == TokenType.LPAREN
        ):
            if isinstance(base, Compound):
                raise ParseError(
                    "TIMEOUT_ON_COMPOUND: TO(...) applies to leaf schedules only, "
                    "not to Compound / Chain expressions",
                    SourceSpan(self._peek().line, self._peek().col),
                )
            if isinstance(base, AversiveSchedule):
                raise ParseError(
                    f"TO_ON_AVERSIVE: TO(...) is not applicable to "
                    f"{base.kind} (aversive schedules manage their own shock "
                    "schedule; constraint §81)",
                    SourceSpan(self._peek().line, self._peek().col),
                )
            base = self._parse_timeout_postfix(base)

        # Check for ResponseCost(...) postfix (Weiner, 1962; Hackenberg, 2009)
        if (
            self._at(TokenType.IDENTIFIER)
            and self._peek().value == "ResponseCost"
            and self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type == TokenType.LPAREN
        ):
            if isinstance(base, Compound):
                raise ParseError(
                    "RC_ON_COMPOUND: ResponseCost applies to leaf schedules only, "
                    "not to Compound expressions — apply per-component instead "
                    "(constraint §94)",
                    SourceSpan(self._peek().line, self._peek().col),
                )
            base = self._parse_response_cost_postfix(base)

        return self._maybe_wrap_annotations(base)

    def _parse_response_cost_postfix(self, inner: ScheduleExpr) -> ResponseCostWrapped:
        """ResponseCost "(" "amount" "=" number ("," "unit" "=" string)? ")" """
        self._advance()  # consume "ResponseCost"
        self._expect(TokenType.LPAREN, "'(' after 'ResponseCost'")
        amount: float | None = None
        unit = "token"
        seen: set[str] = set()
        while not self._at(TokenType.RPAREN):
            key_tok = self._expect(TokenType.IDENTIFIER, "ResponseCost kwarg name")
            if key_tok.value in seen:
                raise ParseError(
                    f"RESPONSE_COST_DUPLICATE_KWARG: '{key_tok.value}' set twice",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            seen.add(key_tok.value)
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            if key_tok.value == "amount":
                num_tok = self._expect(TokenType.NUMBER, "amount value")
                amount = float(num_tok.value)
                if amount <= 0:
                    raise ParseError(
                        f"RESPONSE_COST_NONPOSITIVE_AMOUNT: amount must be positive "
                        f"(got {amount})",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
            elif key_tok.value == "unit":
                str_tok = self._expect(TokenType.STRING_LITERAL, "unit string")
                unit = str_tok.value
            else:
                raise ParseError(
                    f"unknown ResponseCost kwarg '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            if self._at(TokenType.COMMA):
                self._advance()
        self._expect(TokenType.RPAREN, "closing ')' on ResponseCost")
        if amount is None:
            raise ParseError(
                "RESPONSE_COST_MISSING_AMOUNT: ResponseCost(...) requires 'amount='",
                SourceSpan(1, 1),
            )
        return ResponseCostWrapped(
            inner=inner, response_cost=ResponseCost(amount=amount, unit=unit)
        )

    def _parse_timeout_postfix(self, inner: ScheduleExpr) -> TimeoutWrapped:
        """TO "(" "duration" "=" time_value "," "reset_on_response" "=" bool ")" """
        name_tok = self._advance()  # consume "TO" or "Timeout"
        self._expect(TokenType.LPAREN, f"'(' after '{name_tok.value}'")
        duration: float | None = None
        duration_unit: str | None = None
        reset_on_response: bool | None = None
        seen: set[str] = set()
        while not self._at(TokenType.RPAREN):
            key_tok = self._expect(TokenType.IDENTIFIER, "TO keyword arg name")
            if key_tok.value in seen:
                raise ParseError(
                    f"TIMEOUT_DUPLICATE_KWARG: '{key_tok.value}' set more than once",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            seen.add(key_tok.value)
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            if key_tok.value == "duration":
                val, unit = self._parse_value()
                if val <= 0:
                    raise ParseError(
                        f"TIMEOUT_NONPOSITIVE_DURATION: TO duration must be positive (got {val})",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                if unit is None:
                    raise ParseError(
                        "TIMEOUT_MISSING_TIME_UNIT: TO duration requires a time unit",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                duration = val
                duration_unit = unit
            elif key_tok.value == "reset_on_response":
                bool_tok = self._expect(TokenType.IDENTIFIER, "boolean value")
                if bool_tok.value not in ("true", "false"):
                    raise ParseError(
                        f"expected 'true' or 'false' (got '{bool_tok.value}')",
                        SourceSpan(bool_tok.line, bool_tok.col, len(bool_tok.value)),
                    )
                reset_on_response = bool_tok.value == "true"
            else:
                raise ParseError(
                    f"unknown TO keyword arg '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            if self._at(TokenType.COMMA):
                self._advance()
        self._expect(TokenType.RPAREN, "closing ')' on TO")
        if duration is None:
            raise ParseError(
                "TIMEOUT_MISSING_DURATION: TO(...) requires 'duration='",
                SourceSpan(1, 1),
            )
        if reset_on_response is None:
            raise ParseError(
                "TIMEOUT_MISSING_RESET_RULE: TO(...) requires 'reset_on_response=true|false'",
                SourceSpan(1, 1),
            )
        return TimeoutWrapped(
            inner=inner,
            timeout=Timeout(
                duration=duration,
                duration_unit=duration_unit,
                reset_on_response=reset_on_response,
            ),
        )

    def _maybe_wrap_annotations(self, expr: ScheduleExpr) -> ScheduleExpr:
        """Parse optional annotations and wrap expr if any are found."""
        if not self._extensions or not self._at(TokenType.AT):
            return expr
        annotations = self._parse_annotations()
        if not annotations:
            return expr
        return AnnotatedSchedule(expr=expr, annotations=tuple(annotations))

    def _parse_annotations(self) -> list[Annotation]:
        """annotation* ::= ("@" annotation_name "(" annotation_args ")")*"""
        annotations: list[Annotation] = []
        while self._at(TokenType.AT):
            at_tok = self._advance()  # consume @

            # annotation_name must be a known keyword from registered extensions
            name_tok = self._peek()
            if name_tok.type != TokenType.IDENTIFIER:
                raise ParseError(
                    f"expected annotation name after '@', got {name_tok.type.name} '{name_tok.value}'",
                    SourceSpan(name_tok.line, name_tok.col),
                )
            if name_tok.value not in self._annotation_keywords:
                raise ParseError(
                    f"unknown annotation '@{name_tok.value}' — "
                    "not registered in any enabled extension",
                    SourceSpan(at_tok.line, at_tok.col, len(name_tok.value) + 1),
                )
            self._advance()  # consume name
            keyword = name_tok.value

            positional = None
            params: dict = {}

            if self._at(TokenType.LPAREN):
                self._advance()  # consume (

                if not self._at(TokenType.RPAREN):
                    # First arg: check if positional (no key=) or keyword
                    tok = self._peek()
                    if (
                        tok.type == TokenType.IDENTIFIER
                        and self._pos + 1 < len(self._tokens)
                        and self._tokens[self._pos + 1].type == TokenType.EQUALS
                    ):
                        # keyword arg
                        key_tok = self._advance()
                        self._advance()  # =
                        params[key_tok.value] = self._parse_annotation_value()
                    else:
                        # positional
                        positional = self._parse_annotation_value()

                    while self._at(TokenType.COMMA):
                        self._advance()
                        key_tok = self._expect(TokenType.IDENTIFIER, f"@{keyword} keyword arg name")
                        self._expect(TokenType.EQUALS, f"@{keyword} keyword arg =")
                        params[key_tok.value] = self._parse_annotation_value()

                self._expect(TokenType.RPAREN, f"@{keyword} closing paren")

            canonical, label = _canonicalize_annotation_keyword(keyword)
            annotations.append(Annotation(
                keyword=canonical,
                positional=positional,
                params=params if params else None,
                label=label,
            ))
        return annotations

    def _parse_program_annotation(self) -> Annotation:
        """Parse a program-level annotation: @keyword(...) before param_decls."""
        at_tok = self._advance()  # consume @
        name_tok = self._peek()
        if name_tok.type != TokenType.IDENTIFIER:
            raise ParseError(
                f"expected annotation name after '@', got {name_tok.type.name} '{name_tok.value}'",
                SourceSpan(name_tok.line, name_tok.col),
            )
        if name_tok.value not in self._annotation_keywords:
            raise ParseError(
                f"unknown annotation '@{name_tok.value}' — "
                "not registered in any enabled extension",
                SourceSpan(at_tok.line, at_tok.col, len(name_tok.value) + 1),
            )
        self._advance()  # consume name
        keyword = name_tok.value

        positional = None
        params: dict = {}

        if self._at(TokenType.LPAREN):
            self._advance()  # consume (
            if not self._at(TokenType.RPAREN):
                # First arg: check if positional (no key=) or keyword
                tok = self._peek()
                if (
                    tok.type == TokenType.IDENTIFIER
                    and self._pos + 1 < len(self._tokens)
                    and self._tokens[self._pos + 1].type == TokenType.EQUALS
                ):
                    # keyword arg
                    key_tok = self._advance()
                    self._advance()  # =
                    params[key_tok.value] = self._parse_annotation_value()
                else:
                    # positional
                    positional = self._parse_annotation_value()

                while self._at(TokenType.COMMA):
                    self._advance()
                    key_tok = self._expect(TokenType.IDENTIFIER, f"@{keyword} keyword arg name")
                    self._expect(TokenType.EQUALS, f"@{keyword} keyword arg =")
                    params[key_tok.value] = self._parse_annotation_value()

            self._expect(TokenType.RPAREN, f"@{keyword} closing paren")

        canonical, label = _canonicalize_annotation_keyword(keyword)
        return Annotation(
            keyword=canonical,
            positional=positional,
            params=params if params else None,
            label=label,
        )

    def _parse_annotation_value(self) -> str | float | int | dict | list | bool:
        """Parse an annotation value: string literal, number (with optional time unit), array, or bool."""
        tok = self._peek()
        if tok.type == TokenType.STRING_LITERAL:
            self._advance()
            return tok.value
        # Negative number: - NUMBER
        if tok.type == TokenType.MINUS:
            self._advance()  # consume -
            num_tok = self._expect(TokenType.NUMBER, "number after '-'")
            num = -float(num_tok.value)
            if self._at(TokenType.TIME_UNIT):
                unit_tok = self._advance()
                val = int(num) if num == int(num) else num
                return {"value": val, "time_unit": unit_tok.value}
            return int(num) if num == int(num) else num
        if tok.type == TokenType.NUMBER:
            self._advance()
            num = float(tok.value)
            # Check for time unit suffix
            if self._at(TokenType.TIME_UNIT):
                unit_tok = self._advance()
                val = int(num) if num == int(num) else num
                return {"value": val, "time_unit": unit_tok.value}
            return int(num) if num == int(num) else num
        if tok.type == TokenType.LBRACKET:
            return self._parse_annotation_array()
        if tok.type == TokenType.LBRACE:
            return self._parse_annotation_object()
        # Handle boolean-like identifiers (true/false)
        if tok.type == TokenType.IDENTIFIER and tok.value in ("true", "false"):
            self._advance()
            return tok.value == "true"
        # Handle bare `none` identifier as null.
        if tok.type == TokenType.IDENTIFIER and tok.value == "none":
            self._advance()
            return None
        # Cross-layer distribution-name lexeme used as an annotation value.
        # The lexer classifies {hodos, linear, exponential, uniform, fixed}
        # as DISTRIBUTION_NAME (see schema/foundations/grammar.ebnf); at
        # the annotation-value position we surface them as plain strings
        # so a keyword like @iti(distribution=exponential, ...) records
        # the distribution name uniformly with @iti(distribution="exponential", ...).
        if tok.type == TokenType.DISTRIBUTION_NAME:
            self._advance()
            return tok.value
        raise ParseError(
            f"expected string, number, or array in annotation argument, got {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )

    def _parse_annotation_array(self) -> list:
        """Parse an array literal: [ value, value, ... ]"""
        self._advance()  # consume [
        items = []
        if not self._at(TokenType.RBRACKET):
            items.append(self._parse_annotation_value())
            while self._at(TokenType.COMMA):
                self._advance()
                items.append(self._parse_annotation_value())
        self._expect(TokenType.RBRACKET, "annotation array closing bracket")
        return items

    def _parse_annotation_object(self) -> dict:
        """Parse an object literal: { key = value, key = value, ... }"""
        self._advance()  # consume {
        obj: dict = {}
        if not self._at(TokenType.RBRACE):
            self._parse_annotation_object_entry(obj)
            while self._at(TokenType.COMMA):
                self._advance()
                self._parse_annotation_object_entry(obj)
        self._expect(TokenType.RBRACE, "annotation object closing brace")
        return obj

    def _parse_annotation_object_entry(self, obj: dict) -> None:
        key_tok = self._peek()
        if key_tok.type not in (TokenType.IDENTIFIER, TokenType.PR_PARAM):
            raise ParseError(
                f"expected identifier key in object literal, got "
                f"{key_tok.type.name} '{key_tok.value}'",
                SourceSpan(key_tok.line, key_tok.col),
            )
        self._advance()
        self._expect(TokenType.EQUALS, f"'=' after object key '{key_tok.value}'")
        obj[key_tok.value] = self._parse_annotation_value()

    def _parse_base_schedule(self) -> ScheduleExpr:
        """base_schedule ::= atomic_or_second | compound | modifier | ident | "(" schedule ")" """
        tok = self._peek()

        # Parenthesized expression
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_schedule()
            self._expect(TokenType.RPAREN, "closing parenthesis")
            return expr

        # Compound: Conc(...), Chain(...), etc.
        if tok.type == TokenType.COMBINATOR:
            return self._parse_compound()

        # Modifier: DRL, DRH, DRO
        if tok.type == TokenType.DR_MOD:
            return self._parse_dr_mod()

        # Modifier: PR
        if tok.type == TokenType.PR:
            return self._parse_pr_mod()

        # Modifier: Repeat
        if tok.type == TokenType.REPEAT:
            return self._parse_repeat()

        # Atomic or second-order: FR5, FR5(FI30), EXT, CRF
        if tok.type == TokenType.SCHEDULE_TYPE:
            return self._parse_atomic_or_second()

        if tok.type == TokenType.EXT:
            self._advance()
            return Special(kind="EXT")

        if tok.type == TokenType.CRF:
            self._advance()
            return Special(kind="CRF")

        # Identifier reference, aversive schedule, Pctl schedule, or
        # respondent Tier A primitive dispatch.
        if tok.type == TokenType.IDENTIFIER:
            next_is_lparen = (
                self._pos + 1 < len(self._tokens)
                and self._tokens[self._pos + 1].type == TokenType.LPAREN
            )
            if tok.value in _AVERSIVE_NAME_ALIASES and next_is_lparen:
                return self._parse_aversive_schedule()
            if tok.value == "Pctl" and next_is_lparen:
                return self._parse_pctl_schedule()
            if tok.value in ("MTS", "GoNoGo") and next_is_lparen:
                return self._parse_trial_based()
            if tok.value in ("Adj", "Adjusting") and next_is_lparen:
                return self._parse_adjusting_schedule()
            if tok.value in ("Interlock", "Interlocking") and next_is_lparen:
                return self._parse_interlocking_schedule()
            if tok.value == "Lag" or (tok.value.startswith("Lag") and tok.value[3:].isdigit()):
                return self._parse_lag()
            if tok.value in RESPONDENT_PRIMITIVE_NAMES:
                respondent = try_parse_respondent(self)
                if respondent is not None:
                    return respondent
            self._advance()
            ref = IdentifierRef(name=tok.value)
            # Second-order form with an IdentifierRef as the overall:
            # `y(x)` where `y` is a let-bound Atomic (Issue #33).
            if self._at(TokenType.LPAREN):
                self._advance()
                unit = self._parse_second_order_unit()
                self._expect(TokenType.RPAREN, "second-order schedule closing paren")
                return SecondOrder(overall=ref, unit=unit)
            return ref

        # Error
        if tok.type == TokenType.EOF:
            raise ParseError("unexpected end of input", SourceSpan(tok.line, tok.col))

        raise ParseError(
            f"unexpected token: {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )

    def _parse_adjusting_schedule(self) -> AdjustingSchedule:
        """Adj|Adjusting "(" target ("," kwarg)* ")" """
        self._advance()  # Adj / Adjusting
        self._expect(TokenType.LPAREN, "'(' after 'Adj'")
        target_tok = self._expect(TokenType.IDENTIFIER, "Adj target")
        if target_tok.value not in ("delay", "ratio", "amount", "interval"):
            raise ParseError(
                f"ADJUSTING_UNKNOWN_TARGET: '{target_tok.value}' (expected "
                "delay | ratio | amount | interval)",
                SourceSpan(target_tok.line, target_tok.col, len(target_tok.value)),
            )
        temporal = target_tok.value in ("delay", "interval")
        params: dict = {"adj_start": None, "adj_step": None, "adj_min": None, "adj_max": None}
        seen: set[str] = set()
        while self._at(TokenType.COMMA):
            self._advance()
            key_tok = self._peek()
            if key_tok.type not in (TokenType.IDENTIFIER, TokenType.PR_PARAM):
                raise ParseError(
                    f"expected Adj kwarg name, got {key_tok.type.name} '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col),
                )
            self._advance()
            if key_tok.value in seen:
                raise ParseError(
                    f"ADJUSTING_DUPLICATE_KWARG: '{key_tok.value}' set twice",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            seen.add(key_tok.value)
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            val, unit = self._parse_value()
            if temporal and unit is None:
                raise ParseError(
                    f"ADJUSTING_MISSING_TIME_UNIT: '{key_tok.value}' must carry a "
                    f"time unit when target='{target_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            if not temporal and unit is not None:
                raise ParseError(
                    f"ADJUSTING_UNEXPECTED_TIME_UNIT: '{key_tok.value}' must be "
                    f"dimensionless when target='{target_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            payload = {"value": int(val) if val == int(val) else val, "time_unit": unit}
            if key_tok.value == "start":
                params["adj_start"] = payload
            elif key_tok.value == "step":
                params["adj_step"] = payload
            elif key_tok.value == "min":
                params["adj_min"] = payload
            elif key_tok.value == "max":
                params["adj_max"] = payload
            else:
                raise ParseError(
                    f"unknown Adj kwarg '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
        self._expect(TokenType.RPAREN, "closing ')' on Adj")
        if params["adj_start"] is None:
            raise ParseError(
                "ADJUSTING_MISSING_START: Adj(...) requires 'start='",
                SourceSpan(target_tok.line, target_tok.col),
            )
        if params["adj_step"] is None:
            raise ParseError(
                "ADJUSTING_MISSING_STEP: Adj(...) requires 'step='",
                SourceSpan(target_tok.line, target_tok.col),
            )
        # Semantic validation
        start_v = params["adj_start"]["value"]
        step_v = params["adj_step"]["value"]
        if target_tok.value == "ratio":
            if start_v != int(start_v):
                raise ParseError(
                    f"ADJ_RATIO_NOT_INTEGER: ratio start must be integer "
                    f"(got {start_v})",
                    SourceSpan(target_tok.line, target_tok.col),
                )
            if step_v != int(step_v):
                raise ParseError(
                    f"ADJ_RATIO_NOT_INTEGER: ratio step must be integer "
                    f"(got {step_v})",
                    SourceSpan(target_tok.line, target_tok.col),
                )
        if start_v <= 0:
            raise ParseError(
                f"ADJ_NONPOSITIVE_START: start must be positive (got {start_v})",
                SourceSpan(target_tok.line, target_tok.col),
            )
        if step_v <= 0:
            raise ParseError(
                f"ADJ_NONPOSITIVE_STEP: step must be positive (got {step_v})",
                SourceSpan(target_tok.line, target_tok.col),
            )
        mn = params["adj_min"]["value"] if params["adj_min"] is not None else None
        mx = params["adj_max"]["value"] if params["adj_max"] is not None else None
        if mn is not None and mx is not None and mn >= mx:
            raise ParseError(
                f"ADJ_INVALID_BOUNDS: min ({mn}) must be less than max ({mx})",
                SourceSpan(target_tok.line, target_tok.col),
            )
        if mn is not None and start_v < mn:
            raise ParseError(
                f"ADJ_START_OUT_OF_BOUNDS: start ({start_v}) below min ({mn})",
                SourceSpan(target_tok.line, target_tok.col),
            )
        if mx is not None and start_v > mx:
            raise ParseError(
                f"ADJ_START_OUT_OF_BOUNDS: start ({start_v}) above max ({mx})",
                SourceSpan(target_tok.line, target_tok.col),
            )
        return AdjustingSchedule(
            adj_target=target_tok.value,
            adj_start=params["adj_start"],
            adj_step=params["adj_step"],
            adj_min=params["adj_min"],
            adj_max=params["adj_max"],
        )

    def _parse_interlocking_schedule(self) -> InterlockingSchedule:
        """Interlock|Interlocking "(" R0_kwarg "," T_kwarg ")" (order-independent)"""
        self._advance()
        self._expect(TokenType.LPAREN, "'(' after 'Interlock'")
        r0: int | None = None
        t_value: dict | None = None
        seen: set[str] = set()
        while not self._at(TokenType.RPAREN):
            key_tok = self._expect(TokenType.IDENTIFIER, "Interlock kwarg name")
            if key_tok.value in seen:
                raise ParseError(
                    f"INTERLOCK_DUPLICATE_KWARG: '{key_tok.value}' set twice",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            seen.add(key_tok.value)
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            if key_tok.value == "R0":
                num_tok = self._expect(TokenType.NUMBER, "R0 value")
                if "." in num_tok.value:
                    raise ParseError(
                        f"INTERLOCK_INVALID_R0: R0 must be an integer "
                        f"(got {num_tok.value})",
                        SourceSpan(num_tok.line, num_tok.col, len(num_tok.value)),
                    )
                r0 = int(float(num_tok.value))
                if r0 <= 0:
                    raise ParseError(
                        f"INTERLOCK_NONPOSITIVE_R0: R0 must be positive (got {r0})",
                        SourceSpan(num_tok.line, num_tok.col, len(num_tok.value)),
                    )
            elif key_tok.value == "T":
                val, unit = self._parse_value()
                if unit is None:
                    raise ParseError(
                        "INTERLOCK_MISSING_TIME_UNIT: T requires a time unit",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                if val <= 0:
                    raise ParseError(
                        f"INTERLOCK_NONPOSITIVE_T: T must be positive (got {val})",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                t_value = {"value": val, "time_unit": unit}
            else:
                raise ParseError(
                    f"unknown Interlock kwarg '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            if self._at(TokenType.COMMA):
                self._advance()
        self._expect(TokenType.RPAREN, "closing ')' on Interlock")
        if r0 is None:
            raise ParseError(
                "INTERLOCK_MISSING_R0: Interlock(...) requires 'R0='",
                SourceSpan(1, 1),
            )
        if t_value is None:
            raise ParseError(
                "INTERLOCK_MISSING_T: Interlock(...) requires 'T='",
                SourceSpan(1, 1),
            )
        return InterlockingSchedule(interlock_R0=r0, interlock_T=t_value)

    def _parse_lag(self) -> Modifier:
        """Lag N | Lag(N) | Lag(N, length=K) | LagN (compact form)"""
        head_tok = self._advance()
        n_value: int | None = None
        length = 1
        seen: set[str] = set()
        if head_tok.value != "Lag":
            n_value = int(head_tok.value[3:])
        elif self._at(TokenType.LPAREN):
            self._advance()
            n_tok = self._expect(TokenType.NUMBER, "Lag n value")
            if "." in n_tok.value:
                raise ParseError(
                    f"LAG_NON_INTEGER_N: Lag n must be an integer (got {n_tok.value})",
                    SourceSpan(n_tok.line, n_tok.col, len(n_tok.value)),
                )
            n_value = int(float(n_tok.value))
            while self._at(TokenType.COMMA):
                self._advance()
                key_tok = self._expect(TokenType.IDENTIFIER, "Lag kwarg name")
                if key_tok.value in seen:
                    raise ParseError(
                        f"LAG_DUPLICATE_KWARG: '{key_tok.value}' set twice",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                seen.add(key_tok.value)
                self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
                if key_tok.value == "length":
                    len_tok = self._expect(TokenType.NUMBER, "length value")
                    if "." in len_tok.value:
                        raise ParseError(
                            f"LAG_NON_INTEGER_LENGTH: length must be an integer "
                            f"(got {len_tok.value})",
                            SourceSpan(len_tok.line, len_tok.col, len(len_tok.value)),
                        )
                    length = int(float(len_tok.value))
                else:
                    raise ParseError(
                        f"unknown Lag kwarg '{key_tok.value}'",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
            self._expect(TokenType.RPAREN, "closing ')' on Lag")
        else:
            n_tok = self._expect(TokenType.NUMBER, "Lag n value")
            if "." in n_tok.value:
                raise ParseError(
                    f"LAG_NON_INTEGER_N: Lag n must be an integer (got {n_tok.value})",
                    SourceSpan(n_tok.line, n_tok.col, len(n_tok.value)),
                )
            n_value = int(float(n_tok.value))
        if n_value is None or n_value < 0:
            raise ParseError(
                f"LAG_NEGATIVE_N: Lag n must be non-negative (got {n_value})",
                SourceSpan(head_tok.line, head_tok.col, len(head_tok.value)),
            )
        if length < 1:
            raise ParseError(
                f"LAG_NONPOSITIVE_LENGTH: length must be ≥ 1 (got {length})",
                SourceSpan(head_tok.line, head_tok.col, len(head_tok.value)),
            )
        return Modifier(modifier="Lag", value=float(n_value), length=length)

    def _parse_trial_based(self) -> TrialBased:
        """MTS|GoNoGo "(" kwarg ("," kwarg)* ")" — trial-based schedule.

        MTS params: comparisons (int), consequence (ScheduleExpr), incorrect
            (ScheduleExpr, default EXT), ITI (time value), mts_type (str,
            default "arbitrary").
        GoNoGo params: responseWindow (time value), consequence (ScheduleExpr),
            incorrect (ScheduleExpr, default EXT), falseAlarm (ScheduleExpr,
            default EXT), ITI (time value).
        """
        name_tok = self._expect(TokenType.IDENTIFIER, "trial-based schedule name")
        trial_type = name_tok.value
        self._expect(TokenType.LPAREN, f"'(' after '{trial_type}'")
        params: dict = {}
        seen: set[str] = set()
        while not self._at(TokenType.RPAREN):
            # Accept `LH` as a synonym for `limitedHold` — the lexer emits it
            # as a dedicated LH token, but inside TrialBased kwargs we want
            # identifier semantics.
            head = self._peek()
            if head.type == TokenType.LH:
                self._advance()
                key_tok = head
            else:
                key_tok = self._expect(TokenType.IDENTIFIER, "kwarg name")
            canonical = (
                "mts_type" if key_tok.value == "type"
                else "LH" if head.type == TokenType.LH
                else key_tok.value
            )
            if canonical in seen:
                raise ParseError(
                    f"TRIAL_BASED_DUPLICATE_KWARG: '{canonical}' set more than once",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            seen.add(canonical)
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            key = key_tok.value
            if key in ("consequence", "incorrect", "falseAlarm"):
                sched = self._parse_schedule()
                if isinstance(sched, Compound) and key in ("consequence", "incorrect"):
                    prefix = "MTS" if trial_type == "MTS" else "GONOGO"
                    raise ParseError(
                        f"{prefix}_INVALID_CONSEQUENCE: {trial_type} '{key}' "
                        f"must not be a compound schedule "
                        f"(got {sched.combinator.value})",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                if isinstance(sched, TrialBased) and key in ("consequence", "incorrect"):
                    if trial_type == "MTS":
                        raise ParseError(
                            f"MTS_INVALID_CONSEQUENCE: MTS '{key}' must not "
                            "nest another trial-based schedule",
                            SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                        )
                    raise ParseError(
                        f"GONOGO_RECURSIVE_CONSEQUENCE: GoNoGo '{key}' must "
                        "not recursively nest another GoNoGo/MTS",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                params[key] = sched
            elif key in ("ITI", "responseWindow"):
                val, unit = self._parse_value()
                if val <= 0:
                    raise ParseError(
                        f"TRIAL_BASED_NONPOSITIVE: '{key}' must be positive",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                if unit is None:
                    raise ParseError(
                        f"TRIAL_BASED_MISSING_TIME_UNIT: '{key}' requires a time unit",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                params[key] = val
                params[f"{key}_unit" if key == "ITI" else f"{key}Unit"] = unit
            elif key in ("comparisons", "samples"):
                num = self._expect(TokenType.NUMBER, f"{key} count")
                if "." in num.value:
                    raise ParseError(
                        f"MTS_{key.upper()}_FRACTIONAL: {key} must be integer "
                        f"(got {num.value})",
                        SourceSpan(num.line, num.col, len(num.value)),
                    )
                n = int(float(num.value))
                if key == "comparisons" and n < 2:
                    raise ParseError(
                        f"MTS_COMPARISONS_TOO_FEW: comparisons must be ≥ 2 (got {n})",
                        SourceSpan(num.line, num.col, len(num.value)),
                    )
                params[key] = n
            elif key == "LH":
                # LH=3s keyword inside GoNoGo/MTS: records the limited-hold
                # on the TrialBased leaf as inline `limitedHold` / `limitedHoldUnit`.
                val, unit = self._parse_value()
                if val <= 0:
                    raise ParseError(
                        f"TRIAL_BASED_NONPOSITIVE_LH: LH must be positive "
                        f"(got {val})",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                if unit is None:
                    raise ParseError(
                        "TRIAL_BASED_LH_MISSING_UNIT: LH requires a time unit",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                params["limitedHold"] = val
                params["limitedHoldUnit"] = unit
            elif key == "delay":
                # Matching-to-sample retention interval: zero-delay MTS is
                # simultaneous matching; positive delay is delayed matching.
                val, unit = self._parse_value()
                if val < 0:
                    raise ParseError(
                        f"TRIAL_BASED_NEGATIVE_DELAY: 'delay' must be >= 0",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                if unit is None:
                    raise ParseError(
                        "MTS_DELAY_TIME_UNIT_REQUIRED: delay requires a time unit",
                        SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                    )
                params["delay"] = val
                params["delay_unit"] = unit
            elif key == "correction":
                # Correction-procedure flag: true/false/integer/string alias
                # (Cumming & Berryman, 1965).
                val_tok = self._peek()
                if val_tok.type == TokenType.IDENTIFIER and val_tok.value in ("true", "false"):
                    self._advance()
                    params["correction"] = (
                        {"mode": "unlimited"} if val_tok.value == "true"
                        else {"mode": "disabled"}
                    )
                elif val_tok.type == TokenType.NUMBER:
                    self._advance()
                    if "." in val_tok.value:
                        raise ParseError(
                            "MTS_CORRECTION_FRACTIONAL: correction limit must be integer",
                            SourceSpan(val_tok.line, val_tok.col, len(val_tok.value)),
                        )
                    limit = int(float(val_tok.value))
                    if limit <= 0:
                        raise ParseError(
                            f"MTS_CORRECTION_LIMIT_NONPOSITIVE: correction limit "
                            f"must be positive (got {limit})",
                            SourceSpan(val_tok.line, val_tok.col, len(val_tok.value)),
                        )
                    params["correction"] = {
                        "mode": "bounded",
                        "limit": limit,
                    }
                elif val_tok.type == TokenType.STRING_LITERAL:
                    self._advance()
                    if val_tok.value in ("repeat_until_correct", "unlimited"):
                        params["correction"] = {"mode": "unlimited"}
                    elif val_tok.value == "disabled":
                        params["correction"] = {"mode": "disabled"}
                    else:
                        raise ParseError(
                            f"MTS_CORRECTION_UNKNOWN_STRING: '{val_tok.value}'",
                            SourceSpan(val_tok.line, val_tok.col, len(val_tok.value)),
                        )
                else:
                    raise ParseError(
                        "TRIAL_BASED_INVALID_CORRECTION: 'correction' must be "
                        "true/false, integer, or a string alias",
                        SourceSpan(val_tok.line, val_tok.col),
                    )
            elif key in ("mts_type", "type"):
                id_tok = self._expect(TokenType.IDENTIFIER, "mts_type value")
                if id_tok.value not in ("arbitrary", "identity"):
                    raise ParseError(
                        f"MTS_INVALID_TYPE: '{id_tok.value}' (expected "
                        "'arbitrary' or 'identity')",
                        SourceSpan(id_tok.line, id_tok.col, len(id_tok.value)),
                    )
                params["mts_type"] = id_tok.value
            else:
                raise ParseError(
                    f"unknown {trial_type} kwarg '{key}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            if self._at(TokenType.COMMA):
                self._advance()
        self._expect(TokenType.RPAREN, f"closing ')' on {trial_type}")
        _validate_trial_based(trial_type=trial_type, params=params)
        return TrialBased(trial_type=trial_type, params=params)

    def _parse_pctl_schedule(self) -> Modifier:
        """Pctl(<target>, <rank> [, window=N] [, dir=below|above])"""
        name_tok = self._expect(TokenType.IDENTIFIER, "Pctl keyword")
        self._expect(TokenType.LPAREN, "'(' after Pctl")
        target_tok = self._expect(TokenType.IDENTIFIER, "Pctl target dimension")
        if target_tok.value not in _PCTL_KNOWN_TARGETS:
            raise ParseError(
                f"PCTL_UNKNOWN_TARGET: '{target_tok.value}' (expected one of "
                f"{sorted(_PCTL_KNOWN_TARGETS)})",
                SourceSpan(target_tok.line, target_tok.col, len(target_tok.value)),
            )
        self._expect(TokenType.COMMA, "',' after Pctl target")
        rank_tok = self._expect(TokenType.NUMBER, "Pctl rank")
        if "." in rank_tok.value:
            raise ParseError(
                f"PCTL_INVALID_RANK: Pctl rank must be an integer (got {rank_tok.value})",
                SourceSpan(rank_tok.line, rank_tok.col, len(rank_tok.value)),
            )
        rank = int(float(rank_tok.value))
        if not (0 <= rank <= 100):
            raise ParseError(
                f"PCTL_INVALID_RANK: Pctl rank={rank} must be in [0, 100]",
                SourceSpan(rank_tok.line, rank_tok.col, len(rank_tok.value)),
            )
        window: int | None = None
        direction: str | None = None
        seen: set[str] = set()
        while self._at(TokenType.COMMA):
            self._advance()
            key_tok = self._expect(TokenType.IDENTIFIER, "Pctl keyword arg name")
            if key_tok.value in seen:
                raise ParseError(
                    f"PCTL_DUPLICATE_{key_tok.value.upper()}: '{key_tok.value}' "
                    "set more than once",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
            seen.add(key_tok.value)
            self._expect(TokenType.EQUALS, f"'=' after '{key_tok.value}'")
            if key_tok.value == "window":
                val = self._expect(TokenType.NUMBER, "Pctl window value")
                w = int(float(val.value))
                if w <= 0:
                    raise ParseError(
                        f"PCTL_INVALID_WINDOW: window must be positive (got {w})",
                        SourceSpan(val.line, val.col, len(val.value)),
                    )
                window = w
            elif key_tok.value == "dir":
                val = self._expect(TokenType.IDENTIFIER, "Pctl dir value")
                if val.value not in ("below", "above"):
                    raise ParseError(
                        f"Pctl dir must be 'below' or 'above' (got '{val.value}')",
                        SourceSpan(val.line, val.col, len(val.value)),
                    )
                direction = val.value
            else:
                raise ParseError(
                    f"unknown Pctl keyword arg '{key_tok.value}'",
                    SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
                )
        self._expect(TokenType.RPAREN, "closing ')' on Pctl")
        return Modifier(
            modifier="Pctl",
            pctl_target=target_tok.value,
            pctl_rank=rank,
            pctl_window=window if window is not None else 20,
            pctl_dir=direction if direction is not None else "below",
        )

    def _parse_aversive_schedule(self) -> AversiveSchedule:
        """aversive_schedule ::= AversiveName "(" aversive_param ("," aversive_param)* ")" """
        name_tok = self._expect(TokenType.IDENTIFIER, "aversive schedule name")
        kind = _AVERSIVE_NAME_ALIASES[name_tok.value]
        open_tok = self._expect(TokenType.LPAREN, "'(' after aversive schedule name")
        params: dict = {}
        if not self._at(TokenType.RPAREN):
            self._parse_aversive_param(params, kind=kind)
            while self._at(TokenType.COMMA):
                self._advance()
                self._parse_aversive_param(params, kind=kind)
        self._expect(TokenType.RPAREN, "closing ')' on aversive schedule")
        _validate_aversive_params(
            kind=kind, params=params, span=SourceSpan(open_tok.line, open_tok.col)
        )
        return AversiveSchedule(kind=kind, params=params)

    def _parse_aversive_param(self, params: dict, *, kind: str) -> None:
        """Parse `<name> = <value>` into the canonical params map.

        Name aliases map via `_AVERSIVE_PARAM_ALIASES`. `mode` takes an
        identifier value (`escape` / `fixed`); every other parameter takes a
        time-valued expression (`5s`, `200ms`, `3min`). Duplicate names —
        including via aliases — raise ParseError (SemanticError-shaped
        message so the conformance harness accepts the DslError).
        """
        key_tok = self._expect(TokenType.IDENTIFIER, "aversive parameter name")
        if key_tok.value not in _AVERSIVE_PARAM_ALIASES:
            raise ParseError(
                f"unknown aversive parameter '{key_tok.value}'",
                SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
            )
        canonical = _AVERSIVE_PARAM_ALIASES[key_tok.value]
        if canonical in params:
            raise ParseError(
                f"AVERSIVE_DUPLICATE_PARAM: '{canonical}' appears twice in "
                f"{kind}(...) (canonical and/or aliases collide)",
                SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
            )
        self._expect(TokenType.EQUALS, f"'=' after aversive parameter '{key_tok.value}'")
        if canonical == "mode":
            mode_tok = self._peek()
            # `mode` values are bare identifiers (`escape`, `fixed`). The
            # latter is classified by the lexer as DISTRIBUTION_NAME because
            # it overlaps with the foundations-layer distribution vocabulary.
            if mode_tok.type not in (TokenType.IDENTIFIER, TokenType.DISTRIBUTION_NAME):
                raise ParseError(
                    f"expected identifier for 'mode' value, got {mode_tok.type.name} '{mode_tok.value}'",
                    SourceSpan(mode_tok.line, mode_tok.col),
                )
            if mode_tok.value not in ("escape", "fixed", "response_terminated"):
                raise ParseError(
                    f"AVERSIVE_INVALID_MODE: mode must be one of "
                    f"'escape'/'fixed'/'response_terminated' "
                    f"(got '{mode_tok.value}')",
                    SourceSpan(mode_tok.line, mode_tok.col, len(mode_tok.value)),
                )
            self._advance()
            params[canonical] = mode_tok.value
            return
        value, unit = self._parse_value()
        if unit is None:
            raise ParseError(
                f"AVERSIVE_MISSING_TIME_UNIT: '{canonical}' requires a time unit",
                SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
            )
        if value <= 0:
            raise ParseError(
                f"AVERSIVE_NONPOSITIVE_VALUE: '{canonical}' must be positive (got {value})",
                SourceSpan(key_tok.line, key_tok.col, len(key_tok.value)),
            )
        params[canonical] = {"value": value, "time_unit": unit}

    def _parse_atomic_or_second(self) -> ScheduleExpr:
        """atomic_or_second ::= parametric_atomic ("(" simple_schedule ")")?"""
        atomic = self._parse_parametric_atomic()

        # Check for second-order: FR5(FI30) or FR5(x) with `x` a let-binding.
        if self._at(TokenType.LPAREN):
            self._advance()
            unit = self._parse_second_order_unit()
            self._expect(TokenType.RPAREN, "second-order schedule closing paren")
            return SecondOrder(overall=atomic, unit=unit)

        return atomic

    def _parse_second_order_unit(self):
        """A SecondOrder's inner unit may be a parametric Atomic (`FI30`) or
        a let-bound identifier (`x`). Higher-arity inner forms are rejected
        here; use explicit Atomic in source."""
        tok = self._peek()
        if tok.type == TokenType.IDENTIFIER and not (
            self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type == TokenType.LPAREN
        ):
            # Identifier reference (let-bound Atomic).
            self._advance()
            return IdentifierRef(name=tok.value)
        return self._parse_parametric_atomic()

    def _parse_parametric_atomic(self) -> Atomic:
        """parametric_atomic ::= dist domain ws? value"""
        tok = self._expect(TokenType.SCHEDULE_TYPE, "schedule type")
        keyword = tok.value[:2]
        dist = Distribution(keyword[0])
        domain = Domain(keyword[1])
        val, unit = self._parse_value()
        return Atomic(
            schedule_type=ScheduleType(dist, domain),
            value=val,
            time_unit=unit,
        )

    def _parse_compound(self) -> Compound:
        """compound ::= combinator "(" positional_args ("," keyword_arg)* ")" """
        tok = self._expect(TokenType.COMBINATOR)
        # `Interp` is an alias for `Interpolate` — canonicalise at parse time
        # so the serialised form uses the canonical combinator name.
        combinator = Combinator.INTERPOLATE if tok.value == "Interp" else Combinator(tok.value)
        self._expect(TokenType.LPAREN, f"{tok.value} opening paren")

        components: list[ScheduleExpr] = []
        components.append(self._parse_schedule())

        if not self._at(TokenType.COMMA):
            raise ParseError(
                f"{tok.value} requires at least 2 components",
                SourceSpan(tok.line, tok.col),
            )

        # Parse remaining positional args and keyword args
        params: dict[str, CombinatorParamValue] = {}
        directional_entries: list[DirectionalEntry] = []
        has_kw = False
        # Separate trackers for one-off kwargs whose presence is tracked by
        # their canonical name but whose AST emission may be conditional
        # (e.g. Overlay `target=all` is the default and does not appear in
        # params; still count the occurrence to catch duplicate-target
        # errors).
        overlay_target_seen = False
        while self._at(TokenType.COMMA):
            self._advance()
            # Check if next token is a keyword arg name
            if self._at(TokenType.KW_ARG_NAME):
                has_kw = True
                kw_tok = self._advance()
                canonical = KW_ARG_KEYWORDS[kw_tok.value]

                # Directional / indexed form: COD(x->y)=value, PUNISH(x->y)=
                # <schedule>, PUNISH(N)=<schedule>, PUNISH(changeover)=<schedule>
                if self._at(TokenType.LPAREN):
                    if canonical == "COD":
                        self._advance()  # consume (
                        from_ref = self._parse_dir_ref()
                        self._expect(TokenType.ARROW, "-> in directional keyword arg")
                        to_ref = self._parse_dir_ref()
                        self._expect(TokenType.RPAREN, "directional keyword closing paren")
                        self._expect(TokenType.EQUALS)
                        val, unit = self._parse_value()
                        directional_entries.append(
                            DirectionalEntry(from_ref=from_ref, to_ref=to_ref, value=val, time_unit=unit)
                        )
                    elif canonical == "PUNISH":
                        self._advance()  # consume (
                        # Three sub-forms distinguished by the contents:
                        # 1) N->M  → directional {from, to, schedule}
                        # 2) changeover → {"changeover": <schedule>}
                        # 3) N   → component {component: N, schedule}
                        peek1 = self._peek()
                        if peek1.type == TokenType.IDENTIFIER and peek1.value == "changeover":
                            self._advance()
                            self._expect(TokenType.RPAREN, "PUNISH closing paren")
                            self._expect(TokenType.EQUALS)
                            sched_val = self._parse_schedule()
                            existing = params.get("PUNISH")
                            if existing is None:
                                params["PUNISH"] = {"changeover": sched_val}
                            elif "directional" in existing:
                                raise ParseError(
                                    "PUNISH_TARGET_CONFLICT: PUNISH(x->y) "
                                    "and PUNISH(changeover) cannot coexist",
                                    SourceSpan(peek1.line, peek1.col),
                                )
                            else:
                                raise ParseError(
                                    "PUNISH_DUPLICATE: PUNISH(changeover) "
                                    "set more than once",
                                    SourceSpan(peek1.line, peek1.col),
                                )
                        elif peek1.type == TokenType.NUMBER or (
                            peek1.type == TokenType.IDENTIFIER
                        ):
                            first_ref = self._parse_dir_ref()
                            if self._at(TokenType.ARROW):
                                self._advance()
                                to_ref = self._parse_dir_ref()
                                self._expect(TokenType.RPAREN, "PUNISH closing paren")
                                self._expect(TokenType.EQUALS)
                                sched_val = self._parse_schedule()
                                if first_ref == to_ref:
                                    raise ParseError(
                                        f"PUNISH_SELF_REFERENCE: PUNISH("
                                        f"{first_ref}->{to_ref}) — a component "
                                        "cannot punish its own self-transition",
                                        SourceSpan(peek1.line, peek1.col),
                                    )
                                existing = params.setdefault("PUNISH", {})
                                if "changeover" in existing:
                                    raise ParseError(
                                        "PUNISH_TARGET_CONFLICT: PUNISH(x->y) "
                                        "and PUNISH(changeover) cannot coexist",
                                        SourceSpan(peek1.line, peek1.col),
                                    )
                                dir_list = existing.setdefault("directional", [])
                                for prior in dir_list:
                                    if (prior["from"], prior["to"]) == (first_ref, to_ref):
                                        raise ParseError(
                                            f"PUNISH_DUPLICATE: PUNISH("
                                            f"{first_ref}->{to_ref}) appears twice",
                                            SourceSpan(peek1.line, peek1.col),
                                        )
                                dir_list.append(
                                    {"from": first_ref, "to": to_ref, "schedule": sched_val}
                                )
                            else:
                                self._expect(TokenType.RPAREN, "PUNISH closing paren")
                                self._expect(TokenType.EQUALS)
                                sched_val = self._parse_schedule()
                                existing = params.setdefault("PUNISH", {})
                                existing.setdefault("component", []).append(
                                    {"component": first_ref, "schedule": sched_val}
                                )
                        else:
                            raise ParseError(
                                f"PUNISH: expected index, 'changeover', or direction, "
                                f"got {peek1.type.name} '{peek1.value}'",
                                SourceSpan(peek1.line, peek1.col),
                            )
                    else:
                        raise ParseError(
                            f"INVALID_DIRECTIONAL_KW: directional form "
                            f"is valid for COD/PUNISH only, not {canonical}",
                            SourceSpan(kw_tok.line, kw_tok.col),
                        )
                else:
                    # Scalar form: COD=value
                    self._expect(TokenType.EQUALS)
                    val, unit = self._parse_value()
                    if canonical in params:
                        raise ParseError(
                            f"duplicate keyword argument '{canonical}'",
                            SourceSpan(kw_tok.line, kw_tok.col),
                        )
                    params[canonical] = CompoundParam(value=val, time_unit=unit)
            elif (
                self._at(TokenType.IDENTIFIER)
                and self._peek().value == "target"
                and combinator == Combinator.OVERLAY
                and self._pos + 1 < len(self._tokens)
                and self._tokens[self._pos + 1].type == TokenType.EQUALS
            ):
                # Overlay(..., target=changeover|all|component_1|...)
                has_kw = True
                self._advance()  # consume "target"
                self._expect(TokenType.EQUALS)
                val_tok = self._expect(TokenType.IDENTIFIER, "Overlay target value")
                if val_tok.value not in ("all", "changeover") and not val_tok.value.startswith("component_"):
                    raise ParseError(
                        f"OVERLAY_TARGET_UNKNOWN: target='{val_tok.value}' is "
                        "not a valid value (expected 'all' / 'changeover' / "
                        "'component_N')",
                        SourceSpan(val_tok.line, val_tok.col, len(val_tok.value)),
                    )
                if overlay_target_seen:
                    raise ParseError(
                        "OVERLAY_DUPLICATE_TARGET: target set more than once",
                        SourceSpan(val_tok.line, val_tok.col),
                    )
                overlay_target_seen = True
                if val_tok.value != "all":
                    params["target"] = val_tok.value
            elif (
                self._at(TokenType.IDENTIFIER)
                and self._peek().value in ("count", "onset")
                and combinator == Combinator.INTERPOLATE
                and self._pos + 1 < len(self._tokens)
                and self._tokens[self._pos + 1].type == TokenType.EQUALS
            ):
                # Interpolate-specific keyword args: count (integer, required)
                # and onset (duration, optional; when the alternate schedule
                # starts). Both recorded as CompoundParam entries.
                has_kw = True
                kw_tok = self._advance()
                self._expect(TokenType.EQUALS)
                val, unit = self._parse_value()
                if kw_tok.value in params:
                    raise ParseError(
                        f"duplicate keyword argument '{kw_tok.value}'",
                        SourceSpan(kw_tok.line, kw_tok.col),
                    )
                params[kw_tok.value] = CompoundParam(value=val, time_unit=unit)
            else:
                # Positional arg — must not appear after keyword args
                if has_kw:
                    next_tok = self._peek()
                    raise ParseError(
                        f"positional argument after keyword argument in {tok.value}",
                        SourceSpan(next_tok.line, next_tok.col),
                    )
                components.append(self._parse_schedule())

        self._expect(TokenType.RPAREN, f"{tok.value} closing paren")

        # Interpolate / Overlay require exactly 2 positional components; catch
        # at parse time so the error surfaces before analysis.
        if combinator == Combinator.INTERPOLATE and len(components) != 2:
            raise ParseError(
                f"INTERPOLATE_REQUIRES_TWO: Interpolate requires exactly 2 "
                f"components (baseline + insertion), got {len(components)}",
                SourceSpan(tok.line, tok.col),
            )

        # Resolve identifier-based dir_ref to 1-indexed integers.
        # Applies to both COD directional entries and PUNISH directional payloads.
        name_to_idx: dict[str, int] = {}
        for i, comp in enumerate(components, start=1):
            if isinstance(comp, IdentifierRef):
                name_to_idx[comp.name] = i

        if directional_entries:
            resolved: list[DirectionalEntry] = []
            for entry in directional_entries:
                from_ref = entry.from_ref
                to_ref = entry.to_ref
                if isinstance(from_ref, str):
                    if from_ref not in name_to_idx:
                        raise ParseError(
                            f"directional ref '{from_ref}' does not match any component",
                            SourceSpan(tok.line, tok.col),
                        )
                    from_ref = name_to_idx[from_ref]
                if isinstance(to_ref, str):
                    if to_ref not in name_to_idx:
                        raise ParseError(
                            f"directional ref '{to_ref}' does not match any component",
                            SourceSpan(tok.line, tok.col),
                        )
                    to_ref = name_to_idx[to_ref]
                resolved.append(DirectionalEntry(from_ref=from_ref, to_ref=to_ref, value=entry.value, time_unit=entry.time_unit))

            base = params.pop("COD", None) if "COD" in params else None
            base_param = base if isinstance(base, CompoundParam) else None
            params["COD"] = DirectionalCOD(
                base=base_param,
                directional=tuple(resolved),
            )

        # Resolve identifier-based refs in PUNISH directional entries.
        punish_payload = params.get("PUNISH")
        if isinstance(punish_payload, dict) and "directional" in punish_payload:
            for entry in punish_payload["directional"]:
                for key in ("from", "to"):
                    ref = entry.get(key)
                    if isinstance(ref, str):
                        if ref not in name_to_idx:
                            raise ParseError(
                                f"PUNISH directional ref '{ref}' does not match any component",
                                SourceSpan(tok.line, tok.col),
                            )
                        entry[key] = name_to_idx[ref]

        return Compound(
            combinator=combinator,
            components=tuple(components),
            params=params if params else None,
        )

    def _parse_dir_ref(self) -> int | str:
        """dir_ref ::= number | ident

        Returns int (1-indexed) for numeric refs, or str for identifier refs.
        Identifier refs are resolved to integer indices by the semantic analyzer.
        """
        tok = self._peek()
        if tok.type == TokenType.NUMBER:
            self._advance()
            return int(float(tok.value))
        if tok.type == TokenType.IDENTIFIER:
            self._advance()
            return tok.value
        raise ParseError(
            f"expected number or identifier in directional reference, "
            f"got {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )

    def _parse_dr_mod(self) -> Modifier:
        """dr_mod ::= ("DRL" | "DRH" | "DRO") ws? value"""
        tok = self._expect(TokenType.DR_MOD)
        keyword = tok.value[:3]
        val, unit = self._parse_value()
        return Modifier(modifier=keyword, value=val, time_unit=unit)

    def _parse_pr_mod(self) -> Modifier:
        """pr_mod ::= "PR" ("(" pr_opts ")")? | "PR" NUMBER"""
        self._expect(TokenType.PR)

        # PR N shorthand: linear step with start=N, increment=N
        # (Jarmolowicz & Lattal, 2010).
        if self._at(TokenType.NUMBER):
            num_tok = self._advance()
            if "." in num_tok.value:
                raise ParseError(
                    f"PR_NON_INTEGER: PR shorthand 'PR N' requires an integer "
                    f"(got {num_tok.value})",
                    SourceSpan(num_tok.line, num_tok.col, len(num_tok.value)),
                )
            n = float(num_tok.value)
            return Modifier(
                modifier="PR",
                pr_step="linear",
                pr_start=n,
                pr_increment=n,
            )

        if not self._at(TokenType.LPAREN):
            raise ParseError(
                "PR_BARE: bare 'PR' requires a number (e.g. 'PR 5') or "
                "parenthesized options (e.g. 'PR(linear, start=5)' / "
                "'PR(hodos)')",
                SourceSpan(1, 1),
            )

        self._advance()  # consume (

        # PR(start=N, step=N) shorthand: keyword-only form, elides the
        # step-function name. Interpreted as `linear` with start=N and
        # increment=step. `step=` is accepted as an alias for `increment=`.
        # This matches the behavioral-economics convention where the
        # arithmetic-progression form is the default assumption.
        if self._at(TokenType.PR_PARAM) or (
            self._at(TokenType.IDENTIFIER) and self._peek().value == "step"
        ):
            pr_step = "linear"
            step_tok = None  # no explicit step-function token
        else:
            step_tok = self._expect(TokenType.DISTRIBUTION_NAME, "PR step type")
            if step_tok.value not in ("hodos", "linear", "exponential", "geometric"):
                raise ParseError(
                    f"PR step type must be one of hodos/linear/exponential/geometric, "
                    f"got '{step_tok.value}'",
                    SourceSpan(step_tok.line, step_tok.col),
                )
            pr_step = step_tok.value
        pr_start: float | None = None
        pr_increment: float | None = None
        pr_ratio: float | None = None

        # In `PR(start=N, step=N)` shorthand the first kwarg is adjacent to
        # the opening paren with no leading comma; in the canonical
        # `PR(linear, start=N, increment=N)` form the kwargs follow the
        # step-function token and each is preceded by a comma. Accept both
        # by checking the leading token before each kwarg.
        is_first_kwarg = step_tok is None
        while is_first_kwarg or self._at(TokenType.COMMA):
            if not is_first_kwarg:
                self._advance()  # consume comma
            is_first_kwarg = False
            param_tok = self._peek()
            if param_tok.type not in (TokenType.PR_PARAM, TokenType.IDENTIFIER):
                raise ParseError(
                    f"expected PR parameter name, got {param_tok.type.name} '{param_tok.value}'",
                    SourceSpan(param_tok.line, param_tok.col),
                )
            self._advance()
            self._expect(TokenType.EQUALS)
            num_tok = self._expect(TokenType.NUMBER)
            # `step=N` is a keyword-form alias for `increment=N` — the
            # arithmetic-progression quantity. Accept it only in the
            # keyword-first shorthand (where it is most commonly written).
            param_name = (
                "increment" if param_tok.value == "step" else param_tok.value
            )
            if param_name == "start":
                if "." in num_tok.value:
                    raise ParseError(
                        f"PR_NON_INTEGER_START: PR start must be integer "
                        f"(got {num_tok.value})",
                        SourceSpan(num_tok.line, num_tok.col, len(num_tok.value)),
                    )
                pr_start = float(num_tok.value)
            elif param_name == "increment":
                if "." in num_tok.value:
                    raise ParseError(
                        f"PR_NON_INTEGER_INCREMENT: PR increment must be integer "
                        f"(got {num_tok.value})",
                        SourceSpan(num_tok.line, num_tok.col, len(num_tok.value)),
                    )
                pr_increment = float(num_tok.value)
            elif param_name == "ratio":
                pr_ratio = float(num_tok.value)
                if pr_step == "geometric" and pr_ratio <= 1:
                    raise ParseError(
                        f"PR_GEOMETRIC_RATIO_NOT_PROGRESSIVE: geometric ratio "
                        f"must be > 1 to produce a progressive schedule "
                        f"(got {pr_ratio})",
                        SourceSpan(num_tok.line, num_tok.col, len(num_tok.value)),
                    )
            else:
                raise ParseError(
                    f"unknown PR kwarg '{param_tok.value}'",
                    SourceSpan(param_tok.line, param_tok.col, len(param_tok.value)),
                )

        self._expect(TokenType.RPAREN, "PR closing paren")
        return Modifier(
            modifier="PR",
            pr_step=pr_step,
            pr_start=pr_start,
            pr_increment=pr_increment,
            pr_ratio=pr_ratio,
        )

    def _parse_repeat(self) -> Modifier:
        """repeat ::= "Repeat" "(" number "," schedule ")" """
        self._expect(TokenType.REPEAT)
        self._expect(TokenType.LPAREN, "Repeat opening paren")
        count_tok = self._expect(TokenType.NUMBER, "repeat count")
        if "." in count_tok.value:
            raise ParseError(
                f"REPEAT_NON_INTEGER_COUNT: Repeat count must be integer "
                f"(got {count_tok.value})",
                SourceSpan(count_tok.line, count_tok.col, len(count_tok.value)),
            )
        self._expect(TokenType.COMMA, "Repeat comma")
        inner = self._parse_schedule()
        self._expect(TokenType.RPAREN, "Repeat closing paren")
        return Modifier(modifier="Repeat", value=float(count_tok.value), inner=inner)

    def _parse_value(self) -> tuple[float, str | None]:
        """value ::= number time_unit?"""
        num_tok = self._expect(TokenType.NUMBER, "numeric value")
        val = float(num_tok.value)
        unit: str | None = None
        if self._at(TokenType.TIME_UNIT):
            unit = self._advance().value
        return val, unit
