---
name: python-docstring-ja
description: PressWatchのPython Docstringを追加・修正するときに使う。
---

# PressWatch Docstring JA

## 書く対象

公開関数・クラス・dataclassなど、利用側が責務や非自明な契約を理解する必要がある対象を優先する。
内部関数・テスト・helperは、名前・型ヒント・周辺コードだけでは意図や前提が分かりにくい場合に書く。
コードの読み上げになる説明は省略してよい。

## 形式

- 日本語のGoogleスタイルとする。
- 型はシグネチャやフィールドに任せ、`Args`・`Returns`・`Attributes`に重複させない。
- Summaryは「です。」「します。」を避け、名詞止め・体言止め寄りの簡潔な表現にする。
- 各項目の説明末尾に句点を付けない。
- `Args`は引数の役割を示し、コードから読める分岐などの実装詳細を繰り返さない。
- `Returns`には戻り値の意味と、利用側に必要な異常系の扱いを示す。
- dataclassの各フィールドの役割は、必要に応じて`Attributes`へ書く。

```python
def _parse_heading_date(value: str) -> date | None:
    """報道発表日の見出し文字列から日付を抽出

    Args:
        value: 報道発表日の見出し文字列

    Returns:
        抽出した日付、形式不一致または実在しない日付の場合はNone
    """
```

## テストとhelper

テスト名だけで保証範囲が分かる場合はDocstringを省略し、必要なら実際に保証する振る舞いを短く書く。
テストメソッドには`Args`・`Returns`を付けない。
helperでは、呼び出し側から引数や戻り値の意味が分かりにくい場合にこれらを付ける。
可変長引数や展開を使うhelperは、何を渡すか迷う場合に短い呼び出し例を添えてよい。
