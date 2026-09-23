---
name: presswatch-markdown-style-ja
description: PressWatch内のMarkdownを作成・更新・レビューするときに使う。Git管理外のtask.mdやnotesも対象とする。
---

# PressWatch Markdown Style JA

## 書式

- 日本語は原則一文一行とし、表示幅だけを理由に文の途中で改行しない。
- 同じ段落では文ごとに改行し、段落を分けるときだけ空行を入れる。
- 箇条書きの二文目以降は、同じ項目の継続行に置く。
- 見出し・短いラベル・表・コードブロックは一文一行の対象外とする。
- 引用や自動生成内容は原文と構造を維持する。
- 今回の変更箇所へ適用し、無関係な文書の一括整形はしない。

```markdown
- 一文目を書く。
  二文目は同じ項目の継続行に置く。
```

## 空白検証

Git管理対象では、未ステージの変更を確認する。

```bash
git diff --check
```

ステージ済みの変更がある場合は、そちらも確認する。

```bash
git diff --cached --check
```

Git管理外・ignoredの変更は通常のdiffに含まれないため、変更ファイルごとに確認する。

```bash
target_markdown="/absolute/path/to/changed.md"
git diff --no-index --check /dev/null "$target_markdown"
```

no-indexの終了コード1は差分の存在も表すため、出力を確認して空白エラーと区別する。
見出し、箇条書き、リンク、コードフェンス、表の構造も変更箇所で確認する。
