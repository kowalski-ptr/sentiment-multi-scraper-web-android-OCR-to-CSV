#!/bin/bash
#
# Android App Sentiment Data Collection Script (Hardware Layer)
#
# This script handles ONLY the Android emulator and screenshot capture:
#   1. Start emulator
#   2. Unlock screen
#   3. Navigate to sentiment screen (Maestro/ADB fallback)
#   4. Capture screenshots
#   5. Shutdown emulator
#
# Data processing (OCR, CSV generation) and git operations are handled
# by main.py, which is called by run_tms_scraper.sh after this script completes.
#
# Architecture (Centralized Processing):
#     run_scraper.sh
#         ├── collect_sentiment.sh → screenshots only (this script)
#         └── main.py --source androidapp → OCR + CSV + git push
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREENSHOTS_DIR="$SCRIPT_DIR/screenshots"
OCR_DATA_DIR="$SCRIPT_DIR/ocr-data"
MAESTRO_FLOW="$SCRIPT_DIR/maestro/navigate_to_sentiment.yaml"
EXTRACT_SCRIPT="$SCRIPT_DIR/extract_sentiment.py"
OUTPUT_CSV="$OCR_DATA_DIR/android_sentiment_raw.csv"
ADB_DEVICE="emulator-5554"
AVD_NAME="sentiment_avd"
EMULATOR_TIMEOUT=120

# Add Maestro to PATH
export PATH="$PATH:$HOME/.maestro/bin"

# Load environment variables from .env file
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

echo "=========================================="
echo "Android App Sentiment Data Collection"
echo "Started at: $(date)"
echo "=========================================="

