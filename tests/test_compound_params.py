"""Tests for Compound keyword args: COD, FRCO, BO.

Grammar §7-14, §35-36: COD/FRCO on Conc, BO on Mult/Mix.
"""

from __future__ import annotations

import pytest

from contingency_dsl.parser import parse
from contingency_dsl.serializer import to_dict
from contingency_dsl.printer import format_program
from contingency_dsl.analyzer import analyze
from contingency_dsl.errors import ParseError, SemanticError


class TestCODParsing:
    """COD keyword arg on Conc."""

    def test_conc_with_cod(self) -> None:
        prog = parse("Conc(VI30s, VI60s, COD=2s)")
        d = to_dict(prog)
        sched = d["schedule"]
        assert sched["type"] == "Compound"
        assert sched["combinator"] == "Conc"
        assert len(sched["components"]) == 2
        assert "params" in sched
        assert "COD" in sched["params"]
        assert sched["params"]["COD"]["value"] == 2.0
        assert sched["params"]["COD"]["time_unit"] == "s"

    def test_conc_cod_zero(self) -> None:
        prog = parse("Conc(VI30s, VI60s, COD=0s)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["COD"]["value"] == 0.0

    def test_conc_cod_alias(self) -> None:
        prog = parse("Conc(VI30s, VI60s, ChangeoverDelay=2s)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["COD"]["value"] == 2.0

    def test_conc_cod_ms(self) -> None:
        prog = parse("Conc(VI30s, VI60s, COD=500ms)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["COD"]["value"] == 500.0
        assert d["schedule"]["params"]["COD"]["time_unit"] == "ms"


class TestFRCOParsing:
    """FRCO keyword arg on Conc."""

    def test_conc_with_frco(self) -> None:
        prog = parse("Conc(VI30s, VI60s, FRCO=5)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["FRCO"]["value"] == 5

    def test_conc_cod_and_frco(self) -> None:
        prog = parse("Conc(VI30s, VI60s, COD=2s, FRCO=5)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["COD"]["value"] == 2.0
        assert d["schedule"]["params"]["FRCO"]["value"] == 5


class TestBOParsing:
    """BO keyword arg on Mult/Mix."""

    def test_mult_with_bo(self) -> None:
        prog = parse("Mult(FR5, EXT, BO=5s)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["BO"]["value"] == 5.0
        assert d["schedule"]["params"]["BO"]["time_unit"] == "s"

    def test_mix_with_bo(self) -> None:
        prog = parse("Mix(FR5, FR10, BO=3s)")
        d = to_dict(prog)
        assert d["schedule"]["params"]["BO"]["value"] == 3.0


class TestSemanticConstraints:
    """Grammar §8, §13: COD/FRCO on Conc only, BO on Mult/Mix only."""

    def test_cod_on_chain_error(self) -> None:
        with pytest.raises((ParseError, SemanticError)):
            prog = parse("Chain(FR5, FI30s, COD=2s)")
            analyze(prog)

    def test_bo_on_conc_error(self) -> None:
        with pytest.raises((ParseError, SemanticError)):
            prog = parse("Conc(VI30s, VI60s, BO=5s)")
            analyze(prog)

    def test_missing_cod_warning(self) -> None:
        """Conc without COD → MISSING_COD warning."""
        prog = parse("Conc(VI30s, VI60s)")
        result = analyze(prog)
        assert any("MISSING_COD" in w for w in result.warnings)

    def test_explicit_cod_no_warning(self) -> None:
        """Conc with COD → no MISSING_COD warning."""
        prog = parse("Conc(VI30s, VI60s, COD=2s)")
        result = analyze(prog)
        assert not any("MISSING_COD" in w for w in result.warnings)


class TestKeywordArgOrdering:
    """Grammar §10: keyword args must follow all positional args."""

    def test_kw_between_components_error(self) -> None:
        with pytest.raises(ParseError):
            parse("Conc(VI30s, COD=2s, VI60s)")


class TestPrinterRoundtrip:
    """format_program includes keyword args."""

    def test_conc_cod_format(self) -> None:
        prog = parse("Conc(VI30s, VI60s, COD=2s)")
        text = format_program(prog)
        assert "COD=" in text or "COD =" in text

    def test_mult_bo_format(self) -> None:
        prog = parse("Mult(FR5, EXT, BO=5s)")
        text = format_program(prog)
        assert "BO=" in text or "BO =" in text
