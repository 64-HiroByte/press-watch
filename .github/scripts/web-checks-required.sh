#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "Usage: bash web-checks-required.sh BASE HEAD" >&2
  exit 2
fi

changed_files="$(mktemp)"
trap 'rm -f "$changed_files"' EXIT

# 改名元の削除も判定し、ファイル名内の改行を区切りとして扱わない。
git diff --name-only --no-renames -z "$1" "$2" > "$changed_files"

web_checks_required=false
while IFS= read -r -d '' changed_file; do
  printf -- '- %q\n' "$changed_file" >&2
  case "$changed_file" in
    *.md)
      ;;
    apps/web/*|package.json|pnpm-lock.yaml|pnpm-workspace.yaml|.oxlintrc.json|.oxfmtrc.json|.editorconfig|.gitattributes|.github/workflows/*|.github/scripts/*|infra/docker/web.Dockerfile)
      web_checks_required=true
      ;;
  esac
done < "$changed_files"

printf '%s\n' "$web_checks_required"
