---
name: presswatch-skill-maintenance-ja
description: PressWatch の .codex/skills 配下でスキルを新規作成・更新・検証するときに使う。skill-creator と併用し、quick_validate.py はローカル Python へ依存を入れず uv run --with pyyaml で実行する運用を固定するためのスキル。
---

# PressWatch Skill Maintenance JA

## 目的

PressWatch のローカルスキルを作成・更新するときの検証手順を揃える。

特に `quick_validate.py` の実行で `PyYAML` 不足に毎回引っかからないよう、ローカル Python ではなく `uv run --with pyyaml` を使う。

## 基本方針

- スキルの設計・記述は `skill-creator` に従う
- スキルは小さく保ち、既存スキルを肥大化させない
- PressWatch 固有の運用は `.codex/skills/` 配下に置く
- 検証用依存は PressWatch 本体の依存へ追加しない
- ローカル Python へ `PyYAML` を直接インストールしない

## 検証コマンド

スキル作成・更新後は、対象スキルに対して次を実行する。

```bash
uv run --with pyyaml python /Users/hiro/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/<skill-name>
```

例:

```bash
uv run --with pyyaml python /Users/hiro/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/presswatch-notes-ja
```

`uv run --with pyyaml` は、この検証実行にだけ `PyYAML` を用意する。
PressWatch の `pyproject.toml` やローカル Python 環境を汚さない。

## 検証が失敗したとき

- frontmatter の `name` / `description` をまず確認する
- `name` は小文字英数字とハイフンだけにする
- `description` は、そのスキルを使うタイミングが分かる文にする
- `SKILL.md` 以外の README や補助ドキュメントを安易に増やさない

ネットワークやキャッシュ権限で `uv run --with pyyaml` が失敗した場合は、必要に応じて権限昇格で同じコマンドを再実行する。
その場合も、PressWatch 本体の依存関係には追加しない。

## 完了前チェック

- `quick_validate.py` を `uv run --with pyyaml` 経由で実行したか
- `git diff --check` を実行したか
- 新スキルの責務が既存スキルと重なりすぎていないか
- 既存スキルには参照だけを足し、詳細手順を重複させていないか
