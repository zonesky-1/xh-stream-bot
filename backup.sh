#!/usr/bin/env bash
# backup xh-bot v2 → ~/backups/xh-bot-YYYYMMDD-HHMMSS.tar.gz
# isi: source + .env + requirements.txt + backup.sh (tanpa .venv/dl/log — bisa rebuild)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p "$HOME/backups"
OUT="$HOME/backups/xh-bot-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$OUT" \
    --exclude='./.venv' \
    --exclude='./dl' \
    --exclude='./bot.log' \
    --exclude='./__pycache__' \
    .
echo "$OUT"
ls -la "$OUT"
