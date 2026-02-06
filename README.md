# Sentiment Data Collection Framework

A modular Python/Bash framework for collecting financial market sentiment data from multiple sources and publishing it via GitHub Actions (CI/CD) for use in trading system - TradingView.

## Background & Evolution

This framework was built incrementally, evolving organically based on current needs. It started with a single goal: feed custom sentiment data into TradingView charts through their Pine Seeds program.

Results are visible as two public indicators, which you can find in TradingView under the names:
- Retail Sentiment CFD Index Commodity Crypto Fear/Greed
- Retail Forex Sentiment Fear/Greed CurrencyPairs

**How it evolved:**

1. **First attempt - Web API scraping**: The initial version used Scrapy with Zyte proxy to scrape retail trader sentiment from a broker's public API. It worked, but the data proved too volatile for meaningful analysis.

2. **The Android app pivot**: After realizing that a mobile trading app provided more stable and reliable sentiment readings, I built an entirely new module. This required Android emulator automation (Maestro/ADB), screenshot capture, and OCR text extraction - a completely different technical challenge. Once this was working, the original web scraper became a legacy module (still included, toggled via `.env`).

3. **Adding more data sources**: Over time, I integrated additional sentiment indicators:
   - An equity market fear & greed index (cloud-based scraping with anti-bot bypass)
   - A weekly individual investor sentiment survey (BeautifulSoup + Excel parsing)
   - A cryptocurrency fear & greed index (simple JSON API)

4. **Handling different update frequencies**: TradingView processes data once daily, but sources publish at different intervals - some daily, some weekly. This drove the modular architecture with two separate bash entry points: one for frequently-updated data, another for weekly sources.

The result is admittedly not the cleanest architecture - it reflects iterative development where requirements emerged gradually and ties together web scraping, mobile automation, OCR, and CI/CD pipelines.

## Features

- **Multiple data collection methods:**
  - **Android App (OCR)**: Uses Android emulator with Maestro/ADB automation to capture screenshots from trading apps, then extracts sentiment data via Tesseract OCR
  - **Cloud Scraper**: Bypasses anti-bot protection to collect equity market fear & greed index data with automatic retry and caching
  - **Web Scraper (BeautifulSoup)**: Parses weekly individual investor sentiment survey data from HTML, with intelligent date handling for year boundaries
  - **JSON API Collector**: Fetches cryptocurrency fear & greed index from public REST endpoints
  - **Web API (Scrapy)**: Legacy module - scrapes retail trader sentiment via Zyte API proxy (kept for reference, disabled by default)

- **Centralized processing**: All data processing and git operations are handled by a single `main.py` hub
- **CI/CD ready**: Includes GitHub Actions workflows for data validation and TradingView upload
- **Automated publishing**: Pushes CSV data to GitHub, which triggers CI/CD pipeline
- **Email notifications**: Optional failure alerts via Gmail

## Architecture

```
run_scraper.sh (entry point)
    │
    ├── Data Collection (based on USE_ANDROID_APP in .env):
    │     ├── android_app → collect_sentiment.sh → screenshots/
    │     │                 └── Maestro/ADB automation
    │     └── webscrap_api → scrapy crawl sentiment → JSON
    │
    └── main.py (central hub):
          ├── AndroidApp: extract_sentiment.py (OCR) → transfer_ocr_to_csv.py
          ├── WebScrapZyteAPI: parse JSON → write CSVs to data/
          └── Git: push to origin + publish to public repo
```

## Quick Start

### 1. Clone and Configure

```bash
git clone <your-repo-url>
cd sentiment-data-collection

# Copy example config and fill in your values
cp .env.example .env
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt

# For Android app automation (optional):
# - Install Android SDK with emulator
# - Install Maestro: curl -Ls "https://get.maestro.mobile.dev" | bash
# - Install Tesseract OCR
```

### 3. Run

```bash
# Production mode
./run_scraper.sh

# Test mode (no git operations)
./run_scraper.sh --dry-run

# Debug mode (save raw OCR text)
./run_scraper.sh --debug
```

