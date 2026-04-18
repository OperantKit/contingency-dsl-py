# contingency-dsl-py

:jp: [日本語版 README](README.ja.md)

Python reference parser for [contingency-dsl](https://github.com/OperantKit/contingency-dsl).

Zero external dependencies. Implements the full grammar.

## Usage

```python
from contingency_dsl import parse

program = parse("Conc(VI30s, VI60s)")
```

## License

MIT. See [LICENSE](LICENSE).
