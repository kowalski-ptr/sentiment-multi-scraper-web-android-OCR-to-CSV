"""
============================================================================
MAIN.PY - CENTRAL DATA PROCESSING AND GIT OPERATIONS HUB
============================================================================

This is the SINGLE source of truth for all sentiment data processing
and git operations in the SentimentCollection project.

Architecture (Centralized Processing):

    run_scraper.sh (entry point)
        │
        ├── Data Collection (one of):
        │     ├── collect_sentiment.sh → screenshots (Android App)
        │     └── scrapy crawl sentiment → JSON (WebScrap Zyte API)
        │
        └── THIS FILE (main.py) - always called after collection:
              ├── Data Processing:
              │     ├── AndroidApp: extract_sentiment.py → transfer_ocr_to_csv.py
              │     └── WebScrapZyteAPI: parse sentiment_history.json → write CSVs
              │
              └── Git Operations (CRITICAL - triggers GitHub Actions):
                    ├── git_handler.push_changes() → commit & push to origin
                    └── GitPublisher.publish() → push to public repo

IMPORTANT: Git operations are CRITICAL for the GitHub Actions workflow:
    1. This script pushes changes to the repository
    2. GitHub Actions (check_data.yaml) triggers on push to data/**
    3. Validation scripts run and create a PR
    4. upload_data.yaml processes the PR and uploads to TradingView

Without the git push from this file, no data reaches production!

Usage:
    python main.py --source androidapp       # Process Android app screenshots
    python main.py --source webscrapzyteapi  # Process WebScrap Zyte API JSON data
    python main.py --no-git                  # Skip git operations (for testing)
    python main.py --no-publish              # Skip public repo publish

Called by: run_scraper.sh (the universal orchestrator)
"""

import json
import csv
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import os
import argparse
import logging
import sys

# =============================================================================
# CRITICAL IMPORTS - Git operations are essential for the pipeline
# =============================================================================
# GitHandler: Handles git add, commit, push to origin repository
# GitPublisher: Clones public repo, copies CSVs, commits and pushes
# These are the ONLY places in the codebase where git operations happen.
# =============================================================================
from scripts.git_handler import GitHandler, GitPublisher
from config import PUBLIC_REPO_URL, USE_ANDROID_APP


