#!/usr/bin/env bash
# Adds (or replaces) the nightly 00:00 job in your crontab. Remove with: ./install_cron.sh --remove
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
MARK="# admission_watch"
# headed browser under a virtual screen, so it matches the Chrome used for --verify
XVFB="$(command -v xvfb-run >/dev/null && echo "xvfb-run -a" || true)"
LINE="0 0 * * * cd $DIR && /usr/bin/flock -n /tmp/admission_watch.lock $XVFB $DIR/.venv/bin/python $DIR/admission_watch.py >> $DIR/logs/cron.log 2>&1 $MARK"
mkdir -p "$DIR/logs"
current="$(crontab -l 2>/dev/null | grep -v "$MARK" || true)"
if [[ "${1:-}" == "--remove" ]]; then
  printf '%s\n' "$current" | sed '/^$/d' | crontab -
  echo "admission_watch cron job removed"; exit 0
fi
printf '%s\n%s\n' "$current" "$LINE" | sed '/^$/d' | crontab -
echo "Installed. Runs every night at 00:00 ($(cat /etc/timezone 2>/dev/null || date +%Z)):"
crontab -l | grep "$MARK"
