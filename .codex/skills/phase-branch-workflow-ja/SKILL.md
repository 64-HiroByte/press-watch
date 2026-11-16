---
name: phase-branch-workflow-ja
description: PressWatchのタスク編集前のブランチ準備、ブランチ命名、PRのbaseと本文、マージ後の整理に使う。
---

# Phase Branch Workflow JA

Git操作の承認は`AGENTS.md`に従う。
このスキルでは分岐元、命名、PRの統合先と本文を扱う。

## 分岐元とPRのbase

- Phase全体の統合先は`phase-N/...`とする。
- タスクブランチは対象Phaseブランチから作成し、タスクPRも同じPhaseをbaseにする。
- 前タスクの作業ブランチを次タスクの親にせず、Phaseブランチへタスク差分を直接作らない。
- Phase完了時だけ、Phaseブランチから`main`へPRを作成する。

## 開始・再開時

新しいタスクの編集前に`git status --short --branch`と関連する参照を確認し、現在の状態、親ブランチ、作業ブランチ案を示して承認を得る。
承認後に親ブランチから作業ブランチを作成して切り替え、そのブランチで編集を始める。
既存差分がある場合は所有者と移動先を確認し、差分を保つ方法を選ぶ。
コミット直前に、現在のブランチが承認済みの作業ブランチと一致することを確認する。

## 命名

Phaseブランチは`phase-3/db-persistence`のように命名する。
タスクブランチは具体的な作業内容を表し、通常は`docs/`、`feat/`、`fix/`、`refactor/`、`test/`、`chore/`を使う。
作業ブランチ名に`codex/`や`phase-X-`などの内部情報を含めない。
開発補助・設定・スキル保守は`chore/`に相当する。

例 `feat/db-connection`、`docs/branch-and-pr-rules`

## PRとマージ後

- PR作成前に、baseが対象Phaseか、Phase完了PRなら`main`かを確認する。
- PR本文は[PRテンプレート](../../../.github/PULL_REQUEST_TEMPLATE.md)の見出し構成に沿い、対象・除外事項・検証結果を常体で簡潔に書く。
- PR作成や本文更新の前に、見出し構成と文体を確認する。
- マージ後の切り替え・最新化・削除も、`AGENTS.md`の承認対象とする。
- 次タスクは最新化を確認したPhaseから始める。
