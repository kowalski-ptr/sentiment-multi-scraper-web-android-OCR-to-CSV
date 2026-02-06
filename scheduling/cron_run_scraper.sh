#!/bin/bash
#
# Cron wrapper for run_scraper.sh
# Checks SCHEDULE_RUN_SCRAPER in .env before executing.
# If the variable is false or missing, the script exits silently.
#
# The cron job fires unconditionally Mon-Fri at 14:00 CET.
# This wrapper provides the runtime toggle via .env boolean.
#

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

LOGFILE="$LOG_DIR/cron_run_scraper_$(date +%Y%m%d_%H%M%S).log"

# Load .env
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Check the toggle - default to false (manual mode)
if [ "${SCHEDULE_RUN_SCRAPER:-false}" != "true" ]; then
    echo "$(date): SCHEDULE_RUN_SCRAPER is not true, skipping." >> "$LOGFILE"
    exit 0
fi

echo "$(date): Starting scheduled run_scraper.sh" >> "$LOGFILE"

# Execute the actual script, capturing all output
"$PROJECT_DIR/run_scraper.sh" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

echo "$(date): run_scraper.sh finished with exit code $EXIT_CODE" >> "$LOGFILE"

# Rotate logs: keep max 11 files
LOG_COUNT=$(find "$LOG_DIR" -name "cron_run_scraper_*.log" -type f | wc -l)
if [ "$LOG_COUNT" -gt 11 ]; then
    find "$LOG_DIR" -name "cron_run_scraper_*.log" -type f -printf '%T+ %p\n' | \
        sort | head -n $((LOG_COUNT - 11)) | cut -d' ' -f2- | \
        while read -r file; do
            rm -f "$file"
        done
fi

exit $EXIT_CODE
