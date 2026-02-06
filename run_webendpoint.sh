#!/bin/bash
set -e

# Create logs directory if it doesn't exist
mkdir -p logs

# Set log filename with timestamp
timestamp=$(date +%Y%m%d_%H%M%S)
logfile="logs/${timestamp}.log"

# Logging function
log() {
    echo "$1"
    echo "$1" >> "$logfile"
}

# Function to clean up old logs
cleanup_logs() {
    local count
    count=$(find logs -name "*.log" -type f | wc -l)

    # If there are more than 11 files, delete the oldest ones
    if [ "$count" -gt 11 ]; then
        find logs -name "*.log" -type f -printf '%T+ %p\n' | \
            sort | head -n $((count - 11)) | cut -d' ' -f2- | \
            while read -r file; do
                rm -f "$file"
                log "Deleted old log file: $file"
            done
    fi
}

log "=== Script started at $(date) ==="

# Change to script directory
cd "$(dirname "$0")"

# Initialize Conda
if [ -f "$HOME/miniconda/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    source "/opt/conda/etc/profile.d/conda.sh"
fi

# Activate Conda environment
if ! conda activate webscrap 2>/dev/null; then
    log "Failed to activate Conda environment"
    exit 1
fi
log "Conda environment 'webscrap' activated successfully"

# Check if webendpoint_json_data.py exists
if [ ! -f "webendpoint_json_data.py" ]; then
    log "Error: webendpoint_json_data.py not found"
    exit 1
fi
log "Found webendpoint_json_data.py"

# Run the script
log "Running webendpoint_json_data.py..."
if ! python webendpoint_json_data.py >> "$logfile" 2>&1; then
    log "Error: Script execution failed"
    exit 1
fi

# Deactivate Conda environment
conda deactivate
log "Conda environment deactivated"

# Clean up old logs
cleanup_logs
log "Log cleanup completed"

log "Script completed successfully"
log "=== Script ended at $(date) ==="
echo "Script completed successfully"
