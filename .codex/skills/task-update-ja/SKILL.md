---
name: task-update-ja
description: PressWatchのdocs/tasks.mdでタスクやPhaseの進捗・完了状態を更新するときに使う。
---

# Task Update JA

## 完了の判定

チェックは実装済みではなく、完了条件の確認済みを表す。

- 主要な動作と、要件上重要な異常系・空データを確認する。
- 対象に合うテスト・lint・typecheckとレビューを済ませる。
- レビュー指摘がある場合は、対応または未対応理由を整理する。
- 未確認事項、範囲内の未対応、制約で満たせない完了条件が残る場合はチェックせず、メモや後続作業を示す。

## Phase完了前の文書点検

起動手順、API、画面、運用、CI、技術前提などが変わり、共有文書に影響するPhaseだけ、末尾に点検・更新タスクを置く。
関係する`README.md`、`docs/local-development.md`、`docs/requirements.md`、`docs/tech-stack.md`などを実装と照合する。

```markdown
- [ ] Phase Nの完了前に、READMEと関連docsの手順・要件・未対応範囲を現状に合わせて点検・更新する
```
