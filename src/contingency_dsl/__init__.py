"""contingency-dsl: Python reference parser for the contingency DSL."""

from .ast import (
    AnnotatedSchedule,
    AnnotatedScheduleExpr,
    Annotation,
    AnnotationArg,
    Atomic,
    Binding,
    Compound,
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
from .extensions import ExtensionModule, ExtensionRegistry
from .analyzer import AnalysisResult, analyze
from .parser import parse
from .printer import format_expr, format_program
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
    "ExtensionModule",
    "ExtensionRegistry",
    # Analyzer
    "analyze",
    "AnalysisResult",
    # Printer
    "format_expr",
    "format_program",
    # Serializer
    "to_dict",
    "from_dict",
]
