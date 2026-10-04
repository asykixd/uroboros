#!/usr/bin/env bash
# PostToolUse: formats and lint-fixes the just-edited .py file.
f=$(jq -r '.tool_input.file_path // empty')
[[ $f == *.py && -f $f ]] || exit 0
ruff="$CLAUDE_PROJECT_DIR/.venv/bin/ruff"
[[ -x $ruff ]] || exit 0
"$ruff" format -q "$f"
if ! out=$("$ruff" check -q --fix "$f" 2>&1); then
  echo "ruff check: errors left in $f" >&2
  echo "$out" >&2
  exit 2
fi
exit 0