## Configuration

Edit `.env` file:

```bash
# API Keys
ZYTE_API_KEY=your_zyte_api_key_here

# Git Publishing
PUBLIC_REPO_URL=git@github.com:your_username/your_repo.git

# Email Notifications (optional)
EMAIL_SENDER=your_email@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_RECIPIENT=recipient@example.com

# Data Source Selection
# true = Android app (OCR), false = Web API (Scrapy)
USE_ANDROID_APP=true
```

## Customization

### Adapting for Different Data Sources

#### For Android App Scraping:

1. **Maestro flows**: Edit `maestro/navigate_to_sentiment.yaml`
   - Change `appId` to your target app's package name
   - Adjust tap coordinates for your app's UI layout
   - Modify text elements to match your app's screens

2. **OCR extraction**: Edit `extract_sentiment.py`
   - Update `KNOWN_INSTRUMENTS` set with valid symbols
   - Modify `parse_sentiment_data()` regex patterns for your app's text format
   - Add OCR corrections in `OCR_CORRECTIONS` dict

3. **CSV mapping**: Edit `transfer_ocr_to_csv.py`
   - Update symbol mappings to match your data format

#### For Web API Scraping:

1. **Spider**: Edit `webscrap_zyteapi/webscrap_zyteapi/spiders/sentiment_spider.py`
   - Change `allowed_domains` and `start_urls` to your target API
   - Modify `parse()` method to handle your API's response format
   - Update request headers in `start_requests()` as needed

2. **Settings**: Edit `webscrap_zyteapi/webscrap_zyteapi/settings.py`
   - Adjust rate limiting (`DOWNLOAD_DELAY`, `CONCURRENT_REQUESTS`)
   - Configure Zyte API if needed

## Important Notes

### Linux/Wayland Environment

This project uses **Cage** (a Wayland compositor) to run the Android emulator in headless mode on Linux with Wayland. If you're using a different environment:

- **Linux X11**: You may be able to run the emulator directly without Cage
- **macOS/Windows**: Remove the `cage --` prefix from emulator commands in `collect_sentiment.sh`
- **Headless server**: You may need Xvfb or similar virtual display

The relevant line in `collect_sentiment.sh`:
```bash
cage -- ~/Android/Sdk/emulator/emulator -avd "$AVD_NAME" ...
```

### Adapting to Your Data Sources

The URLs in this repository are **placeholders** (e.g., `api.example.com`). To use this framework with your own data sources, you need to:

1. **Replace placeholder URLs** with your actual endpoints
2. **Adapt the parsing logic** to match your target's HTML structure, JSON schema, or app UI

> **Important:** This code is NOT a universal scraper. The parsing functions are tailored to specific website structures and app layouts. Simply changing the URL will not work - you must also modify the parsing code (regex patterns, CSS selectors, XPath queries, screen coordinates, etc.) to match your target source.

| File | What to Change |
|------|----------------|
| `webscrap_zyteapi/.../sentiment_spider.py` | `allowed_domains`, `start_urls`, request headers, `parse()` method |
| `maestro/navigate_to_sentiment.yaml` | `appId`, tap coordinates, text element identifiers |
| `collect_sentiment.sh` | App package name, screen coordinates in ADB fallback |
| `extract_sentiment.py` | `KNOWN_INSTRUMENTS`, `parse_sentiment_data()` regex patterns |
| `webendpoint_json_data.py` | API URLs, JSON field names in parsing functions |
| `modules/webendpoint_scraper.py` | `base_url`, HTML parsing selectors |

## Project Structure

