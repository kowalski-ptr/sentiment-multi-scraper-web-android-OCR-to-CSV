#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EquityIndividualInvestorSurvey Sentiment Manager - Final Implementation
Manages EquityIndividualInvestorSurvey sentiment data using local Excel parsing + HTML scraping for updates
"""

import pandas as pd
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Import our HTML scraper
try:
    from .aaii_web_scraper import AAIIWebScraper
except ImportError:
    try:
        from modules.aaii_web_scraper import AAIIWebScraper
    except ImportError:
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent))
        from aaii_web_scraper import AAIIWebScraper

logger = logging.getLogger(__name__)

class AAIISentimentManager:
    """
    Final EquityIndividualInvestorSurvey Sentiment data manager with simplified workflow:
    1. Check if local Excel and JSON exist
    2. If Excel exists but no JSON -> parse Excel to create JSON
    3. If JSON exists -> scrape HTML for updates and merge
    """

    def __init__(self, base_data_dir: str = "data-works"):
        self.base_data_dir = Path(base_data_dir)
        self.aaii_dir = self.base_data_dir / "aaii"
        self.local_excel_file = self.aaii_dir / "aaii-sentiment.xls"
        self.json_file = self.aaii_dir / "aaii-sentiment-data.json"

        # Initialize web scraper
        self.web_scraper = AAIIWebScraper()

        # Ensure directories exist
        self.aaii_dir.mkdir(parents=True, exist_ok=True)

    def check_data_status(self) -> Dict[str, bool]:
        """Check what data files are available and determine action needed"""
        status = {
            "local_excel_exists": self.local_excel_file.exists(),
            "json_exists": self.json_file.exists(),
            "action_needed": "none"
        }

        if status["local_excel_exists"] and not status["json_exists"]:
            status["action_needed"] = "initialize_from_excel"
        elif status["json_exists"]:
            status["action_needed"] = "update_from_web"
        elif not status["local_excel_exists"] and not status["json_exists"]:
            status["action_needed"] = "no_data_available"

        logger.info(f"Data status: {status}")
        return status

    def initialize_from_local_excel(self) -> bool:
        """Parse local Excel file and create initial JSON data"""

        if not self.local_excel_file.exists():
            logger.error(f"Local Excel file not found: {self.local_excel_file}")
            return False

        try:
            logger.info(f"Initializing AAII data from local Excel: {self.local_excel_file}")

            # Read Excel file
            df = pd.read_excel(self.local_excel_file, engine='xlrd')
            logger.info(f"Loaded Excel file: {df.shape[0]} rows, {df.shape[1]} columns")

            # Extract sentiment data using same logic as before
            data_entries = self._extract_sentiment_from_excel(df)

            if not data_entries:
                logger.error("No valid sentiment data found in Excel file")
                return False

            # Create JSON structure
            json_output = {
                "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "local_excel_initialization",
                "total_records": len(data_entries),
                "data": data_entries
            }

            # Write JSON file
            self._write_json_data(json_output)

            logger.info(f"Successfully initialized {len(data_entries)} records from Excel")
            logger.info(f"Historical date range: {data_entries[0]['date']} to {data_entries[-1]['date']}")

            return True

        except Exception as e:
            logger.error(f"Error initializing from Excel: {str(e)}")
            return False

    def update_from_web_scraping(self) -> bool:
        """Scrape latest data from web and merge with existing JSON - WITH 7-DAY INTELLIGENT CACHING"""

        if not self.json_file.exists():
            logger.error("JSON file does not exist. Cannot perform web update.")
            return False

        try:
            logger.info("Starting web scraping update process")

            # Read current JSON data
            current_data = self._read_json_data()
            if not current_data:
                return False

            # Find latest date in current data
            current_entries = current_data['data']
            latest_date = max(entry['date'] for entry in current_entries)
            latest_date_obj = datetime.strptime(latest_date, "%Y-%m-%d")

            logger.info(f"Latest date in current data: {latest_date}")

            # INTELLIGENT 7-DAY CACHING - Check if we should scrape
            days_since_last_update = (datetime.now() - latest_date_obj).days
            logger.info(f"Days since last AAII update: {days_since_last_update}")

            # Check if we have metadata about last scraping attempt
            last_scraping_attempt = current_data.get('last_scraping_attempt')
            last_scraping_date = None

            if last_scraping_attempt:
                try:
                    last_scraping_date = datetime.strptime(last_scraping_attempt, "%Y-%m-%dT%H:%M:%SZ")
                    hours_since_scraping = (datetime.now() - last_scraping_date).total_seconds() / 3600
                    logger.debug(f"Hours since last scraping attempt: {hours_since_scraping:.1f}")
                except:
                    pass

            # DECISION LOGIC: Should we scrape?
            should_scrape = False
            scraping_reason = ""

            if days_since_last_update >= 7:
                # It's been 7+ days, definitely should scrape
                should_scrape = True
                scraping_reason = f"7+ days since last update ({days_since_last_update} days)"
            elif days_since_last_update >= 6 and (not last_scraping_date or (datetime.now() - last_scraping_date).total_seconds() > 3600):
                # It's been 6+ days and we haven't scraped in the last hour (allow checking for delayed updates)
                should_scrape = True
                scraping_reason = f"6+ days since last update, checking for delayed data ({days_since_last_update} days)"
            elif not last_scraping_date:
                # No record of previous scraping attempt
                should_scrape = True
                scraping_reason = "No previous scraping attempt recorded"
            else:
                # Too recent, skip scraping
                should_scrape = False
                scraping_reason = f"Only {days_since_last_update} days since last update (< 6 days threshold)"

            if not should_scrape:
                logger.info(f"⏭️ Skipping web scraping: {scraping_reason}")
                logger.info("EquityIndividualInvestorSurvey data is likely up-to-date (publishes weekly)")
                return True

            # Proceed with scraping
            logger.info(f"🌐 Proceeding with web scraping: {scraping_reason}")
            web_entries = self.web_scraper.scrape_sentiment_data()

            if not web_entries:
                logger.warning("No data scraped from web")
                return False

            logger.info(f"Scraped {len(web_entries)} entries from web")

            # Filter for entries newer than our latest date
            new_entries = [
                entry for entry in web_entries
                if entry['date'] > latest_date
            ]

            if not new_entries:
                logger.info("No new data found - data is up to date")

                # Still update metadata to record the scraping attempt
                current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                updated_json = current_data.copy()
                updated_json["last_scraping_attempt"] = current_timestamp
                updated_json["scraping_reason"] = scraping_reason
                updated_json["last_scraping_result"] = "no_new_data"

                # Write updated metadata
                self._write_json_data(updated_json)
                logger.debug("Updated scraping attempt metadata")

                return True

            logger.info(f"Found {len(new_entries)} new entries to merge:")
            for entry in new_entries:
                logger.info(f"  New: {entry['date']} - Bullish: {entry['bullish']}%, Neutral: {entry['neutral']}%, Bearish: {entry['bearish']}%")

            # Merge new data with existing data
            merged_data = current_entries + new_entries
            merged_data.sort(key=lambda x: x['date'])  # Ensure chronological order

            # Update JSON structure with scraping metadata
            current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            updated_json = {
                "last_updated": current_timestamp,
                "last_scraping_attempt": current_timestamp,
                "source": "web_scraping_update",
                "total_records": len(merged_data),
                "new_entries_added": len(new_entries),
                "scraping_reason": scraping_reason,
                "data": merged_data
            }

            # Write updated JSON
            self._write_json_data(updated_json)

            logger.info(f"Successfully merged {len(new_entries)} new entries")
            logger.info(f"Updated date range: {merged_data[0]['date']} to {merged_data[-1]['date']}")
            logger.info(f"Total records: {len(merged_data)}")

            return True

        except Exception as e:
            logger.error(f"Error during web update: {str(e)}")
            return False

    def _extract_sentiment_from_excel(self, df: pd.DataFrame) -> List[Dict]:
        """Extract sentiment data from Excel DataFrame (same logic as before)"""

        # Column mappings based on previous analysis
        date_col = 'Unnamed: 0'
        bullish_col = 'Unnamed: 1'
        neutral_col = 'Unnamed: 2'
        bearish_col = 'Text in header of bearish col.'

        valid_data = []

        for idx, row in df.iterrows():
            # Skip header rows, start from row 6 where actual data begins
            if idx < 6:
                continue

            date_val = row[date_col]
            bullish_val = row[bullish_col]
            neutral_val = row[neutral_col]
            bearish_val = row[bearish_col]

            # Check if we have valid sentiment data
            if (pd.notna(date_val) and isinstance(date_val, datetime) and
                pd.notna(bullish_val) and isinstance(bullish_val, (int, float)) and
                pd.notna(neutral_val) and isinstance(neutral_val, (int, float)) and
                pd.notna(bearish_val) and isinstance(bearish_val, (int, float))):

                data_entry = {
                    "date": date_val.strftime("%Y-%m-%d"),
                    "bullish": round(float(bullish_val * 100), 1),
                    "neutral": round(float(neutral_val * 100), 1),
                    "bearish": round(float(bearish_val * 100), 1)
                }

                valid_data.append(data_entry)

        # Sort by date
        valid_data.sort(key=lambda x: x['date'])

        logger.info(f"Extracted {len(valid_data)} valid sentiment entries from Excel")
        return valid_data

    def _read_json_data(self) -> Optional[Dict]:
        """Read existing JSON data"""
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading JSON: {str(e)}")
            return None

    def _write_json_data(self, data: Dict) -> bool:
        """Write JSON data to file"""
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"JSON data written to: {self.json_file}")
            return True
        except Exception as e:
            logger.error(f"Error writing JSON: {str(e)}")
            return False

    def run_data_management(self) -> bool:
        """Main method - determines what action to take and executes it"""

        logger.info("Starting EquityIndividualInvestorSurvey data management")

        status = self.check_data_status()

        if status["action_needed"] == "no_data_available":
            logger.warning("No local Excel file or JSON data found")
            logger.info("Please place 'aaii-sentiment.xls' file in ./data-works/aaii/ directory to initialize")
            return False

        elif status["action_needed"] == "initialize_from_excel":
            logger.info("Initializing sentiment data from local Excel file")
            return self.initialize_from_local_excel()

        elif status["action_needed"] == "update_from_web":
            logger.info("Updating sentiment data from web scraping")
            return self.update_from_web_scraping()

        else:
            logger.info("No action needed")
            return True

    def get_latest_sentiment(self) -> Optional[Dict]:
        """Get the most recent sentiment values"""

        data = self._read_json_data()
        if not data or not data.get('data'):
            return None

        latest_entry = data['data'][-1]

        return {
            "date": latest_entry['date'],
            "bullish": latest_entry['bullish'],
            "neutral": latest_entry['neutral'],
            "bearish": latest_entry['bearish'],
            "last_updated": data.get('last_updated'),
            "total_records": data.get('total_records', 0)
        }

    def get_sentiment_statistics(self) -> Optional[Dict]:
        """Get comprehensive statistics about the sentiment data"""

        data = self._read_json_data()
        if not data or not data.get('data'):
            return None

        entries = data['data']

        # Calculate some basic statistics
        recent_entries = entries[-10:] if len(entries) >= 10 else entries
        avg_bullish = sum(e['bullish'] for e in recent_entries) / len(recent_entries)
        avg_neutral = sum(e['neutral'] for e in recent_entries) / len(recent_entries)
        avg_bearish = sum(e['bearish'] for e in recent_entries) / len(recent_entries)

        return {
            "total_records": len(entries),
            "date_range": {
                "start": entries[0]['date'],
                "end": entries[-1]['date']
            },
            "last_updated": data.get('last_updated'),
            "source": data.get('source'),
            "latest_sentiment": {
                "date": entries[-1]['date'],
                "bullish": entries[-1]['bullish'],
                "neutral": entries[-1]['neutral'],
                "bearish": entries[-1]['bearish']
            },
            "recent_averages_10_weeks": {
                "bullish": round(avg_bullish, 1),
                "neutral": round(avg_neutral, 1),
                "bearish": round(avg_bearish, 1)
            }
        }