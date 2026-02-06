"""
WebScrap Zyte API Scrapy Pipeline - Data Collection Only

This pipeline ONLY saves scraped data to sentiment_history.json.
All data processing (CSV generation) and git operations are handled
centrally by main.py, which is called by run_scraper.sh after
the spider completes.

Architecture (Centralized Git):
    run_scraper.sh
        ├── scrapy crawl sentiment → this pipeline → sentiment_history.json
        └── main.py --source webscrapzyteapi → CSV processing + git push

See main.py for the central data processing and git operations hub.
"""
import json
from datetime import datetime
import logging


class JsonHistoryPipeline:
    """
    Scrapy pipeline that saves sentiment data to JSON history file.

    This pipeline is responsible ONLY for:
    - Collecting scraped items during spider execution
    - Saving them to sentiment_history.json when spider closes

    CSV processing and git operations are handled by main.py (called by run_scraper.sh).
    """
    def __init__(self):
        self.sentiment_file_path = 'sentiment_history.json'
        self.manual_file_path = 'man_history.json'  # Manual fallback for missing historical data
        self.current_scrape_data = []
        self.max_history = 99

    def open_spider(self, spider):
        self.current_scrape_data = []
        self.timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M")

    def process_item(self, item, spider):
        # Calculate sentiment_percent according to the algorithm
        sentiment_percent = 0
        if item['long_percentage'] >= 50:
            sentiment_percent = round(item['long_percentage'] - 50, 1)
        elif item['short_percentage'] >= 50:
            sentiment_percent = round(50 - item['short_percentage'], 1)

        self.current_scrape_data.append({
            'pair': item['pair'],
            'timestamp': self.timestamp,
            'sentiment_percent': sentiment_percent
        })
        return item

    def close_spider(self, spider):
        """
        Called when spider closes. Saves scraped data to JSON file.

        Note: CSV processing and git push are handled by main.py,
        which is called by run_scraper.sh after this spider completes.
        This ensures git operations are centralized in one place.
        """
        try:
            self._save_sentiment_history()
            logging.info(f"Saved {len(self.current_scrape_data)} items to {self.sentiment_file_path}")
            logging.info("CSV processing and git push will be handled by main.py")
        except Exception as e:
            logging.error(f"Error in pipeline: {e}")

    def _save_sentiment_history(self):
        try:
            # Load existing history
            try:
                with open(self.sentiment_file_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                history = []

            # Add new data and limit history length
            history = self.current_scrape_data + history
            if len(history) > self.max_history:
                history = history[:self.max_history]

            # Save updated history
            with open(self.sentiment_file_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logging.error(f"Error saving sentiment history: {e}")
