# contingency-dsl-py

:gb: [English README](README.md)

[contingency-dsl](https://github.com/OperantKit/contingency-dsl) の Python リファレンスパーサ。

外部依存ゼロ。現行文法をフルに実装し、コア推奨アノテーション語彙も同梱する。

## インストール

```bash
pip install contingency-dsl-py
```

## 30 秒で動く例

スケジュールを構文解析し、JSON にできる AST として中身を見て、正規形で書き戻す:

```python
from contingency_dsl import ParseError, format_program, from_dict, parse, to_dict

program = parse("Conc(VI30s, VI60s, COD=2s)")
ast = to_dict(program)  # 素の dict。contingency-dsl の AST スキーマに適合する
print(ast["schedule"]["combinator"])  # Conc
print([c["value"] for c in ast["schedule"]["components"]])  # [30.0, 60.0]
print(format_program(from_dict(ast)))  # Conc(VI30s, VI60s, COD=2s)

try:
    parse("Conc(VI30s,")
except ParseError as error:
    print(error)  # line 1, col 12: unexpected end of input
```

解析したスケジュールに反応を与えて動かすには、[contingency-py](https://github.com/OperantKit/contingency-py) の `contingency.from_dsl` に渡す（`pip install contingency-py`）。

## 自作の 50 行では足りない理由

`FR 5` や `VI 30-s` を拾う正規表現は、実験が 2 つ以上のスケジュールを必要とした時点で破綻する:

- **文法の全体.** 複合スケジュール（`Conc`, `Mult`, `Chain`, `Tand`, `Alt`, `Conj` ほか）は任意に入れ子にでき、切替遅延（`COD`、方向別の `COD(1->2)`）、固定比率の切替要件（`FRCO`）、Limited Hold、二次スケジュール、パラメータ宣言、束縛、レスポンデント手続きを含む。
- **適合性スイート.** テストは [contingency-dsl](https://github.com/OperantKit/contingency-dsl) の 1,000 件を超える適合性ケースを再生し、直列化した AST をその JSON Schema で検証する。他のパーサ（[contingency-rs](https://github.com/OperantKit/contingency-rs) の Rust 版を含む）も同じケースで検査できる。
- **往復変換.** `parse` → `to_dict` → `from_dict` → `format_program` で正規形のソースに戻る。往復はテストで確かめている。
- **Method 節.** AST の dict はそのまま [contingency-dsl2procedure](https://github.com/OperantKit/contingency-dsl2procedure) の入力になり、スケジュールを Method 節の段落として書き出す。[contingency-procedure2dsl](https://github.com/OperantKit/contingency-procedure2dsl) は論文の Method 本文からスケジュールを抽出する。
- **アノテーションを検証する.** `@reinforcer`・`@algorithm`・`@session_end` などのキーワードは拡張モジュールが検査し、黙って無視されることはない。
- **エラーに位置が付く.** 字句エラーと構文エラーは行と列を報告する。

解析したスケジュールは、自作の計時コードの代わりに [contingency-py](https://github.com/OperantKit/contingency-py) で動かせる。スケジュールを組む 20 件の依頼で Claude Code（claude-opus-5-5）と Codex CLI（gpt-6.1-sol）にそのコードを 1 回ずつ書かせたところ、VI の間隔を Fleshler-Hoffman の数列で作ったのは 14 本中 7 本、並立スケジュール 6 本中 2 本に切替遅延の誤り、手書きの間隔スケジュール 18 本中 2 本が利用可能な強化子を捨てるか、間隔の経過前の反応を強化しうるものだった（詳細は contingency-py の README）。

## 使い方

```python
from contingency_dsl import parse

program = parse("FR 5")
```

`@reinforcer` などのアノテーションは拡張が検証するので、それを含む
レジストリを渡す:

```python
from contingency_dsl import parse
from contingency_dsl.annotations import StimulusExtension
from contingency_dsl.extensions import ExtensionRegistry

registry = ExtensionRegistry.build(StimulusExtension())
program = parse('FR 5 @reinforcer("food")', extensions=registry)
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
