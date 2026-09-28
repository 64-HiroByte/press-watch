---
name: presswatch-skill-maintenance-ja
description: PressWatchの.codex/skills配下でスキルを作成・更新・検証するときに使う。
---

# PressWatch Skill Maintenance JA

設計とfrontmatterは`skill-creator`に従い、PressWatch固有のスキルは`.codex/skills/`に置く。
検証用のPyYAMLは`uv run --with pyyaml`で一時的に用意し、プロジェクト依存や別のPython環境へ追加しない。

## 検証

利用可能スキル一覧の`skill-creator`のロケータからディレクトリを解決し、`scripts/quick_validate.py`の存在を確認する。
ロケータを取得できない場合はパスを推測せず、構造検証が未実施であることと理由を報告する。
ユーザー名や特定マシンのインストール先をスキルへ固定しない。

変更したスキルと、影響を受ける参照元を検証する。

```bash
skill_creator_dir="/absolute/path/resolved/from/skill-locator"
target_skill_dir=".codex/skills/presswatch-notes-ja"
uv run --with pyyaml python "$skill_creator_dir/scripts/quick_validate.py" "$target_skill_dir"
```

ネットワーク・キャッシュの権限制約で失敗した場合は、同じコマンドを必要な権限で再実行する。
構造エラーはfrontmatter、命名、未完了の雛形を確認して直す。

バリデータだけでは適用判断を保証できないため、代表的な依頼と対象外の依頼で、適用条件・責務・参照関係も見直す。
Markdownの書式と空白検証は`presswatch-markdown-style-ja`に従う。
