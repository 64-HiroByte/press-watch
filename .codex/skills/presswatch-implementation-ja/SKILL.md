---
name: presswatch-implementation-ja
description: PressWatchで確定した計画に基づく実装・文書変更を、承認済みの範囲で検証・セルフレビュー・報告まで進めるときに使う。
---

# PressWatch Implementation JA

## 開始条件

[AGENTS.md](../../../AGENTS.md)、存在する場合は`task.md`、確定した計画を照合し、今回の対象・除外事項・承認範囲を確認する。
`git status --short --branch`で現在の状態を確認し、既存差分を保つ。
新タスク開始・引き継ぎは[presswatch-task-handoff-ja](../presswatch-task-handoff-ja/SKILL.md)、ブランチを扱う場合は[phase-branch-workflow-ja](../phase-branch-workflow-ja/SKILL.md)に従う。
既に確認した資料や承認は、今回の状況に変更がなければ利用し、同じ確認を繰り返さない。

設計が未確定、または複数案の比較が必要なら、編集前にPlanモードを提案し、該当する実装は比較・合意後に進める。
調査・計画だけの依頼では編集しない。
計画への合意やスキルの呼び出しを、編集・ブランチ作成・公開・DB接続などの一括承認と扱わない。
現在のタスクで明示承認された同じ操作には再承認を求めず、段階別の承認は`AGENTS.md`、`task.md`、現在のユーザー指示に従う。
前タスクの承認は自動で引き継がない。

## 変更に応じた手順

承認済みの計画に沿って実装し、共有仕様や手順に影響があれば、その範囲内で必要なDocs更新を行う。
変更する対象に応じて、次のスキルの該当する手順だけを使う。

| 対象 | 参照するスキル |
| --- | --- |
| 製品の観測可能な振る舞いの追加・変更 | [presswatch-tdd-ja](../presswatch-tdd-ja/SKILL.md) |
| Python Docstring | [python-docstring-ja](../python-docstring-ja/SKILL.md) |
| 行・ブロック・テストコメント | [comment-style-ja](../comment-style-ja/SKILL.md) |
| Markdown | [presswatch-markdown-style-ja](../presswatch-markdown-style-ja/SKILL.md) |
| スキルの作成・更新 | [presswatch-skill-maintenance-ja](../presswatch-skill-maintenance-ja/SKILL.md) |
| `docs/tasks.md`の進捗・完了更新 | [task-update-ja](../task-update-ja/SKILL.md) |
| コミット候補の分割・メッセージ | [commit-message-ja](../commit-message-ja/SKILL.md) |

notesへの記録は[presswatch-notes-ja](../presswatch-notes-ja/SKILL.md)の書き込み条件に従い、実装完了だけを理由に行わない。
範囲外の変更や追加承認が必要な操作は、理由と選択肢を示して該当部分を保留し、承認済みの独立した作業は続ける。

## 検証・セルフレビュー・報告

変更対象に対応するスキルと今回の完了条件に従って、必要な検証を行う。
文書だけの変更では構造・参照・差分を確認し、RED/GREENや製品全テストを形式的に実行しない。
[presswatch-review-ja](../presswatch-review-ja/SKILL.md)で通常のセルフレビューを行い、今回の実装依頼に含まれる範囲の問題は修正・関連検証・再レビューまで進める。

変更内容、検証結果、未確認事項と理由を報告する。
未解決事項や承認待ちを完了扱いせず、Git操作は`AGENTS.md`の承認条件に従う。

## 呼び出し例

Git操作・公開・DB接続の追加承認は含まない。

```text
$presswatch-implementation-ja 確定した計画を、今回承認済みの範囲で実装してください。承認条件はAGENTS.mdとtask.mdに従ってください。
```