# Step 1: Clear old screenshots and prepare directories
echo ""
echo "[1/6] Clearing old screenshots..."
rm -f "$SCREENSHOTS_DIR"/*.png
mkdir -p "$SCREENSHOTS_DIR"
mkdir -p "$OCR_DATA_DIR"
echo "  Done."

# Step 2: Start emulator if not running
echo ""
echo "[2/6] Starting emulator..."
if adb devices | grep -q "$ADB_DEVICE.*device"; then
    echo "  Emulator already running."
else
    echo "  Starting emulator via cage..."
    cage -- ~/Android/Sdk/emulator/emulator -avd "$AVD_NAME" -gpu host -no-audio -no-snapshot -no-metrics &
    EMULATOR_PID=$!
    
    echo "  Waiting for emulator to boot (max ${EMULATOR_TIMEOUT}s)..."
    ELAPSED=0
    while [ $ELAPSED -lt $EMULATOR_TIMEOUT ]; do
        if adb devices | grep -q "$ADB_DEVICE.*device"; then
            # Check if boot completed
            BOOT_COMPLETED=$(adb -s $ADB_DEVICE shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
            if [ "$BOOT_COMPLETED" = "1" ]; then
                echo "  Emulator booted after ${ELAPSED}s."
                break
            fi
        fi
        sleep 2
        ELAPSED=$((ELAPSED + 2))
        echo -n "."
    done
    echo ""
    
    if [ $ELAPSED -ge $EMULATOR_TIMEOUT ]; then
        echo "  ERROR: Emulator failed to boot within ${EMULATOR_TIMEOUT}s"
        exit 1
    fi
    
    # Give it a few more seconds to stabilize
    sleep 3
fi

# Step 3: Wake up and unlock screen with PIN 1111
echo ""
echo "[3/6] Unlocking screen..."
# Set screen timeout to 30 minutes
adb -s $ADB_DEVICE shell settings put system screen_off_timeout 1800000
# Wake up screen
adb -s $ADB_DEVICE shell input keyevent KEYCODE_WAKEUP
sleep 0.5
# Swipe up to show PIN entry (repeat twice to ensure unlock)
adb -s $ADB_DEVICE shell input swipe 540 2200 540 400 500
sleep 0.5
adb -s $ADB_DEVICE shell input swipe 540 2200 540 400 500
sleep 1
# Enter PIN 1111 - button "1" coordinates
PIN_X=270
PIN_Y=1050
for i in 1 2 3 4; do
    adb -s $ADB_DEVICE shell input tap $PIN_X $PIN_Y
    sleep 0.2
done
sleep 0.3
# Tap confirm/enter button (bottom right of keypad)
adb -s $ADB_DEVICE shell input tap 810 1850
sleep 1
echo "  Screen unlocked."

# Step 4: Use Maestro to navigate to sentiment screen
echo ""
echo "[4/6] Navigating to sentiment screen with Maestro..."

# Restart ADB server to fix "device offline" issues with cage emulator
echo "  Restarting ADB server..."
adb kill-server 2>/dev/null || true
sleep 2
adb start-server 2>/dev/null || true
sleep 3

# Reconnect any offline devices
echo "  Reconnecting offline devices..."
adb reconnect offline 2>/dev/null || true
sleep 2

# Force device enumeration
adb devices 2>/dev/null

# Wait for device to be fully online
echo "  Waiting for device to be online..."
adb -s $ADB_DEVICE wait-for-device
for attempt in $(seq 1 15); do
    DEVICE_STATE=$(adb -s $ADB_DEVICE get-state 2>/dev/null)
    if [ "$DEVICE_STATE" = "device" ]; then
        echo "  Device online after attempt $attempt (state: $DEVICE_STATE)"
        # Extra verification - run a command
        if adb -s $ADB_DEVICE shell echo "ready" 2>/dev/null | grep -q "ready"; then
            echo "  Device responding to commands."
            break
        fi
    fi
    echo "  Attempt $attempt: device state is '$DEVICE_STATE', waiting..."
    sleep 2
done

# One more reconnect right before Maestro
adb reconnect offline 2>/dev/null || true
sleep 1

# Check if trading app is installed
# NOTE: Replace com.example.trading.app with your actual app package name
echo "  Checking if trading app is installed..."
if ! adb -s $ADB_DEVICE shell pm list packages | grep -q "com.example.trading.app"; then
    echo "  ERROR: Trading app not installed! Please install the app first."
    exit 1
fi
echo "  Trading app found."

# Maestro timeout in seconds (90s should be enough for navigation)
MAESTRO_TIMEOUT=90

echo "  Running Maestro (timeout: ${MAESTRO_TIMEOUT}s)..."
if timeout $MAESTRO_TIMEOUT maestro test "$MAESTRO_FLOW" --no-ansi 2>&1; then
    echo "  Navigation completed successfully."
else
    MAESTRO_EXIT=$?
    if [ $MAESTRO_EXIT -eq 124 ]; then
        echo "  WARNING: Maestro timed out after ${MAESTRO_TIMEOUT}s, switching to ADB fallback..."
    else
        echo "  WARNING: Maestro failed (exit code: $MAESTRO_EXIT), switching to ADB fallback..."
    fi

    # Fallback: ADB navigation with "man in the middle" manual login support

    # Helper function: tap with logging
    tap_and_log() {
        local X=$1
        local Y=$2
        local DESC=$3
        echo "  [TAP] ($X, $Y) - $DESC"
        adb -s $ADB_DEVICE shell input tap $X $Y
    }

    # Helper function: get current screen UI content (with retry for idle state issues)
    get_screen_content() {
        # Try uiautomator dump with retries (sometimes fails with "could not get idle state")
        for attempt in 1 2 3; do
            sleep 1  # Wait for app to stabilize
            if adb -s $ADB_DEVICE shell uiautomator dump /sdcard/ui.xml 2>&1 | grep -q "UI hierchary"; then
                adb -s $ADB_DEVICE shell cat /sdcard/ui.xml 2>/dev/null || true
                return
            fi
        done
        # Fallback: return empty if all attempts failed
        echo ""
    }

    # Helper function: get current focused activity (alternative detection method)
    get_current_activity() {
        adb -s $ADB_DEVICE shell dumpsys window windows 2>/dev/null | grep -E "mCurrentFocus|mFocusedApp" | head -1 || true
    }

    # Helper function: check if logged in (main app screen)
    is_logged_in() {
        # Method 1: Check UI content for logged-in elements
        local UI_CONTENT=$(get_screen_content)
        if echo "$UI_CONTENT" | grep -qi "Marketwatch" || \
           echo "$UI_CONTENT" | grep -qi "Equity" || \
           echo "$UI_CONTENT" | grep -qi "Margin" || \
           echo "$UI_CONTENT" | grep -qi "Portfolio" || \
           echo "$UI_CONTENT" | grep -qi "positions"; then
            return 0  # logged in
        fi

        # Method 2: Check that we're NOT on login/welcome screens
        if ! echo "$UI_CONTENT" | grep -q "Sign In" && \
           ! echo "$UI_CONTENT" | grep -q "LOG IN" && \
           ! echo "$UI_CONTENT" | grep -q "SIGN UP" && \
           ! echo "$UI_CONTENT" | grep -q "Email"; then
            # Not on any login screen - assume logged in
            return 0
        fi

        return 1  # not logged in
    }

    # Helper function: check if on credentials screen (Email + Sign In visible)
    is_on_credentials_screen() {
        local UI_CONTENT=$(get_screen_content)
        if echo "$UI_CONTENT" | grep -q "Sign In" || echo "$UI_CONTENT" | grep -q "Email"; then
            return 0
        fi
        return 1
    }

    # Helper function: check if on welcome screen (LOG IN / SIGN UP buttons)
    is_on_welcome_screen() {
        local UI_CONTENT=$(get_screen_content)
        if echo "$UI_CONTENT" | grep -q "LOG IN" || echo "$UI_CONTENT" | grep -q "SIGN UP"; then
            return 0
        fi
        return 1
    }

    # Helper function: display current screen state
    show_screen_state() {
        local UI_CONTENT=$(get_screen_content)
        echo "  [SCREEN] Detected elements:"
        echo "$UI_CONTENT" | grep -q "LOG IN" && echo "    - LOG IN (welcome screen)" || true
        echo "$UI_CONTENT" | grep -q "SIGN UP" && echo "    - SIGN UP (welcome screen)" || true
        echo "$UI_CONTENT" | grep -q "Accept All Cookies" && echo "    - Cookies popup" || true
        echo "$UI_CONTENT" | grep -q "Email" && echo "    - Email field (credentials)" || true
        echo "$UI_CONTENT" | grep -q "Password" && echo "    - Password field (credentials)" || true
        echo "$UI_CONTENT" | grep -q "Sign In" && echo "    - Sign In button (credentials)" || true
        echo "$UI_CONTENT" | grep -q "My Marketwatch" && echo "    - My Marketwatch (LOGGED IN)" || true
        echo "$UI_CONTENT" | grep -q "Equity" && echo "    - Equity (LOGGED IN)" || true
        echo "$UI_CONTENT" | grep -q "Traders Sentiment" && echo "    - Traders Sentiment" || true
        echo "$UI_CONTENT" | grep -q "Not now" && echo "    - Rating popup" || true
    }

    # Configuration for manual login wait
    MAX_WAIT_MINUTES=45
    CHECK_INTERVAL_SECONDS=30
    MAX_CHECKS=$((MAX_WAIT_MINUTES * 60 / CHECK_INTERVAL_SECONDS))

    # Step F1: Launch the app
    # NOTE: Replace com.example.trading.app with your actual app package name
    echo ""
    echo "  [F1] Launching trading app..."
    adb -s $ADB_DEVICE shell am start -n com.example.trading.app/.MainActivity
    sleep 5
    show_screen_state

    # Step F2: Click LOG IN if on welcome screen
    if is_on_welcome_screen; then
        echo ""
        echo "  [F2] On welcome screen, clicking LOG IN..."
        tap_and_log 540 1080 "LOG IN button"
        sleep 3
        show_screen_state
    else
        echo ""
        echo "  [F2] Not on welcome screen, skipping LOG IN click..."
    fi

    # Step F3: Handle cookies popup if present
    echo ""
    echo "  [F3] Checking for cookies popup..."
    UI_CONTENT=$(get_screen_content)
    if echo "$UI_CONTENT" | grep -q "Accept All Cookies"; then
        echo "  [F3] Cookies popup found, accepting..."
        tap_and_log 540 1650 "Accept All Cookies"
        sleep 2
        show_screen_state
    else
        echo "  [F3] No cookies popup."
    fi

    # Step F4: Check login state and wait for manual login if needed
    echo ""
    echo "  [F4] Checking login state..."

    if is_logged_in; then
        echo "  [F4] Already logged in! Proceeding to navigation..."
    elif is_on_credentials_screen; then
        echo ""
        echo "  =============================================="
        echo "  [MANUAL LOGIN REQUIRED]"
        echo "  Please log in manually in the emulator."
        echo "  Waiting up to $MAX_WAIT_MINUTES minutes..."
        echo "  Checking every $CHECK_INTERVAL_SECONDS seconds."
        echo "  =============================================="
        echo ""

        LOGIN_SUCCESS=false
        for check_num in $(seq 1 $MAX_CHECKS); do
            ELAPSED_MINUTES=$((check_num * CHECK_INTERVAL_SECONDS / 60))
            REMAINING_MINUTES=$((MAX_WAIT_MINUTES - ELAPSED_MINUTES))
            echo "  [WAITING] Check $check_num/$MAX_CHECKS (~${ELAPSED_MINUTES} min elapsed, ~${REMAINING_MINUTES} min remaining)..."

            if is_logged_in; then
                echo ""
                echo "  [SUCCESS] Login detected! Proceeding..."
                LOGIN_SUCCESS=true
                break
            fi

            sleep $CHECK_INTERVAL_SECONDS
        done

        if [ "$LOGIN_SUCCESS" = false ]; then
            echo ""
            echo "  =============================================="
            echo "  [TIMEOUT] No login after $MAX_WAIT_MINUTES minutes."
            echo "  Killing processes and exiting..."
            echo "  =============================================="

            # Kill emulator
            adb -s $ADB_DEVICE emu kill 2>/dev/null || true
            # Kill cage if running
            pkill -f "cage.*emulator" 2>/dev/null || true

            exit 1
        fi
    else
        echo "  [F4] Unknown screen state:"
        show_screen_state
        echo "  [F4] Attempting to continue anyway..."
    fi

    # Step F5: Dismiss rating popup if present
    echo ""
    echo "  [F5] Checking for popups..."
    UI_CONTENT=$(get_screen_content)
    if echo "$UI_CONTENT" | grep -q "Not now"; then
        echo "  [F5] Rating popup found, dismissing..."
        tap_and_log 540 1400 "Not now"
        sleep 2
    else
        echo "  [F5] No popup to dismiss."
    fi

    # Step F6: Navigate to Traders Sentiment
    echo ""
    echo "  [F6] Opening menu (4-dots)..."
    tap_and_log 980 2300 "4-dots menu"
    sleep 3
    show_screen_state

    echo ""
    echo "  [F7] Opening Traders Sentiment..."
    tap_and_log 190 400 "Traders Sentiment tile"
    sleep 3
    show_screen_state

    echo ""
    echo "  [F8] Opening Hottest markets..."
    tap_and_log 350 850 "Hottest markets tile"
    sleep 3
    show_screen_state

    echo ""
    echo "  [F9] Switching to All tab..."
    tap_and_log 900 2130 "All tab"
    sleep 2
    show_screen_state

    # Step F10: Scroll to top of the list
    echo ""
    echo "  [F10] Scrolling to top..."
    for i in 1 2 3 4 5; do
        adb -s $ADB_DEVICE shell input swipe 540 400 540 1800 300
        sleep 0.5
    done
    sleep 2

    echo "  [Fallback] Navigation completed."
fi

# Step 5: Capture screenshots using ADB
echo ""
echo "[5/6] Capturing screenshots via ADB..."
echo "  This may take 1-2 minutes..."

# Take first screenshot
adb -s $ADB_DEVICE exec-out screencap -p > "$SCREENSHOTS_DIR/screen_00.png"
echo "  Screenshot 00 captured"

# Scroll and capture 50 more screenshots
for i in $(seq -w 1 50); do
    # Scroll down
    adb -s $ADB_DEVICE shell input swipe 540 1400 540 900 400
    sleep 0.8
    # Capture screenshot
    adb -s $ADB_DEVICE exec-out screencap -p > "$SCREENSHOTS_DIR/screen_${i}.png"
    echo "  Screenshot $i captured"
done

# Count screenshots
SCREENSHOT_COUNT=$(ls -1 "$SCREENSHOTS_DIR"/*.png 2>/dev/null | wc -l)
echo "  Total: $SCREENSHOT_COUNT screenshots captured."

if [ "$SCREENSHOT_COUNT" -lt 10 ]; then
    echo "  ERROR: Too few screenshots captured. Something went wrong."
    exit 1
fi

# Note: Steps 6-7 (OCR extraction, CSV transfer) are now handled by main.py
# This script only captures screenshots; data processing is centralized in main.py

# Step 6: Shutdown emulator to free resources
echo ""
echo "[6/6] Shutting down emulator..."
adb -s $ADB_DEVICE emu kill 2>/dev/null || true
sleep 2
pkill -f "cage.*emulator" 2>/dev/null || true
pkill -f "qemu-system" 2>/dev/null || true
echo "  Emulator stopped."

echo ""
echo "=========================================="
echo "Screenshot capture completed at: $(date)"
echo "Screenshots saved to: $SCREENSHOTS_DIR"
echo "Next: main.py will process OCR and update CSVs"
echo "=========================================="
