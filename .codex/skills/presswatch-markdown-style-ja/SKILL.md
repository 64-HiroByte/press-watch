---
name: presswatch-markdown-style-ja
description: >
  PressWatch 内の Markdown を作成、更新、レビューするときに使う。
  README、docs、notes、AGENTS.md、task.md、各スキルを対象に、一文一行、既存構造、最小差分、Git管理状態に合う空白検証の方針を揃える。
---

# PressWatch Markdown Style JA

## 対象

PressWatch内のMarkdown全体を対象にする。

例:

- `README.md` と `docs/`
- `notes/`
- `AGENTS.md` と `task.md`
- `.codex/skills/*/SKILL.md` とスキルの参照文書

文書の保存先、内容、書き込み条件は、対象に対応するスキルと `AGENTS.md` に従う。

## 基本方針

- 日本語の本文は、原則として一文を一つの物理行に置く。
- 表示幅だけを理由に、文の途中で改行しない。
- 同じ段落に複数の文を置く場合も、文ごとに改行する。
- 段落を分ける場合だけ空行を入れる。
- 見出しや短いラベルには、一文一行を無理に当てはめない。
- 今回変更する文章だけへ適用し、無関係な既存箇所を一括整形しない。

## 箇条書き

一つの項目に複数の文を書く場合は、二文目以降を同じ項目の継続行に置く。

```markdown
- 一文目を書く。
  二文目は同じ項目の継続行に置く。
```

入れ子の箇条書き、リンク、コードブロックなど、既存のMarkdown構造を崩さない。

## 例外

- コードブロックと表は、一文一行の対象外とする。
- コマンド、JSON、YAMLなどの構造を持つ内容は、適切なコードブロックに置く。
- 外部からの引用や自動生成された内容は、原文や構造の維持を優先する。

## 変更後の検証

Git管理対象のMarkdownは、次で空白エラーを確認する。

```bash
git diff --check
```

Git管理外またはignoredのMarkdownは `git diff --check` の対象にならないため、対象を明示して変更したファイルごとに実行する。

```bash
target_markdown="/absolute/path/to/changed.md"
git diff --no-index --check /dev/null "$target_markdown"
```

no-index検証では、差分があること自体と空白エラーを区別して結果を確認する。

最後に、見出し、箇条書き、リンク、コードブロック、表の意味が変わっていないか、変更行を読み直す。
