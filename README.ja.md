# contingency-dsl-py

:gb: [English README](README.md)

[contingency-dsl](https://github.com/OperantKit/contingency-dsl) の Python リファレンスパーサ。

外部依存ゼロ。現行文法をフルに実装し、コア推奨アノテーション語彙も同梱する。

## 使い方

```python
from contingency_dsl import parse

program = parse("FR 5 @reinforcer('food')")
```

## アノテーション拡張

6 種のコア annotator (`stimulus`, `temporal`, `subjects`, `apparatus`,
`composed`, `measurement`) は `contingency_dsl.annotations` 配下に同梱
されている。DSL 仕様で導入される `@` プレフィックス キーワードの
検証を担う:

```python
from contingency_dsl.annotations import StimulusExtension, MeasurementExtension
from contingency_dsl.extensions import ExtensionRegistry

registry = ExtensionRegistry.build(StimulusExtension(), MeasurementExtension())
```

サードパーティ拡張は `ExtensionModule` Protocol
(`contingency_dsl.extensions`) を実装し、ビルトインと並列に
登録できる。

## ライセンス

MIT。[LICENSE](LICENSE) を参照。
