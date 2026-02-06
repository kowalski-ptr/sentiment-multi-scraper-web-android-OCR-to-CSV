#!/bin/bash
#
# Installs cron jobs for sentiment data collection.
#
# Jobs installed:
#   1. run_webendpoint.sh  - Mon, Wed, Fri at 12:00 CET (always active)
#   2. run_scraper.sh      - Mon-Fri at 14:00 CET (controlled by SCHEDULE_RUN_SCRAPER in .env)
#
# Usage:
#   ./scheduling/install_cron.sh          # Install cron jobs
#   ./scheduling/install_cron.sh --check  # Show what would be installed (dry run)
#

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER_BEGIN="# === BEGIN SentimentCollection scheduled jobs ==="
MARKER_END="# === END SentimentCollection scheduled jobs ==="

# Verify cronie is available
if ! command -v crontab &> /dev/null; then
    echo "ERROR: crontab command not found."
    echo "Install cronie:  sudo dnf install cronie"
    echo "Then enable it:  sudo systemctl enable --now crond"
    exit 1
fi

# Build the cron block
CRON_BLOCK="$MARKER_BEGIN
# Timezone: Central European Time (CET/CEST with automatic DST switch)
CRON_TZ=Europe/Warsaw

# run_webendpoint.sh - Mon, Wed, Fri at 12:00 CET
0 12 * * 1,3,5 $PROJECT_DIR/scheduling/cron_run_webendpoint.sh

# run_scraper.sh (via wrapper) - Mon-Fri at 14:00 CET
# Actual execution controlled by SCHEDULE_RUN_SCRAPER in .env
0 14 * * 1-5 $PROJECT_DIR/scheduling/cron_run_scraper.sh

$MARKER_END"

if [ "$1" = "--check" ]; then
    echo "The following cron block would be installed:"
    echo ""
    echo "$CRON_BLOCK"
    echo ""
    echo "Current crontab:"
    crontab -l 2>/dev/null || echo "(empty)"
    exit 0
fi

# Get existing crontab, stripping any previous SentimentCollection block
EXISTING=$(crontab -l 2>/dev/null || true)
CLEANED=$(echo "$EXISTING" | sed "/$MARKER_BEGIN/,/$MARKER_END/d")

# Remove trailing blank lines from cleaned crontab
CLEANED=$(echo "$CLEANED" | sed -e :a -e '/^\n*$/{$d;N;ba;}')

# Install new crontab
if [ -n "$CLEANED" ]; then
    printf '%s\n\n%s\n' "$CLEANED" "$CRON_BLOCK" | crontab -
else
    echo "$CRON_BLOCK" | crontab -
fi

echo "Cron jobs installed successfully."
echo ""
echo "Schedule:"
echo "  run_webendpoint.sh  -> Mon, Wed, Fri at 12:00 CET"
echo "  run_scraper.sh      -> Mon-Fri at 14:00 CET (toggle: SCHEDULE_RUN_SCRAPER in .env)"
echo ""
echo "Verify with:  crontab -l"
echo "Remove with:  ./scheduling/uninstall_cron.sh"
