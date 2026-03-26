#!/bin/bash
set -e

DATA=/mnt/data

# Ensure persistent directories exist
mkdir -p "$DATA/snapshots" "$DATA/configs"

# Symlink into app directory so web_ui.py finds them at expected paths
ln -sfn "$DATA/snapshots" /app/snapshots
ln -sfn "$DATA/configs"   /app/configs

# Bootstrap config.yaml from env vars if not already present
if [ ! -f "$DATA/config.yaml" ]; then
  cat > "$DATA/config.yaml" << YAML
anthropic_api_key: "${ANTHROPIC_API_KEY:-}"
telegram_bot_token: "${TELEGRAM_BOT_TOKEN:-}"
telegram_chat_id: "${TELEGRAM_CHAT_ID:-}"
cameras: []
YAML
  echo "[camIA] Created initial config.yaml from environment"
fi

ln -sfn "$DATA/config.yaml" /app/config.yaml

exec python3 web_ui.py
