---
name: presswatch-usage-notes-ja
description: PressWatch で FastAPI、Pydantic、Alembic、SQLAlchemy など初見または忘れやすいライブラリ、フレームワーク、メソッド、コマンドを使ったとき、notes/usage/ 配下に使用例・主な引数・返り値・PressWatch での使いどころを記録するためのスキル。
---

# PressWatch Usage Notes JA

## 目的

PressWatch で使った API、メソッド、decorator、コマンドなどを、後から短時間で思い出せる `notes/usage/` メモとして残す。

`usage/` は公式リファレンスの写経ではなく、PressWatch のコードを読むための実用メモとして扱う。

## 使うタイミング

- FastAPI、Pydantic、Alembic、SQLAlchemy など、初見または忘れやすい API を使ったとき
- ユーザーが「このメソッドは何をするのか」「引数や返り値も知りたい」と質問したとき
- 同じライブラリの API を今後も参照しそうなとき
- `notes/topics/` よりも、具体的な使い方の早見表として残したいとき

## 保存先

- `notes/usage/<target>.md`

例:

- `notes/usage/sqlalchemy-api.md`
- `notes/usage/pydantic-api.md`
- `notes/usage/alembic-api.md`
- `notes/usage/fastapi-api.md`

既存の usage メモがある場合は、新規ファイルを増やさず既存ファイルへ追記する。

## `topics/` との切り分け

- `notes/topics/`: 概念整理、設計判断、責務分担、迷った背景
- `notes/usage/`: API、メソッド、decorator、コマンドの使い方、引数、返り値、短い使用例

設計判断の背景まで整理したい場合は `topics/`、コードを読むための使い方を引けるようにしたい場合は `usage/` に置く。

## 書く内容

各 API は、必要に応じて次の形で短く整理する。

~~~markdown
### `api_or_method_name`

一言:

```text
何をするものか。
```

PressWatch の例:

```python
実際のコードに近い短い例
```

主な引数:

- `name`: 必須/任意。型の目安。意味。

返り値:

- 型の目安。
- PressWatch の文脈で何が返るか。

PressWatch での意味:

このプロジェクトでは何のために使うか。
~~~

## 書き方

- 日本語で書く
- くどくしすぎず、後から引ける軽いリファレンスにする
- 公式ドキュメントの網羅ではなく、PressWatch で使った範囲を優先する
- 引数は、必須/任意、型の目安、意味を短く書く
- 返り値は、型の目安と今回の文脈で返るものを書く
- 使用例は、実際のコードに近い短い例にする
- 混乱しやすい API は少し丁寧に、土台系や自明なものは短くする
- 秘密情報や `.env` の中身は書かない

## 追記時の確認

- 既存の usage メモと重複していないか
- 古い説明が現在のコードと矛盾していないか
- ファイル名が `usage/` 配下で冗長になっていないか
  - 例: `sqlalchemy-api.md` はよい
  - 例: `sqlalchemy-api-usage.md` は `usage/` 配下では冗長
- `notes/README.md` の分類と矛盾していないか

## 完了前チェック

- `git diff --check` を実行する
- `notes/` が Git 管理外の場合は、その前提を尊重する
- 外部公開すべき仕様や手順を `usage/` だけに閉じ込めていないか確認する
