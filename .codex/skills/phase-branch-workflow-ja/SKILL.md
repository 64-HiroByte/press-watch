---
name: phase-branch-workflow-ja
description: PressWatch で Phase 単位の開発運用を行うときに使う。Phase ブランチからタスク作業ブランチを切る、タスクPRの base を Phase ブランチにする、タスクPRを Phase ブランチへ順次マージする、Phase 完了時だけ Phase ブランチから main へ PR を作る、という運用を守るためのスキル。
---

# Phase Branch Workflow JA

## 基本方針

- `main` は安定版として扱い、タスク単位の作業ブランチを直接 `main` に向けない。
- Phase 全体の統合先として `phase-N/...` ブランチを使う。
- 個別タスクは Phase ブランチから作業ブランチを切る。
- 個別タスクPRの base は `main` ではなく、元の Phase ブランチにする。
- タスクPRを Phase ブランチへマージしながら、Phase 内の作業を積み上げる。
- Phase が完了した時点で、Phase ブランチから `main` へ PR を作る。

## 作業開始時

1. `git status --short --branch` で現在ブランチと未コミット差分を確認する。
2. ユーザーが Phase ブランチ名を指定している場合は、そのブランチを親ブランチとして扱う。
3. Phase ブランチ上で作業を始める場合は、先にタスク用ブランチを切る。
4. 既に差分を作ってしまっている場合は、差分を保ったまま Phase ブランチからタスク用ブランチを切り直す。差分を破棄しない。

## ブランチ命名

- Phase ブランチは `phase-3/db-persistence` のように `phase-N/...` を使う。
- タスク作業ブランチは内容に応じて `docs/...`、`feat/...`、`fix/...`、`refactor/...`、`test/...` を使う。
- タスク作業ブランチ名は、Phase 名ではなく具体的なタスク名を表す。
- 例: `docs/phase-3-db-policy`
- 例: `feat/phase-3-db-connection`
- 例: `feat/phase-3-press-release-model`

## PR 作成時

- タスクPRの base は必ず親の Phase ブランチにする。
- 例: `docs/phase-3-db-policy` -> `phase-3/db-persistence`
- Phase 完了PRだけ、base を `main` にする。
- PR本文では「このタスクで扱うこと」と「扱わないこと」を短く書く。
- docs/tasks.md を更新した場合は、完了扱いが確認済みのタスクだけにチェックを入れる。

## タスクPRマージ後

1. Phase ブランチへ戻る。
2. Phase ブランチを最新化する。
3. 次のタスク作業ブランチを Phase ブランチから切る。
4. 前タスクの作業ブランチを親にして次タスクブランチを切らない。

## 確認観点

- 現在ブランチが Phase ブランチのまま作業差分を持っていないか。
- タスク作業ブランチの分岐元が対象 Phase ブランチか。
- タスクPRの base が `main` ではなく対象 Phase ブランチか。
- Phase 完了PRだけが `main` を base にしているか。
- 未コミット差分やユーザーの変更を破棄していないか。
