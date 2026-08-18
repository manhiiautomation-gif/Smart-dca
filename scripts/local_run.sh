#!/bin/bash
# Local bot run + generate dashboard + commit + push
# Usage: bash scripts/local_run.sh [--exchange bitkub] [--force]

set -e
cd "$(dirname "$0")/.."

EXCHANGE="${1:---exchange bitkub}"
shift 2>/dev/null || true
EXTRA="$@"

echo "=== Running bot ==="
python live_bot/main.py $EXCHANGE --dry-run $EXTRA

echo "=== Generating dashboard ==="
python scripts/generate_dashboard.py

echo "=== Committing & pushing ==="
git add live_bot/state.json live_bot/_mvrv_history.py trade_log.json dashboard/dist/index.html
git diff --staged --quiet && echo "No changes" && exit 0

git commit -m "local: bot + dashboard update $(date -u +%Y-%m-%d\ %H:%M\ UTC)"
git pull --rebase
git push
echo "=== Done ==="