class SentimentProcessor:
    def __init__(self):
        self.data_by_pair = {}

    def parse_json(self, json_file: str) -> None:
        """Parse JSON file and organize data by trading pairs."""
        logging.info(f"Parsing JSON file: {json_file}")

        try:
            with open(json_file, 'r') as file:
                data = json.load(file)

            logging.info(f"Loaded {len(data)} records from JSON file")

            for entry in data:
                timestamp = entry.get('timestamp')
                pair = entry.get('pair')

                # Check if entry has nested structure (for older entries)
                if 'data' in entry and isinstance(entry['data'], list):
                    logging.info(f"Found nested data structure for timestamp {timestamp}")
                    for item in entry['data']:
                        nested_pair = item.get('pair')
                        nested_sentiment = float(item.get('sentiment_percent', 0))

                        if nested_pair:
                            if nested_pair not in self.data_by_pair:
                                self.data_by_pair[nested_pair] = {}

                            try:
                                dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M')
                                formatted_timestamp = dt.strftime('%Y%m%dT')

                                if formatted_timestamp in self.data_by_pair[nested_pair]:
                                    existing_sentiment = self.data_by_pair[nested_pair][formatted_timestamp]
                                    self.data_by_pair[nested_pair][formatted_timestamp] = round((existing_sentiment + nested_sentiment) / 2, 1)
                                else:
                                    self.data_by_pair[nested_pair][formatted_timestamp] = round(nested_sentiment, 1)
                            except ValueError as e:
                                logging.error(f"Error processing nested timestamp for {nested_pair}: {e}")
                    continue

                # Standard structure
                sentiment = float(entry.get('sentiment_percent', 0))

                if not pair:
                    logging.warning(f"Missing pair in entry: {entry}")
                    continue

                if pair not in self.data_by_pair:
                    self.data_by_pair[pair] = {}

                try:
                    dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M')
                    formatted_timestamp = dt.strftime('%Y%m%dT')

                    if formatted_timestamp in self.data_by_pair[pair]:
                        existing_sentiment = self.data_by_pair[pair][formatted_timestamp]
                        self.data_by_pair[pair][formatted_timestamp] = round((existing_sentiment + sentiment) / 2, 1)
                    else:
                        self.data_by_pair[pair][formatted_timestamp] = round(sentiment, 1)
                except ValueError as e:
                    logging.error(f"Error processing timestamp for {pair}: {e}")
                    continue

            logging.info(f"Processed data for {len(self.data_by_pair)} trading pairs")
            for pair, timestamps in self.data_by_pair.items():
                logging.info(f"Pair {pair}: {len(timestamps)} timestamps")

        except Exception as e:
            logging.error(f"Error parsing JSON file: {e}")
            raise

    def process_pair(self, pair: str) -> List[Tuple[str, float]]:
        if pair not in self.data_by_pair:
            return []
        return sorted(self.data_by_pair[pair].items())

    def write_csv(self, pair: str, output_dir: str) -> None:
        """
        Write sentiment data to CSV file, preserving existing data and adding new records
        (both newer and older timestamps that don't exist in the CSV).
        Records are sorted by timestamp from oldest to newest.
        """
        output_filename = f"{pair.upper()}SENTIMENT.csv"
        output_file = os.path.join(output_dir, output_filename)

        logging.info(f"Writing CSV for {pair} to {output_file}")

        # Read existing data if file exists
        existing_data = {}
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', newline='') as file:
                    reader = csv.reader(file, delimiter=',')
                    for row in reader:
                        if row and len(row) >= 6:  # Ensure row has enough columns
                            timestamp = row[0]
                            sentiment = float(row[1])
                            existing_data[timestamp] = (sentiment, row[2], row[3], row[4], row[5])
                logging.info(f"Read {len(existing_data)} existing records from {output_filename}")
            except Exception as e:
                logging.error(f"Error reading existing CSV file {output_filename}: {e}")
                # Continue with empty existing_data
        else:
            logging.info(f"No existing file found for {pair}, will create new file")

        # Get new data from JSON
        processed_data = self.process_pair(pair)
        logging.info(f"Found {len(processed_data)} records in JSON for {pair}")

        # Count new records for logging
        new_records_count = 0

        # Merge existing and new data
        merged_data = existing_data.copy()
        for timestamp, sentiment in processed_data:
            if timestamp not in merged_data:
                # New record - add it with all columns having the same sentiment value
                merged_data[timestamp] = (
                    sentiment,
                    f"{sentiment:.1f}",
                    f"{sentiment:.1f}",
                    f"{sentiment:.1f}",
                    "0"
                )
                new_records_count += 1

        # Sort data by timestamp (oldest to newest)
        sorted_data = sorted(merged_data.items())

        # Write merged data to file
        try:
            with open(output_file, 'w', newline='') as file:
                writer = csv.writer(file, delimiter=',')
                for timestamp, values in sorted_data:
                    sentiment, col2, col3, col4, col5 = values
                    row = [
                        timestamp,
                        f"{sentiment:.1f}",
                        col2,
                        col3,
                        col4,
                        col5
                    ]
                    writer.writerow(row)

            if new_records_count > 0:
                logging.info(f"Added {new_records_count} new records to {output_filename}")
            logging.info(f"Updated CSV file for {pair} with {len(sorted_data)} total records")
        except Exception as e:
            logging.error(f"Error writing to CSV file {output_filename}: {e}")
            raise


def resolve_source(args_source):
    """Determine data source: 'androidapp' or 'webscrapzyteapi'. Reads USE_ANDROID_APP from config if --source not given."""
    if args_source:
        return args_source
    return 'androidapp' if USE_ANDROID_APP else 'webscrapzyteapi'


