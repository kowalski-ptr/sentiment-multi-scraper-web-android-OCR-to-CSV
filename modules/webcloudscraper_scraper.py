#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EquityIndividualInvestorSurvey Web Scraper Module
Alternative method to get EquityIndividualInvestorSurvey sentiment data by scraping HTML table
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)

class AAIIWebScraper:
    """
    Scrapes EquityIndividualInvestorSurveysentiment data from the HTML table on sentiment survey page
    """

    def __init__(self):
        self.sentiment_url = "https://url.com/"
        self.session = None

    def _create_session(self):
        """Create a requests session with proper headers"""
        if not self.session:
            self.session = requests.Session()

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            self.session.headers.update(headers)

    def scrape_sentiment_data(self) -> List[Dict]:
        """
        Scrape sentiment data from AAII website HTML table
        Returns list of sentiment entries
        """

        try:
            self._create_session()
            logger.info(f"Scraping sentiment data from: {self.sentiment_url}")

            response = self.session.get(self.sentiment_url, timeout=30)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the sentiment table
            table = soup.find('table', class_='bordered')
            if not table:
                logger.error("Could not find sentiment table with class 'bordered'")
                return []

            logger.info("Found sentiment table, extracting data...")

            # Extract data from table
            sentiment_data = []
            rows = table.find_all('tr')

            for row_idx, row in enumerate(rows):
                cells = row.find_all('td')

                if len(cells) < 4:
                    continue

                # Skip header rows
                if any(cell.get('class') == ['tableSubHd2'] for cell in cells):
                    logger.debug(f"Skipping header row {row_idx}")
                    continue

                # Look for data rows with class 'tableTxt'
                if not any(cell.get('class') == ['tableTxt'] for cell in cells):
                    continue

                try:
                    # Extract text from cells
                    date_text = cells[0].get_text(strip=True)
                    bullish_text = cells[1].get_text(strip=True)
                    neutral_text = cells[2].get_text(strip=True)
                    bearish_text = cells[3].get_text(strip=True)

                    # Parse date (format like "Oct 8")
                    parsed_date = self._parse_date(date_text)
                    if not parsed_date:
                        continue

                    # Parse percentages (format like "45.9%")
                    bullish = self._parse_percentage(bullish_text)
                    neutral = self._parse_percentage(neutral_text)
                    bearish = self._parse_percentage(bearish_text)

                    if bullish is None or neutral is None or bearish is None:
                        continue

                    entry = {
                        "date": parsed_date.strftime("%Y-%m-%d"),
                        "bullish": round(bullish, 1),
                        "neutral": round(neutral, 1),
                        "bearish": round(bearish, 1)
                    }

                    sentiment_data.append(entry)

                    # Log first few entries
                    if len(sentiment_data) <= 5:
                        logger.info(f"Scraped entry {len(sentiment_data)}: {entry}")

                except Exception as e:
                    logger.debug(f"Error parsing row {row_idx}: {e}")
                    continue

            # Sort by date (newest first from web, so reverse for chronological order)
            sentiment_data.sort(key=lambda x: x['date'])

            logger.info(f"Successfully scraped {len(sentiment_data)} sentiment entries")
            return sentiment_data

        except requests.RequestException as e:
            logger.error(f"Error fetching web page: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error scraping sentiment data: {str(e)}")
            return []

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse date from formats like 'Oct 8', 'Oct 1', etc.

        Logic: if the parsed date is in the future (more than 7 days),
        use the previous year (EquityIndividualInvestorSurvey data is published weekly).
        """

        try:
            # Clean up text
            date_text = date_text.strip()

            if not date_text:
                return None

            now = datetime.now()
            current_year = now.year

            # Parse format like "Oct 8"
            if ' ' in date_text:
                try:
                    parsed = datetime.strptime(f"{date_text} {current_year}", "%b %d %Y")

                    # If date is in the future (more than 7 days), use the previous year
                    if parsed > now + timedelta(days=7):
                        parsed = datetime.strptime(f"{date_text} {current_year - 1}", "%b %d %Y")

                    return parsed
                except ValueError:
                    pass

            # Try other formats if needed
            logger.debug(f"Could not parse date: '{date_text}'")
            return None

        except Exception as e:
            logger.debug(f"Date parsing error: {e}")
            return None

    def _parse_percentage(self, percent_text: str) -> Optional[float]:
        """
        Parse percentage from formats like '45.9%', '42.9%', etc.
        """

        try:
            # Clean up text
            percent_text = percent_text.strip().replace('%', '')

            if not percent_text:
                return None

            return float(percent_text)

        except ValueError:
            logger.debug(f"Could not parse percentage: '{percent_text}'")
            return None
        except Exception as e:
            logger.debug(f"Percentage parsing error: {e}")
            return None

    def get_latest_entries(self, limit: int = 10) -> List[Dict]:
        """Get the most recent sentiment entries"""

        data = self.scrape_sentiment_data()
        if not data:
            return []

        # Sort by date descending (newest first)
        data.sort(key=lambda x: x['date'], reverse=True)

        return data[:limit]