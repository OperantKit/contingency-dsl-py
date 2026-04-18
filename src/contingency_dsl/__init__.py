"""contingency-dsl: Python reference parser for the contingency DSL."""

from .ast import (
    AnnotatedSchedule,
    AnnotatedScheduleExpr,
    Annotation,
    AnnotationArg,
    Atomic,
    Binding,
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
from .errors import DslError, LexError, ParseError, SemanticError
from .extensions import (
    CyclicDependencyError,
    ExtensionModule,
    ExtensionRegistry,
    UnknownPrimitiveError,
)
from .analyzer import AnalysisResult, analyze
from .parser import parse
from .printer import format_expr, format_program
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
    RespondentExpr,
    Serial,
    TrulyRandom,
    USOnly,
)
from .serializer import from_dict, to_dict

__all__ = [
    # Parser
    "parse",
    # AST nodes
    "AnnotatedSchedule",
    "AnnotatedScheduleExpr",
    "Annotation",
    "AnnotationArg",
    "Atomic",
    "Binding",
    "Compound",
    "IdentifierRef",
    "LimitedHold",
    "Modifier",
    "ParamDecl",
    "Program",
    "ScheduleExpr",
    "ScheduleType",
    "SecondOrder",
    "Special",
    # Enums
    "Combinator",
    "Distribution",
    "Domain",
    # Errors
    "DslError",
    "LexError",
    "ParseError",
    "SemanticError",
    # Extensions
    "CyclicDependencyError",
    "ExtensionModule",
    "ExtensionRegistry",
    "UnknownPrimitiveError",
    # Analyzer
    "analyze",
    "AnalysisResult",
    # Printer
    "format_expr",
    "format_program",
    # Serializer
    "to_dict",
    "from_dict",
    # Experiment layer
    "Criterion",
    "CumulativeReinforcements",
    "Experiment",
    "ExperimenterJudgment",
    "FixedSessions",
    "Paper",
    "PerformanceCriterion",
    "Phase",
    "PhaseRef",
    "PhaseSchedule",
    "PhaseSequence",
    "Stability",
    # Respondent Tier A primitives
    "CSOnly",
    "RespondentCompound",
    "Contingency",
    "Differential",
    "Duration",
    "ExplicitlyUnpaired",
    "Extinction",
    "ITI",
    "PairBackward",
    "PairForwardDelay",
    "PairForwardTrace",
    "PairSimultaneous",
    "RespondentExpr",
    "Serial",
    "TrulyRandom",
    "USOnly",
]
