---
name: phase-branch-workflow-ja
description: PressWatch で Phase 単位の開発運用を行うときに使う。Phase ブランチからタスク作業ブランチを切る、タスクPRの base を Phase ブランチにする、タスクPRを Phase ブランチへ順次マージする、Phase 完了時だけ Phase ブランチから main へ PR を作る、という運用を守るためのスキル。
---

# Phase Branch Workflow JA

## 目的

PressWatch のタスクを対象Phaseへ積み上げ、Phase完了前の変更を直接 `main` へ向けない。

Git操作の承認境界は `AGENTS.md` を正本とし、このスキルではブランチ間の関係とPRのbaseを扱う。

## ブランチの関係

- Phase全体の統合先として `phase-N/...` ブランチを使う。
- 個別タスクは、対象Phaseブランチからタスク作業ブランチを作成する。
- タスクPRのbaseは、`main`ではなく対象Phaseブランチにする。
- Phaseが完了した時点で、Phaseブランチから `main` へPRを作成する。
- 前タスクの作業ブランチを親にして、次のタスクブランチを作成しない。

## 作業開始時

1. `git status --short --branch` で現在ブランチと未コミット差分を確認する。
2. ユーザーが指定したPhaseブランチと、現在のローカル参照を確認する。
3. ブランチの切り替えや最新化が必要な場合は、操作と影響を報告して了承を得る。
4. 対象Phaseブランチから作成するタスクブランチ名を提案し、了承後に作成する。

既に差分がある場合は破棄せず、差分の所有者と作成先を確認してから移動方法を提案する。

## ブランチ命名

- Phaseブランチは `phase-3/db-persistence` のように `phase-N/...` を使う。
- タスクブランチには、内容に応じて `docs/...`、`feat/...`、`fix/...`、`refactor/...`、`test/...`、`chore/...` を使う。
- `chore/...` は、開発補助、設定、スキル保守など、製品の振る舞いを直接変えない作業に使う。
- ブランチ名はPhase名だけでなく、具体的なタスクを表す。

例:

- `docs/phase-3-db-policy`
- `feat/phase-3-db-connection`
- `chore/agent-workflow-audit`

## PRのbase

- タスクPRのbaseは、必ず元のPhaseブランチにする。
- Phase完了PRだけ、baseを `main` にする。
- PR本文では、今回扱うこと、扱わないこと、実行した確認を短く示す。
- `docs/tasks.md` を更新する場合は、`task-update-ja` に従う。

## タスクPRマージ後

マージ後のブランチ切り替え、最新化、ブランチ削除は自動実行しない。
現在の状態と必要な操作を報告し、`AGENTS.md` の承認境界に従う。

次のタスクブランチは、最新化を確認したPhaseブランチから作成する。

## 確認観点

- タスクブランチの分岐元が対象Phaseブランチか。
- タスクPRのbaseが対象Phaseブランチか。
- Phase完了PRだけが `main` をbaseにしているか。
- Phaseブランチ上へタスク差分を直接作っていないか。
- 未コミット差分やユーザーの変更を破棄していないか。
