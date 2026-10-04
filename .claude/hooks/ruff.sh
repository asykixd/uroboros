#!/usr/bin/env bash
# PostToolUse: форматирует и чинит линтером только что изменённый .py-файл.
f=$(jq -r '.tool_input.file_path // empty')
[[ $f == *.py && -f $f ]] || exit 0
ruff="$CLAUDE_PROJECT_DIR/.venv/bin/ruff"
[[ -x $ruff ]] || exit 0
"$ruff" format -q "$f"
if ! out=$("$ruff" check -q --fix "$f" 2>&1); then
  echo "ruff check: остались ошибки в $f" >&2
  echo "$out" >&2
  exit 2
fi
exit 0
