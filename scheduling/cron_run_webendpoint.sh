#!/bin/bash
#
# Cron wrapper for run_webendpoint.sh
# Handles logging and log rotation for scheduled runs.
#
# run_webendpoint.sh creates its own logs (logs/YYYYMMDD_HHMMSS.log),
# this wrapper captures additional output (conda init failures, etc.)
#

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

LOGFILE="$LOG_DIR/cron_webendpoint_$(date +%Y%m%d_%H%M%S).log"

echo "$(date): Starting scheduled run_webendpoint.sh" >> "$LOGFILE"

"$PROJECT_DIR/run_webendpoint.sh" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

echo "$(date): run_webendpoint.sh finished with exit code $EXIT_CODE" >> "$LOGFILE"

# Rotate logs: keep max 11 files (matching run_webendpoint.sh convention)
LOG_COUNT=$(find "$LOG_DIR" -name "cron_webendpoint_*.log" -type f | wc -l)
if [ "$LOG_COUNT" -gt 11 ]; then
    find "$LOG_DIR" -name "cron_webendpoint_*.log" -type f -printf '%T+ %p\n' | \
        sort | head -n $((LOG_COUNT - 11)) | cut -d' ' -f2- | \
        while read -r file; do
            rm -f "$file"
        done
fi

exit $EXIT_CODE
