#!/usr/bin/env bash
# PreToolUse: не даёт читать и править data/ — там сессия Telegram и api_hash (доступ к аккаунту).
f=$(jq -r '.tool_input.file_path // .tool_input.path // empty')
[[ -n $f ]] || exit 0
case "$f" in
  /*) abs=$f ;;
  *) abs="$CLAUDE_PROJECT_DIR/$f" ;;
esac
data="$CLAUDE_PROJECT_DIR/data"
if [[ $abs == "$data" || $abs == "$data"/* ]]; then
  echo "Доступ к data/ заблокирован: там сессия и ключи аккаунта. Если это действительно нужно — попроси пользователя." >&2
  exit 2
fi
exit 0