def run_androidapp_pipeline(output_dir, debug: bool = False):
    """Run the Android App OCR pipeline: extract_sentiment.py → transfer_ocr_to_csv.py"""
    project_dir = Path(__file__).parent

    logging.info("Running Android App OCR pipeline...")

    logging.info("Step 1: Extracting sentiment from screenshots (OCR)...")
    cmd = [sys.executable, str(project_dir / 'extract_sentiment.py')]
    if debug:
        cmd.append('--debug')
    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logging.error(f"extract_sentiment.py failed:\n{result.stderr}")
        raise RuntimeError("OCR extraction failed")
    logging.info(result.stdout.strip() if result.stdout else "OCR extraction done")

    logging.info("Step 2: Transferring OCR data to CSV files...")
    result = subprocess.run(
        [sys.executable, str(project_dir / 'transfer_ocr_to_csv.py')],
        cwd=str(project_dir),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logging.error(f"transfer_ocr_to_csv.py failed:\n{result.stderr}")
        raise RuntimeError("CSV transfer failed")
    logging.info(result.stdout.strip() if result.stdout else "CSV transfer done")


def main():
    parser = argparse.ArgumentParser(description='Process sentiment history and update CSV files')
    parser.add_argument('--source', type=str, choices=['androidapp', 'webscrapzyteapi'], default=None,
                      help='Data source: androidapp (Android app OCR) or webscrapzyteapi (Zyte API). '
                           'If not specified, reads USE_ANDROID_APP from .env')
    parser.add_argument('--json-file', type=str, default=None,
                      help='Path to the JSON file (default: webscrap_zyteapi/sentiment_history.json)')
    parser.add_argument('--output-dir', type=str, default='data',
                      help='Output directory for CSV files (default: data)')
    parser.add_argument('--no-git', action='store_true',
                      help='Skip git operations')
    parser.add_argument('--no-publish', action='store_true',
                      help='Skip publishing to public repository')
    parser.add_argument('--public-repo', type=str,
                      default=PUBLIC_REPO_URL,
                      help='URL of the public repository')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug logging')

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    source = resolve_source(args.source)
    logging.info(f"Data source: {source}")

    try:
        Path(args.output_dir).mkdir(exist_ok=True)

        if source == 'androidapp':
            run_androidapp_pipeline(args.output_dir, debug=args.debug)
        else:
            # WebScrap Zyte API JSON path
            if args.json_file is None:
                json_file = os.path.join(Path(__file__).parent, 'webscrap_zyteapi', 'sentiment_history.json')
            else:
                json_file = args.json_file

            processor = SentimentProcessor()
            logging.info(f"Processing JSON file: {json_file}")
            processor.parse_json(json_file)

            for pair in processor.data_by_pair:
                processor.write_csv(pair, args.output_dir)
                logging.info(f"Processed {pair} successfully")

        # =====================================================================
        # CRITICAL SECTION: GIT OPERATIONS
        # =====================================================================
        # These git operations are ESSENTIAL for the pipeline to work:
        #   1. push_changes() commits and pushes to origin
        #   2. This triggers GitHub Actions (check_data.yaml on push to data/**)
        #   3. GitHub Actions validates data and creates PR
        #   4. PR triggers upload_data.yaml which sends data to TradingView
        #
        # If these operations fail, data will NOT reach production!
        # =====================================================================

        # Step 1: Push to origin repository (triggers GitHub Actions)
        if not args.no_git:
            logging.info("=" * 60)
            logging.info("GIT PUSH TO ORIGIN (triggers GitHub Actions workflow)")
            logging.info("=" * 60)
            repo_path = Path(__file__).parent
            git_handler = GitHandler(repo_path)
            if not git_handler.push_changes():
                logging.error("CRITICAL: Failed to push changes to repository!")
                logging.error("GitHub Actions workflow will NOT be triggered!")
                sys.exit(1)
            logging.info("Successfully pushed to origin - GitHub Actions will process")

        # Step 2: Publish to public repository (backup/alternative distribution)
        if not args.no_publish:
            logging.info("=" * 60)
            logging.info("PUBLISHING TO PUBLIC REPOSITORY")
            logging.info("=" * 60)
            publisher = GitPublisher(
                source_dir=args.output_dir,
                public_repo_url=args.public_repo,
                target_dir='data'
            )
            if not publisher.publish():
                logging.error("Failed to publish CSV files to public repository")
                sys.exit(1)
            logging.info("Successfully published CSV files to public repository")

    except Exception as e:
        logging.error(f"Error processing data: {str(e)}")
        raise


if __name__ == "__main__":
    main()
