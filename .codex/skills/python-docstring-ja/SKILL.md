---
name: python-docstring-ja
description: PressWatch の Python コードに Docstring を追加・修正するときに使う。日本語の Google スタイル Docstring、型ヒントとの役割分担、文末表現、句点の扱いをこのプロジェクトの好みに揃える。
---

# PressWatch Docstring JA

## 概要

PressWatch の Python コードで Docstring を書くときのプロジェクト固有ルール。型情報は型ヒントに任せ、Docstring には意図、責務、異常系の扱いを簡潔に残す。

## 方針

- Docstring は日本語で記述する
- Google スタイル Docstring を使う
- 型は関数シグネチャや dataclass フィールドに書き、`Args` / `Returns` / `Attributes` には型を書かない
- Summary は「です。」「します。」を避け、簡潔な名詞止め・体言止め寄りにする
- `Args` / `Returns` / `Attributes` の各項目説明末尾に句点を付けない
- dataclass と公開関数には原則 Docstring を書く
- 内部関数は、意図、異常系、外部HTML依存、ライブラリ都合が読み取りにくい場合に Docstring を書く
- テストクラス、テストメソッド、テスト用 helper にも短い Docstring を書く
- 自明な処理に長い説明を足して、コードより Docstring が重くならないようにする

## 関数例

```python
def _parse_heading_date(value: str) -> date | None:
    """報道発表日の見出し文字列から日付を抽出

    Args:
        value: 報道発表日の見出し文字列

    Returns:
        抽出した日付、形式不一致または実在しない日付の場合はNone
    """
```

## dataclass 例

```python
@dataclass(frozen=True)
class PressRelease:
    """環境省の報道発表一覧ページから取得した報道発表

    Attributes:
        title: 報道発表のタイトル
        published_at: 報道発表日
        url: 報道発表詳細ページの絶対URL
    """
```

## テスト例

テストの Docstring は、何を保証するテストなのかを短く書く。テストメソッドには `Args` / `Returns` を付けない。

```python
class EnvPressParserTest(unittest.TestCase):
    """環境省報道発表HTMLのパース処理のテスト"""

    def test_parse_press_releases_normalizes_title_text(self) -> None:
        """タイトルの空白とタグ境界を正規化すること"""
```

テスト用 helper は、テストデータ生成の意図が分かる程度に書く。

```python
def _press_release_block(
    heading: str,
    href: str = '/press/press_00001.html',
) -> str:
    """報道発表1件分のHTML断片を生成"""
```

## 確認観点

- 型が Docstring 側に重複していないか
- 文末に不要な句点が付いていないか
- Summary が説明口調になりすぎていないか
- テストの Docstring が保証したい振る舞いを表しているか
- スクレイピングの異常系や外部HTML依存が読み取れるか
