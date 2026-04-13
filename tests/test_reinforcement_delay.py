"""Tests for RD (ReinforcementDelay) param_decl support.

RD is a program-level parameter only (no expression-level syntax).
Per-schedule delays use Tand(S, FT d) — see conformance/core/reinforcement_delay.json.
"""

from __future__ import annotations

import pytest

from contingency_dsl.parser import parse
from contingency_dsl.ast import Atomic, ParamDecl, Program, ScheduleType, Special
from contingency_dsl.enums import Distribution, Domain
from contingency_dsl.serializer import to_dict
from contingency_dsl.printer import format_program
from contingency_dsl.analyzer import analyze
from contingency_dsl.errors import ParseError, SemanticError


class TestRDParamDecl:
    """RD as program-level param_decl."""

    def test_rd_basic_ms(self) -> None:
        prog = parse("RD = 500ms\nFR5")
        assert len(prog.param_decls) == 1
        assert prog.param_decls[0].name == "RD"
        assert prog.param_decls[0].value == 500.0
        assert prog.param_decls[0].time_unit == "ms"

    def test_rd_basic_s(self) -> None:
        prog = parse("RD = 2s\nVI60s")
        assert prog.param_decls[0].name == "RD"
        assert prog.param_decls[0].value == 2.0
        assert prog.param_decls[0].time_unit == "s"

    def test_rd_zero(self) -> None:
        prog = parse("RD = 0s\nFR10")
        assert prog.param_decls[0].value == 0.0
        assert prog.param_decls[0].time_unit == "s"

    def test_rd_alias_reinforcement_delay(self) -> None:
        prog = parse("ReinforcementDelay = 1s\nVI60s")
        assert prog.param_decls[0].name == "RD"
        assert prog.param_decls[0].value == 1.0
        assert prog.param_decls[0].time_unit == "s"

    def test_rd_with_lh(self) -> None:
        prog = parse("LH = 10s\nRD = 500ms\nConc(VI30s, VI60s)")
        names = [d.name for d in prog.param_decls]
        assert names == ["LH", "RD"]
        rd = prog.param_decls[1]
        assert rd.name == "RD"
        assert rd.value == 500.0
        assert rd.time_unit == "ms"


class TestRDSerialization:
    """to_dict produces conformance-test-compatible output."""

    def test_rd_to_dict(self) -> None:
        prog = parse("RD = 500ms\nFR5")
        d = to_dict(prog)
        assert d["param_decls"] == [
            {"type": "ParamDecl", "name": "RD", "value": 500.0, "time_unit": "ms"}
        ]

    def test_rd_alias_to_dict(self) -> None:
        prog = parse("ReinforcementDelay = 1s\nVI60s")
        d = to_dict(prog)
        assert d["param_decls"][0]["name"] == "RD"


class TestRDPrinter:
    """format_program roundtrips RD param_decl."""

    def test_rd_format(self) -> None:
        prog = parse("RD = 500ms\nFR5")
        text = format_program(prog)
        assert "RD = 500ms" in text

    def test_rd_with_lh_format(self) -> None:
        prog = parse("LH = 10s\nRD = 500ms\nFR5")
        text = format_program(prog)
        assert "LH = 10s" in text
        assert "RD = 500ms" in text


class TestRDAnalyzer:
    """Semantic validation and warnings for RD."""

    def test_rd_large_delay_warning(self) -> None:
        prog = parse("RD = 60s\nFR5")
        result = analyze(prog)
        warn_codes = [w for w in result.warnings if "RD_LARGE_DELAY" in w]
        assert len(warn_codes) == 1

    def test_rd_30s_no_warning(self) -> None:
        prog = parse("RD = 30s\nFR5")
        result = analyze(prog)
        warn_codes = [w for w in result.warnings if "RD_LARGE_DELAY" in w]
        assert len(warn_codes) == 0

    def test_rd_zero_no_warning(self) -> None:
        prog = parse("RD = 0s\nFR5")
        result = analyze(prog)
        warn_codes = [w for w in result.warnings if "RD_LARGE_DELAY" in w]
        assert len(warn_codes) == 0

    def test_rd_no_time_unit_error(self) -> None:
        with pytest.raises((SemanticError, ParseError)):
            prog = parse("RD = 5\nFR5")
            analyze(prog)

    def test_rd_preserved_in_analyzed_output(self) -> None:
        """RD param_decl is preserved (not consumed) after analysis."""
        prog = parse("RD = 500ms\nFR5")
        result = analyze(prog)
        rd_decls = [d for d in result.program.param_decls if d.name == "RD"]
        assert len(rd_decls) == 1
        assert rd_decls[0].value == 500.0
