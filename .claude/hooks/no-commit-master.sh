#!/usr/bin/env bash
# PreToolUse (Bash): no commits on master, only merges from dev (/promote). Merge commits are allowed.
cmd=$(jq -r '.tool_input.command // empty')
[[ $cmd == *"git commit"* ]] || exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[[ $branch == master ]] || exit 0
[[ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]] && exit 0
echo "On master: commit to dev, reach master by merging via /promote. Switch: git switch dev" >&2
exit 2
