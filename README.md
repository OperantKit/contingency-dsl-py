# contingency-dsl-py

:jp: [日本語版 README](README.ja.md)

Python reference parser for [contingency-dsl](https://github.com/OperantKit/contingency-dsl).

Zero external dependencies. Implements the full grammar and ships the
core recommended annotation vocabulary.

## Install

```bash
pip install contingency-dsl-py
```

## Usage

```python
from contingency_dsl import parse

program = parse("FR 5 @reinforcer('food')")
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
