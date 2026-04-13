# contingency-dsl-py

Python reference parser for [contingency-dsl](../contingency-dsl/).

Zero external dependencies. Implements the full v1.0 grammar.

## Usage

```python
from contingency_dsl import parse

program = parse("Conc(VI30s, VI60s)")
```