```
├── run_scraper.sh              # Main entry point
├── main.py                     # Central processing hub
├── collect_sentiment.sh        # Android emulator automation
├── extract_sentiment.py        # OCR extraction from screenshots
├── transfer_ocr_to_csv.py      # OCR data to CSV conversion
├── config/                     # Centralized configuration
│   └── __init__.py
├── webscrap_zyteapi/           # Scrapy project for web API
│   └── webscrap_zyteapi/
│       ├── spiders/
│       │   └── sentiment_spider.py
│       ├── settings.py
│       ├── pipelines.py
│       └── middlewares.py
├── maestro/                    # Maestro flow definitions
│   └── navigate_to_sentiment.yaml
├── scripts/                    # Utility scripts
│   ├── git_handler.py
│   └── email_notifier.py
├── modules/                    # Additional data source modules
├── scheduling/                 # Cron scheduling (install/uninstall + wrappers)
├── _github_ActionModule/       # GitHub Actions (rename to .github to enable)
│   └── workflows/
│       ├── check_data.yaml     # Data validation workflow
│       └── upload_data.yaml    # TradingView upload workflow
├── data/                       # Output CSV files
├── screenshots/                # Captured screenshots (Android path)
└── ocr-data/                   # OCR intermediate data
```

## Output Format

CSV files are generated in `data/` directory with format:
```
timestamp,sentiment,open,high,low,volume
20250204T,52.3,52.3,52.3,52.3,0
```

Where `sentiment` represents the long percentage (% of traders buying).

## Scheduling (Cron)

Both scripts can be scheduled via cron (cronie) on Linux. All times use **CET/CEST** (automatic DST switch via `CRON_TZ=Europe/Warsaw`).

| Script | Schedule | Control |
|--------|----------|---------|
| `run_webendpoint.sh` | Mon, Wed, Fri at 12:00 CET | Always active |
| `run_scraper.sh` | Mon-Fri at 14:00 CET | Toggle via `SCHEDULE_RUN_SCRAPER` in `.env` |

### Setup

```bash
# Prerequisite: install cronie (Fedora)
sudo dnf install cronie
sudo systemctl enable --now crond

# Preview what will be installed
./scheduling/install_cron.sh --check

# Install cron jobs
./scheduling/install_cron.sh

# Verify
crontab -l
```

### Enable automatic run_scraper.sh

By default `run_scraper.sh` is manual-only. To enable scheduled execution, set in `.env`:

```bash
SCHEDULE_RUN_SCRAPER=true
```

The cron job fires Mon-Fri at 14:00 CET but only executes when this variable is `true`.

### Remove cron jobs

```bash
./scheduling/uninstall_cron.sh
```

### Logs

Scheduled runs write logs to `logs/` with prefixed filenames (max 11 per script):
- `cron_webendpoint_YYYYMMDD_HHMMSS.log`
- `cron_run_scraper_YYYYMMDD_HHMMSS.log`

## Conda Environments

The project uses conda environments (configurable in `run_scraper.sh`):
- `android` - For Android app pipeline (OCR, image processing)
- `webscrap` - For web scraping pipeline

Adjust `CONDA_ENV_ANDROID` and `CONDA_ENV_WEBSCRAP` variables as needed.

## CI/CD Integration

This project includes **GitHub Actions workflows** for automated data validation and publishing. The workflows are located in `_github_ActionModule/` (renamed from `.github/` to prevent execution in this template repo).

### Enabling CI/CD

To enable CI/CD in your repository:

```bash
mv _github_ActionModule .github
```

### Workflows

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `check_data.yaml` | Push to `data/` or `symbol_info/` | Validates CSV data format and creates a PR |
| `upload_data.yaml` | PR opened | Uploads validated data to TradingView |

### Required Secrets

Add these secrets in your GitHub repository settings (`Settings → Secrets → Actions`):

- `ACTION_TOKEN` - GitHub Personal Access Token with repo permissions

### TradingView Pine Seeds

These workflows are designed for [TradingView Pine Seeds](https://www.tradingview.com/pine-seeds-docs/) integration. The pipeline:
1. Collects sentiment data → writes to `data/*.csv`
2. Git push triggers `check_data.yaml` → validates format
3. Validation creates PR → triggers `upload_data.yaml`
4. Data appears in TradingView as custom data series

## License

MIT License - feel free to use and modify for your own projects.

## Contributing

Contributions welcome! Please open an issue or pull request.
