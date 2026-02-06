#!/bin/bash
#
# Removes SentimentCollection cron jobs.
#
# Usage:
#   ./scheduling/uninstall_cron.sh
#

set -e

MARKER_BEGIN="# === BEGIN SentimentCollection scheduled jobs ==="
MARKER_END="# === END SentimentCollection scheduled jobs ==="

EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -q "$MARKER_BEGIN"; then
    CLEANED=$(echo "$EXISTING" | sed "/$MARKER_BEGIN/,/$MARKER_END/d")
    # Remove trailing blank lines
    CLEANED=$(echo "$CLEANED" | sed -e :a -e '/^\n*$/{$d;N;ba;}')

    if [ -z "$CLEANED" ]; then
        crontab -r
        echo "Cron jobs removed. Crontab is now empty."
    else
        echo "$CLEANED" | crontab -
        echo "SentimentCollection cron jobs removed."
    fi
else
    echo "No SentimentCollection cron jobs found in crontab."
fi

echo ""
echo "Current crontab:"
crontab -l 2>/dev/null || echo "(empty)"
