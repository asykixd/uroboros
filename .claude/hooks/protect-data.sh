#!/usr/bin/env bash
# PreToolUse: blocks reading and editing data/: it holds the Telegram session and api_hash (account access).
f=$(jq -r '.tool_input.file_path // .tool_input.path // empty')
[[ -n $f ]] || exit 0
case "$f" in
  /*) abs=$f ;;
  *) abs="$CLAUDE_PROJECT_DIR/$f" ;;
esac
data="$CLAUDE_PROJECT_DIR/data"
if [[ $abs == "$data" || $abs == "$data"/* ]]; then
  echo "Access to data/ is blocked: it holds the session and account keys. If you really need it, ask the user." >&2
  exit 2
fi
exit 0
