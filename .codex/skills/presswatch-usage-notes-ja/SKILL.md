---
name: presswatch-usage-notes-ja
description: PressWatch で、ユーザーまたは task.md が明示したライブラリ、フレームワーク、メソッド、コマンドの使い方を notes/usage/ に記録するときに使う。使用例、主な引数、返り値、PressWatchでの使いどころを短く整理する。
---

# PressWatch Usage Notes JA

## 目的

PressWatch で使った API、メソッド、decorator、コマンドなどを、後から短時間で思い出せる `notes/usage/` メモとして残す。

`usage/` は公式リファレンスの写経ではなく、PressWatch のコードを読むための実用メモとして扱う。

## 書き込み条件

usageメモを作成、更新するのは、ユーザーの依頼または現在の`task.md`に明示されている場合に限る。

初見のAPIを使ったこと、質問へ回答したこと、今後も参照しそうなことだけを理由に自動更新しない。
記録条件を満たさない場合は、会話内で説明し、必要なら保存先を提案する。

## 保存先

- `notes/usage/<target>.md`

例:

- `notes/usage/sqlalchemy-api.md`
- `notes/usage/pydantic-api.md`
- `notes/usage/alembic-api.md`
- `notes/usage/fastapi-api.md`

既存の usage メモがある場合は、新規ファイルを増やさず既存ファイルへ追記する。

`notes/usage/`を含むnotes全体の索引、読む順番、重複、関連リンクを横断的に整理する場合は、`presswatch-notes-index-ja`を調整役として使う。

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

- `notes/` が Git 管理外の場合は、その前提を尊重する
- 外部公開すべき仕様や手順を `usage/` だけに閉じ込めていないか確認する
- Markdownの書式と管理状態に合う検証は`presswatch-markdown-style-ja`に従う
