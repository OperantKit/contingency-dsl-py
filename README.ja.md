# contingency-dsl-py

:gb: [English README](README.md)

[contingency-dsl](https://github.com/OperantKit/contingency-dsl) の Python リファレンスパーサ。

外部依存ゼロ。現行文法をフルに実装している。

## 使い方

```python
from contingency_dsl import parse

program = parse("Conc(VI30s, VI60s)")
```

## ライセンス

MIT。[LICENSE](LICENSE) を参照。
