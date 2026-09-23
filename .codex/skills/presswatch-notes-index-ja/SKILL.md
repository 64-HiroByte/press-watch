---
name: presswatch-notes-index-ja
description: ユーザーまたはtask.mdが明示したPressWatchのnotes全体の整理、索引、読む順番の見直しに使う。
---

# PressWatch Notes Index JA

## 適用と範囲

notes全体の整理が依頼または現在の`task.md`に明示されている場合に使う。
調査・提案だけの依頼では編集せず、Phase完了やメモ数の増加だけで整理を始めない。

個別内容を編集する場合だけ、対応するスキルを参照する。

- 学習・設計判断・質疑: `presswatch-notes-ja`
- API・コマンドの使い方: `presswatch-usage-notes-ja`
- 用語集: `presswatch-glossary-ja`

これらから再び本スキルへ戻る必要はない。

## 参照と分類

`notes/README.md`と対象の索引から始め、ファイル名・見出しで候補を絞って必要な本文だけ読む。

- `notes/README.md`: 全体の入口、分類、読む順番。
- サブディレクトリの`README.md`: 同じテーマの複数メモの範囲と読む順番。
- `notes/timeline/`: 当時の作業、判断、検証結果。
- `notes/topics/`: 再利用する概念、責務分担、設計判断。
- `notes/usage/`: API・ライブラリ・コマンドの使い方。
- `notes/topics/presswatch-glossary.md`: 短い意味と詳細メモへの入口。

## 編集時の判断

- READMEと用語集には短い入口を置き、詳説の正本へリンクする。
- timelineは当時の記録として維持し、文章の類似だけで履歴や必要な導入を削らない。
- 現在を説明するtopics・usage・READMEは、必要なコードやdocsと照合する。
- 当時・変更前・現在を区別し、未確認の設計案を実装済みと記述しない。
- 既存メモへの追記で足りれば、新規ファイルは増やさない。
- 分類変更や多数の移動・改名・統合・削除は、対象とリンクへの影響、利点・欠点を示して了承を得る。
- timelineの履歴削除、notesのGit管理対象化、docsへの移動、製品コードや共有docsの変更は自動で行わない。

## 検証

相対リンクと見出しの参照先、項目の重複、時制を確認する。
必要に応じて`git check-ignore -v`で管理状態を確認し、Markdownの検証は`presswatch-markdown-style-ja`に従う。
