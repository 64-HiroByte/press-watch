---
name: presswatch-notes-ja
description: ユーザーまたはtask.mdが明示したPressWatchの学習メモ、設計判断、質疑をnotesへ記録するときに使う。
---

# PressWatch Notes JA

## 書き込み条件

ユーザーがnotesへの記録を依頼した場合、または現在の`task.md`が記録を作業範囲に含める場合だけ作成・更新する。
質問や実装完了だけで自動記録せず、条件を満たさない場合は必要に応じて保存先と理由を提案する。

## 保存先

- 時系列の作業・質疑: `notes/timeline/YYYY-MM-DD-topic.md`
- 概念・設計判断: `notes/topics/topic.md`
- API・コマンドの使い方: `notes/usage/topic.md`（`presswatch-usage-notes-ja`を使う）
- 用語集: `presswatch-glossary-ja`を使う。

notes全体の整理が依頼された場合だけ`presswatch-notes-index-ja`を使う。
同じ内容のメモがあれば追記を優先し、notesのGit管理状態は変えない。

## 記録する内容

確認した事実、判断理由、代替案、質疑で整理した論点、除外事項、次回の確認点から必要な情報を短く残す。
コマンドは実際に確認したものだけを書く。
共有する仕様・手順・進捗は`docs/`を正本とし、notesには個人の理解や判断の背景を置いて重複を避ける。

見出しは検索しやすい名前にし、Markdownの書式と検証は`presswatch-markdown-style-ja`に従う。
