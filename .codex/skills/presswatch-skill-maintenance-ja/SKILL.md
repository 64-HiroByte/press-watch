---
name: presswatch-skill-maintenance-ja
description: PressWatch の .codex/skills 配下でスキルを作成、更新、検証するときに使う。skill-creator と併用し、検証スクリプトの位置をスキルロケータから解決して uv run --with pyyaml で実行する。
---

# PressWatch Skill Maintenance JA

## 目的

`skill-creator` の設計方針に、PressWatch固有の配置と検証方法を補う。

このスキルでは、検証用のPyYAMLをPressWatch本体やローカルPythonへ追加せず、`uv run --with pyyaml` で一時的に用意する。

## 責務

- スキルの設計、frontmatter、補助リソースの判断は `skill-creator` に従う。
- PressWatch固有のスキルは `.codex/skills/` 配下に置く。
- 検証用依存をPressWatchの依存定義へ追加しない。
- 変更したスキルと、影響を受ける参照元を検証する。

## 検証スクリプトの解決

1. 利用可能スキル一覧にある `skill-creator` のロケータを確認する。
2. ファイルシステム上の `SKILL.md` を指す場合は、そのディレクトリを `skill_creator_dir` として解決する。
3. `skill_creator_dir/scripts/quick_validate.py` が存在することを確認する。
4. ファイルシステム上のロケータを取得できない場合は、パスを推測せず停止して報告する。

ユーザー名を含む絶対パスや、特定マシンだけのインストール先を `SKILL.md` に固定しない。

## 検証コマンド

ロケータから解決した実パスを設定し、対象スキルごとに実行する。

```bash
skill_creator_dir="/absolute/path/resolved/from/skill-locator"
target_skill_dir=".codex/skills/presswatch-notes-ja"
uv run --with pyyaml python "$skill_creator_dir/scripts/quick_validate.py" "$target_skill_dir"
```

`quick_validate.py` はfrontmatter、命名、未完了の雛形を検証する。
責務、発火条件、対象外、参照関係の妥当性は別に読み直す。

## 失敗時

ネットワークまたはuvキャッシュの権限制約で失敗した場合は、同じコマンドを必要な権限で再実行する。
別のPython環境へPyYAMLをインストールしたり、PressWatch本体の依存へ追加したりしない。

構造上の失敗では、frontmatterの `name` と `description`、フォルダ名、未完了の雛形を確認する。

## 完了前チェック

- 変更したスキルへ `quick_validate.py` を実行したか。
- frontmatterのdescriptionが、使う場面と対象外を判別できるか。
- 参照するスキルとファイルが実在するか。
- 詳細手順を複数スキルへ重複させていないか。
- `presswatch-markdown-style-ja` に従ってMarkdownを検証したか。
