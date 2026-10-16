# contingency-dsl-py

:jp: [日本語版 README](README.ja.md)

Python reference parser for [contingency-dsl](https://github.com/OperantKit/contingency-dsl).

Zero external dependencies. Implements the full grammar and ships the
core recommended annotation vocabulary.

## Install

```bash
pip install contingency-dsl-py
```

## 30-second example

Parse a schedule, inspect it as a JSON-ready AST, and print it back in canonical form:

```python
from contingency_dsl import ParseError, format_program, from_dict, parse, to_dict

program = parse("Conc(VI30s, VI60s, COD=2s)")
ast = to_dict(program)  # plain dict, conforms to the contingency-dsl AST schema
print(ast["schedule"]["combinator"])  # Conc
print([c["value"] for c in ast["schedule"]["components"]])  # [30.0, 60.0]
print(format_program(from_dict(ast)))  # Conc(VI30s, VI60s, COD=2s)

try:
    parse("Conc(VI30s,")
except ParseError as error:
    print(error)  # line 1, col 12: unexpected end of input
```

To run the parsed schedule against responses, pass it to `contingency.from_dsl` from [contingency-py](https://github.com/OperantKit/contingency-py) (`pip install contingency-py`).

## Why not a 50-line hand-written parser?

A regular expression for `FR 5` or `VI 30-s` stops working as soon as an experiment needs more than one schedule:

- **Full grammar.** Compound schedules (`Conc`, `Mult`, `Chain`, `Tand`, `Alt`, `Conj`, and others) nest arbitrarily, with changeover delay (`COD`, direction-specific `COD(1->2)`), fixed-ratio changeover (`FRCO`), limited hold, second-order schedules, parameter declarations, bindings, and respondent procedures.
- **Conformance suite.** The tests replay more than 1,000 conformance cases from [contingency-dsl](https://github.com/OperantKit/contingency-dsl), and serialized ASTs are validated against its JSON Schema, so other parsers (including the Rust one in [contingency-rs](https://github.com/OperantKit/contingency-rs)) can be checked against the same cases.
- **Round trip.** `parse` → `to_dict` → `from_dict` → `format_program` returns the canonical source text; the round trip is covered by tests.
- **Method sections.** The AST dict is the input of [contingency-dsl2procedure](https://github.com/OperantKit/contingency-dsl2procedure), which writes the schedule as a Method-section paragraph, and [contingency-procedure2dsl](https://github.com/OperantKit/contingency-procedure2dsl) extracts schedules from published Method text.
- **Annotations are validated.** `@reinforcer`, `@algorithm`, `@session_end`, and other keywords are checked by extension modules instead of being silently ignored.
- **Errors carry positions.** Lexical and syntax errors report line and column.

## Usage

```python
from contingency_dsl import parse

program = parse("FR 5")
```

Annotations such as `@reinforcer` are validated by extensions, so pass a
registry that includes them:

```python
from contingency_dsl import parse
from contingency_dsl.annotations import StimulusExtension
from contingency_dsl.extensions import ExtensionRegistry

registry = ExtensionRegistry.build(StimulusExtension())
program = parse('FR 5 @reinforcer("food")', extensions=registry)
```

## Annotation extensions

Six core annotators (`stimulus`, `temporal`, `subjects`, `apparatus`,
`composed`, `measurement`) are shipped under `contingency_dsl.annotations`.
They validate `@`-prefixed keywords introduced by the DSL spec:

```python
from contingency_dsl.annotations import StimulusExtension, MeasurementExtension
from contingency_dsl.extensions import ExtensionRegistry

registry = ExtensionRegistry.build(StimulusExtension(), MeasurementExtension())
```

Third-party extensions can implement the `ExtensionModule` Protocol
(`contingency_dsl.extensions`) and compose alongside the built-ins.

## License

MIT. See [LICENSE](LICENSE).
