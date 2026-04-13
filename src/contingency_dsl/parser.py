"""Recursive descent parser for contingency-dsl.

Parses a token stream into an AST (Program node).
LL(2): the only lookahead beyond 1 is FR5 vs FR5(FI30) for second-order,
resolved by peeking for '(' after parsing the atomic.
"""

from __future__ import annotations

from __future__ import annotations

from typing import TYPE_CHECKING

from .ast import (
    AnnotatedSchedule,
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
from .enums import Combinator, Distribution, Domain, LOWERCASE_RESERVED
from .errors import ParseError, SourceSpan
from .lexer import tokenize
from .tokens import Token, TokenType

if TYPE_CHECKING:
    from .extensions import ExtensionRegistry


def parse(source: str, *, extensions: ExtensionRegistry | None = None) -> Program:
    """Parse DSL source text into a Program AST.

    Args:
        source: DSL source text.
        extensions: Optional extension registry. When provided, @-annotations
            are parsed; when None (default), @ is a parse error.
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

    # --- Grammar productions ---

    def parse_program(self) -> Program:
        """program ::= param_decl* binding* schedule"""
        param_decls: list[ParamDecl] = []
        bindings: list[Binding] = []

        # Parse param_decls: ("LH" | "RD") "=" value
        while self._at(TokenType.LH, TokenType.RD):
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

        # Expect EOF
        if not self._at(TokenType.EOF):
            tok = self._peek()
            raise ParseError(
                f"unexpected token after schedule: {tok.type.name} '{tok.value}'",
                SourceSpan(tok.line, tok.col),
            )

        return Program(
            param_decls=tuple(param_decls),
            bindings=tuple(bindings),
            schedule=schedule,
        )

    def _parse_param_decl(self) -> ParamDecl:
        """param_decl ::= ("LH" | "RD") "=" value"""
        tok = self._advance()  # consume LH or RD token
        # Normalize alias: ReinforcementDelay -> RD, LimitedHold -> LH
        if tok.type == TokenType.RD:
            name = "RD"
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
        """schedule ::= base_schedule ("LH" ws? value)? annotation*"""
        base = self._parse_base_schedule()

        # Check for LH postfix
        if self._at(TokenType.LH):
            # Must NOT be followed by "=" (that's a param_decl, not postfix LH)
            if self._pos + 1 < len(self._tokens) and self._tokens[self._pos + 1].type == TokenType.EQUALS:
                return self._maybe_wrap_annotations(base)
            self._advance()  # consume LH
            hold_val, hold_unit = self._parse_value()
            base = LimitedHold(hold_duration=hold_val, inner=base, time_unit=hold_unit)

        return self._maybe_wrap_annotations(base)

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
            name = name_tok.value

            # Parse arguments: "(" args ")"
            args: list[AnnotationArg] = []
            if self._at(TokenType.LPAREN):
                self._advance()  # consume (

                if not self._at(TokenType.RPAREN):
                    args.append(self._parse_annotation_arg())
                    while self._at(TokenType.COMMA):
                        self._advance()
                        args.append(self._parse_annotation_arg())

                self._expect(TokenType.RPAREN, f"@{name} closing paren")

            annotations.append(Annotation(name=name, args=tuple(args)))
        return annotations

    def _parse_annotation_arg(self) -> AnnotationArg:
        """Parse a single annotation argument: positional or key=value."""
        tok = self._peek()

        # Check for keyword argument: ident "=" value
        if tok.type == TokenType.IDENTIFIER:
            if (
                self._pos + 1 < len(self._tokens)
                and self._tokens[self._pos + 1].type == TokenType.EQUALS
            ):
                key_tok = self._advance()  # consume key
                self._advance()  # consume =
                val = self._parse_annotation_value()
                return AnnotationArg(value=val, key=key_tok.value)

        # Positional argument (string or number)
        val = self._parse_annotation_value()
        return AnnotationArg(value=val)

    def _parse_annotation_value(self) -> str | float:
        """Parse an annotation value: string literal or number."""
        tok = self._peek()
        if tok.type == TokenType.STRING_LITERAL:
            self._advance()
            return tok.value
        if tok.type == TokenType.NUMBER:
            self._advance()
            return float(tok.value)
        raise ParseError(
            f"expected string or number in annotation argument, got {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )

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

        # Identifier reference
        if tok.type == TokenType.IDENTIFIER:
            self._advance()
            return IdentifierRef(name=tok.value)

        # Error
        if tok.type == TokenType.EOF:
            raise ParseError("unexpected end of input", SourceSpan(tok.line, tok.col))

        raise ParseError(
            f"unexpected token: {tok.type.name} '{tok.value}'",
            SourceSpan(tok.line, tok.col),
        )

    def _parse_atomic_or_second(self) -> ScheduleExpr:
        """atomic_or_second ::= parametric_atomic ("(" simple_schedule ")")?"""
        atomic = self._parse_parametric_atomic()

        # Check for second-order: FR5(FI30)
        if self._at(TokenType.LPAREN):
            self._advance()
            unit = self._parse_parametric_atomic()
            self._expect(TokenType.RPAREN, "second-order schedule closing paren")
            return SecondOrder(overall=atomic, unit=unit)

        return atomic

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
        """compound ::= combinator "(" schedule_list ")" """
        tok = self._expect(TokenType.COMBINATOR)
        combinator = Combinator(tok.value)
        self._expect(TokenType.LPAREN, f"{tok.value} opening paren")

        components: list[ScheduleExpr] = []
        components.append(self._parse_schedule())

        if not self._at(TokenType.COMMA):
            raise ParseError(
                f"{tok.value} requires at least 2 components",
                SourceSpan(tok.line, tok.col),
            )

        while self._at(TokenType.COMMA):
            self._advance()
            components.append(self._parse_schedule())

        self._expect(TokenType.RPAREN, f"{tok.value} closing paren")
        return Compound(combinator=combinator, components=tuple(components))

    def _parse_dr_mod(self) -> Modifier:
        """dr_mod ::= ("DRL" | "DRH" | "DRO") ws? value"""
        tok = self._expect(TokenType.DR_MOD)
        keyword = tok.value[:3]
        val, unit = self._parse_value()
        return Modifier(modifier=keyword, value=val, time_unit=unit)

    def _parse_pr_mod(self) -> Modifier:
        """pr_mod ::= "PR" ("(" pr_opts ")")?"""
        self._expect(TokenType.PR)

        if not self._at(TokenType.LPAREN):
            return Modifier(modifier="PR", pr_step="hodos")

        self._advance()  # consume (
        step_tok = self._expect(TokenType.PR_STEP, "PR step type")
        pr_step = step_tok.value
        pr_start: float | None = None
        pr_increment: float | None = None

        while self._at(TokenType.COMMA):
            self._advance()
            param_tok = self._expect(TokenType.PR_PARAM, "PR parameter name")
            self._expect(TokenType.EQUALS)
            num_tok = self._expect(TokenType.NUMBER)
            if param_tok.value == "start":
                pr_start = float(num_tok.value)
            elif param_tok.value == "increment":
                pr_increment = float(num_tok.value)

        self._expect(TokenType.RPAREN, "PR closing paren")
        return Modifier(
            modifier="PR",
            pr_step=pr_step,
            pr_start=pr_start,
            pr_increment=pr_increment,
        )

    def _parse_repeat(self) -> Modifier:
        """repeat ::= "Repeat" "(" number "," schedule ")" """
        self._expect(TokenType.REPEAT)
        self._expect(TokenType.LPAREN, "Repeat opening paren")
        count_tok = self._expect(TokenType.NUMBER, "repeat count")
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
