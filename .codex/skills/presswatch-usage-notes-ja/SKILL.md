---
name: presswatch-usage-notes-ja
description: ユーザーまたはtask.mdが明示したPressWatchのAPI・ライブラリ・コマンドの使い方をnotes/usageへ記録するときに使う。
---

# PressWatch Usage Notes JA

## 書き込み条件と保存先

ユーザーの依頼または現在の`task.md`に記録が明示された場合だけ、`notes/usage/<target>.md`を作成・更新する。
初見のAPIや質問への回答だけを理由に自動更新しない。

既存メモへの追記を優先し、ファイル名は`sqlalchemy-api.md`のように用途が分かる名前とする。
`usage/`配下で`-usage`を重ねるなど、冗長な命名は避ける。
設計判断や概念の背景は`notes/topics/`へ分け、全体整理が依頼された場合だけ`presswatch-notes-index-ja`を使う。

## 記録する内容

公式リファレンスを網羅せず、PressWatchで使う範囲に絞って日本語で整理する。
API・メソッド・decorator・コマンドごとに、必要な情報だけを書く。

- 何をするものかと、PressWatchでの使いどころ。
- 実際のコードに近い短い使用例。
- 主な引数の必須・任意、型の目安、意味。
- 返り値の型の目安と、今回の文脈で返るもの。

## 確認

追記箇所の重複、現在のコードとの矛盾、`notes/README.md`の分類との整合を確認する。
共有すべき仕様・手順は`docs/`を正本とし、notesのGit管理状態は変えない。
Markdownの書式と検証は`presswatch-markdown-style-ja`に従う。
