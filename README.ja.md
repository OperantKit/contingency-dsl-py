# contingency-dsl-py

:gb: [English README](README.md)

contingency-dsl-py は、[contingency-dsl](https://github.com/OperantKit/contingency-dsl) の記法（`Conc(VI 30-s, VI 60-s, COD=2-s)` など）で書かれた強化スケジュールと条件づけの手続きを読み、Python のオブジェクトや普通の辞書に変換します。contingency-dsl の Python のリファレンスパーサです。[OperantKit](https://github.com/OperantKit) の中では、[contingency-py](https://github.com/OperantKit/contingency-py) がこれで構文解析したスケジュールを実行し、[contingency-dsl2procedure](https://github.com/OperantKit/contingency-dsl2procedure) が構文解析の結果を方法セクション（Method 節）の文章にします。

**要点**

- 単純な `FR 5` から、切替遅延（changeover delay, COD）・制限時間（limited hold）つきの入れ子の複合スケジュール、二次スケジュール、複数フェーズのデザイン、レスポンデントの手続きまで読めます。
- スケジュールの書き誤りを行と列つきで報告するので、セッションの後ではなくファイルを読んだ時点で見つかります。
- Python の標準ライブラリ以外は何も要りません。

## インストール

Python 3.11 以上が必要です。パッケージはまだ PyPI に登録されていないので、GitHub から入れます。

```bash
pip install git+https://github.com/OperantKit/contingency-dsl-py
```

## 例

スケジュールを構文解析し、普通の辞書として中身を見て、テキストに書き戻します。

```python
from contingency_dsl import ParseError, format_program, from_dict, parse, to_dict

program = parse("Conc(VI30s, VI60s, COD=2s)")
ast = to_dict(program)  # 普通の dict。contingency-dsl の AST スキーマに従う
print(ast["schedule"]["combinator"])  # Conc
print([c["value"] for c in ast["schedule"]["components"]])  # [30.0, 60.0]
print(format_program(from_dict(ast)))  # Conc(VI30s, VI60s, COD=2s)

try:
    parse("Conc(VI30s,")
except ParseError as error:
    print(error)  # line 1, col 12: unexpected end of input
```

この辞書（構文解析の結果。AST とも呼びます）が、OperantKit のパッケージどうしがやり取りする形式です。`to_dict` と `from_dict` はこの辞書と Python のオブジェクトを相互に変換し、`format_program` は正規の形のテキストを書き出します。

## アノテーション

`@reinforcer("food")` や `@species("rat")` のようなアノテーションは、スケジュールに Method 節の情報（被験体、装置、刺激、測定）を加えます。アノテーションは拡張モジュールが検査するので、使うものを含むレジストリを渡します。

```python
from contingency_dsl import parse
from contingency_dsl.annotations import StimulusExtension
from contingency_dsl.extensions import ExtensionRegistry

registry = ExtensionRegistry.build(StimulusExtension())
program = parse('FR 5 @reinforcer("food")', extensions=registry)
```

`contingency_dsl.annotations` には 6 つの拡張が入っています: `StimulusExtension`、`TemporalExtension`、`SubjectsExtension`、`ApparatusExtension`、`ComposedExtension`、`MeasurementExtension`。`contingency_dsl.extensions` の `ExtensionModule` プロトコルを実装すれば自作の拡張を書け、これらと一緒に渡せます。

## 制限

- このパッケージはスケジュールを読むだけで、実行はしません。強化子をいつ提示するかを決めるには [contingency-py](https://github.com/OperantKit/contingency-py) を使います。
- アノテーションつきのテキストをレジストリなしで渡すと、拡張が無いという内容ではなく、`@` の位置の構文エラー（例: `unexpected token after schedule: AT '@'`）になります。
- 仕様のすべての構文を読めるわけではありません。レスポンデント用のアノテーション `@cs` と `@us` は同梱の 6 つの拡張では扱えず、[contingency-respondent-dsl](https://github.com/OperantKit/contingency-respondent-dsl) の Pavlov 型の手続き（`Renewal(...)` など）は構文解析できません。

## 開発に参加する人へ

```bash
git clone https://github.com/OperantKit/contingency-dsl
git clone https://github.com/OperantKit/contingency-dsl-py
cd contingency-dsl-py
pip install -e '.[test]'
pytest
```

適合テストとスキーマのテストは、隣に置いた [contingency-dsl](https://github.com/OperantKit/contingency-dsl) の clone を読みます。clone が無いとそれらのテストは飛ばされます。この README と `README.md` の `python` ブロックは、すべて `tests/test_readme_examples.py` で実行されます。AI のコーディングエージェント向けの説明は [AGENTS.md](AGENTS.md) にあります。

## 引用とライセンス

このパッケージを引用するときは [CITATION.cff](CITATION.cff) を使ってください。MIT License です。[LICENSE](LICENSE) を参照してください。
