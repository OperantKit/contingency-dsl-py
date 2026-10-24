# contingency-dsl-py

:jp: [日本語版 README](README.ja.md)

contingency-dsl-py reads schedules of reinforcement and conditioning procedures written in the [contingency-dsl](https://github.com/OperantKit/contingency-dsl) notation, such as `Conc(VI 30-s, VI 60-s, COD=2-s)`, and turns them into Python objects or plain dictionaries. It is the Python reference parser for contingency-dsl. Within [OperantKit](https://github.com/OperantKit), [contingency-py](https://github.com/OperantKit/contingency-py) runs the schedules it parses, and [contingency-dsl2procedure](https://github.com/OperantKit/contingency-dsl2procedure) writes the parsed form as Method-section text.

**In short**

- Reads schedules from a simple `FR 5` to nested compound schedules with a changeover delay (COD), limited hold, second-order schedules, multi-phase designs, and respondent procedures.
- Reports a mistake in a schedule with its line and column, so it is found when the file is read, not after the session.
- Needs nothing outside the Python standard library.

## Installation

Python 3.11 or newer. The package is not on PyPI yet; install it from GitHub:

```bash
pip install git+https://github.com/OperantKit/contingency-dsl-py
```

## Example

Parse a schedule, look at it as a plain dictionary, and print it back as text:

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

The dictionary (the parsed form, or AST) is the format the other OperantKit packages exchange. `to_dict` and `from_dict` convert between it and the Python objects; `format_program` writes the canonical text.

## Annotations

Annotations such as `@reinforcer("food")` or `@species("rat")` add Method-section details (subjects, apparatus, stimuli, measurement) to a schedule. They are checked by extension modules, so pass a registry that includes the ones you use:

```python
from contingency_dsl import parse
from contingency_dsl.annotations import StimulusExtension
from contingency_dsl.extensions import ExtensionRegistry

registry = ExtensionRegistry.build(StimulusExtension())
program = parse('FR 5 @reinforcer("food")', extensions=registry)
```

Six extensions are included in `contingency_dsl.annotations`: `StimulusExtension`, `TemporalExtension`, `SubjectsExtension`, `ApparatusExtension`, `ComposedExtension`, and `MeasurementExtension`. You can write your own by implementing the `ExtensionModule` protocol in `contingency_dsl.extensions` and pass it alongside them.

## Limitations

- This package reads schedules; it does not run them. To decide when a reinforcer is delivered, use [contingency-py](https://github.com/OperantKit/contingency-py).
- Annotated text without a registry fails with a syntax error at the `@` (for example `unexpected token after schedule: AT '@'`), not with a message about the missing extension.
- Not every construct in the specification is read. The respondent annotations `@cs` and `@us` are not covered by the six included extensions, and the Pavlovian procedures of [contingency-respondent-dsl](https://github.com/OperantKit/contingency-respondent-dsl) (such as `Renewal(...)`) are not parsed.

## For contributors

```bash
git clone https://github.com/OperantKit/contingency-dsl
git clone https://github.com/OperantKit/contingency-dsl-py
cd contingency-dsl-py
pip install -e '.[test]'
pytest
```

The conformance and schema tests read the [contingency-dsl](https://github.com/OperantKit/contingency-dsl) clone next to this one; without it they are skipped. Every `python` block in this README and in `README.ja.md` is run by `tests/test_readme_examples.py`. Notes for AI coding agents are in [AGENTS.md](AGENTS.md).

## Citation and license

Cite this package with [CITATION.cff](CITATION.cff). MIT License; see [LICENSE](LICENSE).
