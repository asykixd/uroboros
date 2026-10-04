#!/usr/bin/env bash
# PreToolUse (Bash): в master коммитить нельзя — только слиянием dev (/promote). Коммит слияния разрешён.
cmd=$(jq -r '.tool_input.command // empty')
[[ $cmd == *"git commit"* ]] || exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[[ $branch == master ]] || exit 0
[[ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]] && exit 0
echo "Сейчас ветка master: коммиты — только в dev, в master — слиянием через /promote. Переключитесь: git switch dev" >&2
exit 2
