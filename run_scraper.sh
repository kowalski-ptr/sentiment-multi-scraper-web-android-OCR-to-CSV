#!/bin/bash
#
# ============================================================================
# UNIFIED ENTRY POINT FOR SENTIMENT DATA COLLECTION
# ============================================================================
#
# This is the SINGLE entry point for the entire sentiment collection pipeline.
# All data collection paths converge here, and main.py handles all processing.
#
# Architecture (Centralized Processing):
#
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │ run_scraper.sh (THIS FILE - Universal Orchestrator)                 │
#   │     │                                                               │
#   │     ├── Step 1: Data Collection (based on USE_ANDROID_APP)         │
#   │     │     ├── android_app → collect_sentiment.sh (screenshots)     │
#   │     │     └── webscrap_api → scrapy crawl sentiment (JSON)         │
#   │     │                                                               │
#   │     └── Step 2: ALWAYS call main.py for:                           │
#   │           ├── Data processing (OCR/CSV or JSON parsing)            │
#   │           ├── git_handler.push_changes() ← CRITICAL                │
#   │           └── GitPublisher.publish()     ← CRITICAL                │
#   └─────────────────────────────────────────────────────────────────────┘
#
# The git operations are CENTRALIZED in main.py - this ensures:
#   - Single source of truth for git push logic
#   - Consistent behavior for both data sources
#   - Easy debugging and maintenance
#
# Configuration: Set USE_ANDROID_APP in .env (true/false)
#

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_RETRIES=3
RETRY_DELAY=30

# =============================================================================
# CLI FLAGS FOR TESTING
# =============================================================================
# --no-git      Skip git add/commit/push (useful for local testing)
# --no-publish  Skip publishing to public repository
# --dry-run     Alias for --no-git --no-publish (full test mode)
# --debug       Save raw OCR text to ocr-data/ocr_debug_raw.txt for analysis
#
# Example usage:
#   ./run_scraper.sh --no-git          # Collect data but don't push
#   ./run_scraper.sh --dry-run         # Full test mode, no git operations
#   ./run_scraper.sh --debug           # Save raw OCR output for debugging
#   ./run_scraper.sh                   # Production mode (default)
# =============================================================================
NO_GIT=""
NO_PUBLISH=""
DEBUG_FLAG=""

for arg in "$@"; do
    case $arg in
        --no-git)
            NO_GIT="--no-git"
            echo "[FLAG] --no-git: Git operations will be SKIPPED"
            ;;
        --no-publish)
            NO_PUBLISH="--no-publish"
            echo "[FLAG] --no-publish: Public repo publish will be SKIPPED"
            ;;
        --dry-run)
            NO_GIT="--no-git"
            NO_PUBLISH="--no-publish"
            echo "[FLAG] --dry-run: ALL git operations will be SKIPPED (test mode)"
            ;;
        --debug)
            DEBUG_FLAG="--debug"
            echo "[FLAG] --debug: Raw OCR text will be saved to ocr_debug_raw.txt"
            ;;
    esac
done

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Set conda env per source:
#   android   → (used by collect_sentiment.sh)
#   webscrap  → web scraping pipeline
# NOTE: Adjust these conda environment names to match your setup
CONDA_ENV_ANDROID="android"
CONDA_ENV_WEBSCRAP="webscrap"

send_failure_email() {
    local source="$1"
    local error_msg="$2"
    conda run -n "$CONDA_ENV" python -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/scripts')
from email_notifier import EmailNotifier
notifier = EmailNotifier()
notifier.send_email(
    subject='[SentimentCollection] Collection FAILED ($source)',
    body='Sentiment data collection failed after $MAX_RETRIES retries.\n\nSource: $source\nError: $error_msg\nHost: $(hostname)\nTime: $(date)'
)
"
}

run_android_app() {
    bash "$PROJECT_DIR/collect_sentiment.sh"
}

