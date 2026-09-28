---
name: phase-branch-workflow-ja
description: PressWatchのPhase・タスクブランチ、PRのbase、マージ後の整理を扱うときに使う。
---

# Phase Branch Workflow JA

Git操作の承認は`AGENTS.md`に従う。
このスキルでは分岐元、命名、PRの統合先を扱う。

## 分岐元とPRのbase

- Phase全体の統合先は`phase-N/...`とする。
- タスクブランチは対象Phaseブランチから作成し、タスクPRも同じPhaseをbaseにする。
- 前タスクの作業ブランチを次タスクの親にせず、Phaseブランチへタスク差分を直接作らない。
- Phase完了時だけ、Phaseブランチから`main`へPRを作成する。

## 開始・再開時

`git status --short --branch`と関連する参照を確認し、現在の状態、親ブランチ、作業ブランチ案を報告する。
既存差分がある場合は所有者と移動先を確認し、差分を保つ方法を選ぶ。
切り替え・最新化・作成は、承認された操作だけ行う。

## 命名

Phaseブランチは`phase-3/db-persistence`のように命名する。
タスクブランチは具体的な作業内容を表し、通常は`docs/`、`feat/`、`fix/`、`refactor/`、`test/`、`chore/`を使う。
ユーザーや実行環境が接頭辞を指定している場合は、その指定に合わせる。
開発補助・設定・スキル保守は`chore/`に相当する。

例: `feat/phase-3-db-connection`、`chore/agent-workflow-audit`

## PRとマージ後

- PR作成前に、baseが対象Phaseか、Phase完了PRなら`main`かを確認する。
- PR本文には、対象・除外事項・検証結果を短く示す。
- マージ後の切り替え・最新化・削除も、`AGENTS.md`の承認対象とする。
- 次タスクは最新化を確認したPhaseから始める。