run_webscrap_api() {
    cd "$PROJECT_DIR/webscrap_zyteapi"
    conda run -n "$CONDA_ENV" scrapy crawl sentiment 2>&1
}

# Select data source and conda env
if [ "${USE_ANDROID_APP:-true}" = "true" ]; then
    SOURCE="android_app"
    CONDA_ENV="$CONDA_ENV_ANDROID"
    RUN_CMD="run_android_app"
else
    SOURCE="webscrap_api"
    CONDA_ENV="$CONDA_ENV_WEBSCRAP"
    RUN_CMD="run_webscrap_api"
fi

echo "=========================================="
echo "Sentiment Collection - run_scraper"
echo "Source: $SOURCE"
echo "Started: $(date)"
echo "=========================================="

# Retry loop
ATTEMPT=0
SUCCESS=false

while [ $ATTEMPT -lt $MAX_RETRIES ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo ""
    echo "[Attempt $ATTEMPT/$MAX_RETRIES]"

    if $RUN_CMD; then
        SUCCESS=true
        break
    else
        EXIT_CODE=$?
        echo "[run_scraper] Attempt $ATTEMPT failed (exit code: $EXIT_CODE)"
        if [ $ATTEMPT -lt $MAX_RETRIES ]; then
            echo "[run_scraper] Retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
        fi
    fi
done

if [ "$SUCCESS" = true ]; then
    echo ""
    echo "=========================================="
    echo "Data collection completed successfully"
    echo "=========================================="

    # =========================================================================
    # CRITICAL: Call main.py to process data and push to git
    # This is the CENTRAL HUB for all data processing and git operations.
    # Both android_app and webscrap_api paths converge here.
    # =========================================================================
    echo ""
    echo "=========================================="
    echo "Processing data and pushing to git..."
    echo "Source: $SOURCE"
    echo "=========================================="

    # Determine main.py source flag based on data source
    if [ "$SOURCE" = "android_app" ]; then
        MAIN_SOURCE="androidapp"
    else
        MAIN_SOURCE="webscrapzyteapi"
    fi

    # Run main.py - this handles:
    #   1. Data processing (OCR extraction + CSV for AndroidApp, or JSON parsing for WebScrapZyteAPI)
    #   2. git add, commit, push to origin (via git_handler.py)
    #   3. Publishing CSV files to public repository (via GitPublisher)
    echo ""
    echo "[main.py] Running with --source $MAIN_SOURCE $NO_GIT $NO_PUBLISH $DEBUG_FLAG..."

    if conda run -n "$CONDA_ENV" python "$PROJECT_DIR/main.py" --source "$MAIN_SOURCE" --output-dir "$PROJECT_DIR/data" $NO_GIT $NO_PUBLISH $DEBUG_FLAG; then
        echo ""
        echo "=========================================="
        echo "Pipeline completed successfully!"
        echo "  - Data collected from: $SOURCE"
        echo "  - CSVs updated in: $PROJECT_DIR/data/"
        if [ -n "$NO_GIT" ]; then
            echo "  - Git push: SKIPPED (--no-git flag)"
        else
            echo "  - Changes pushed to git"
        fi
        if [ -n "$NO_PUBLISH" ]; then
            echo "  - Public repo: SKIPPED (--no-publish flag)"
        fi
        echo "Finished: $(date)"
        echo "=========================================="
        exit 0
    else
        MAIN_EXIT_CODE=$?
        ERROR_MSG="main.py failed with exit code $MAIN_EXIT_CODE (source: $SOURCE)"
        echo ""
        echo "=========================================="
        echo "ERROR: $ERROR_MSG"
        echo "=========================================="
        send_failure_email "$SOURCE" "$ERROR_MSG"
        exit 1
    fi
else
    ERROR_MSG="All $MAX_RETRIES attempts failed for source: $SOURCE"
    echo ""
    echo "=========================================="
    echo "ERROR: $ERROR_MSG"
    echo "=========================================="
    send_failure_email "$SOURCE" "$ERROR_MSG"
    exit 1
fi
