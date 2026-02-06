import scrapy
import logging
import json
import base64
import schedule
import time
import threading
import sys
from pathlib import Path
from ..items import SentimentItem
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TimeoutError

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.email_notifier import EmailNotifier


class SentimentSpider(scrapy.Spider):
    name = 'sentiment'
    # NOTE: Replace these with your actual API domains
    allowed_domains = ['example-api.com', 'api.example.com']
    start_urls = ['https://api.example.com/woc/getcurrent.aspx']

    # Static counters for the entire spider
    success_count = 0
    warning_count = 0
    error_count = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_notifier = EmailNotifier()

        # Configure custom log handler
        logging.basicConfig(level=logging.WARNING)
        handler = logging.StreamHandler()
        handler.setLevel(logging.WARNING)
        handler.addFilter(self.log_filter)
        logging.getLogger().addHandler(handler)

        # Start thread for weekly report scheduling
        self.schedule_weekly_report()

    def log_filter(self, record):
        if record.levelno == logging.WARNING:
            self.warning_count += 1
        elif record.levelno == logging.ERROR:
            self.error_count += 1

        if record.levelno in [logging.WARNING, logging.ERROR]:
            log_message = self.format_log_message(record)
            self.email_notifier.send_email(
                subject=f"Log {record.levelname} in Sentiment Spider",
                body=log_message
            )
        return True

    def format_log_message(self, record):
        return (
            f"Level: {record.levelname}\n"
            f"Message: {record.getMessage()}\n"
            f"Module: {record.module}\n"
            f"Line: {record.lineno}"
        )

    def schedule_weekly_report(self):
        def send_weekly_report():
            report_body = (
                f"Weekly Sentiment Spider Report:\n"
                f"Successes: {self.success_count}\n"
                f"Warnings: {self.warning_count}\n"
                f"Errors: {self.error_count}"
            )
            self.email_notifier.send_email(
                subject="Weekly Sentiment Spider Summary",
                body=report_body
            )
            # Reset counters after sending report
            self.success_count = 0
            self.warning_count = 0
            self.error_count = 0

        def run_schedule():
            schedule.every().friday.at("22:18").do(send_weekly_report)
            while True:
                schedule.run_pending()
                time.sleep(1)

        thread = threading.Thread(target=run_schedule, daemon=True)
        thread.start()

    def start_requests(self):
        # Proper headers to bypass API blocking
        # NOTE: Update these headers based on your target API requirements
        headers = {
            'Referer': 'https://example-dashboard.com/',
            'Origin': 'https://example-dashboard.com',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
        }

        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.errback_httpbin,
                headers=headers,
                dont_filter=True,
                meta={
                    'handle_httpstatus_list': [403, 404, 500, 503]
                }
            )

    def parse(self, response):
        if response.status in [403, 404, 500, 503]:
            logging.error(f"Error {response.status} for URL: {response.url}")
            return

        try:
            # Decode API response
            # NOTE: This decoding logic is specific to the original API
            # You will need to modify this for your data source
            content = response.text
            # Find split point (response length - 1) * 4
            split_point = (len(content) // 4 - 1) * 4
            # Split text into two parts
            first_part = content[0:split_point]
            second_part = content[split_point:]
            # Reverse first part and concatenate with second
            decoded_content = ''.join(reversed(list(first_part))) + second_part
            # Decode base64
            json_data = base64.b64decode(decoded_content.encode('latin-1')).decode('utf-8')
            data = json.loads(json_data)

            if not data or not data.get('symbols'):
                logging.warning(f"No data found in API response: {response.url}")
                return

            for symbol_data in data['symbols']:
                try:
                    item = SentimentItem()
                    item['pair'] = symbol_data.get('symbol', '')
                    item['long_percentage'] = float(symbol_data.get('p', 0))
                    item['short_percentage'] = 100 - item['long_percentage']
                    yield item
                    self.success_count += 1
                except Exception as e:
                    logging.error(f"Error processing symbol data: {e}")
                    continue

        except Exception as e:
            logging.error(f"Error parsing API response: {e}")

    def errback_httpbin(self, failure):
        if failure.check(HttpError):
            response = failure.value.response
            logging.error(f"HttpError for {response.url} - Status: {response.status}")
        elif failure.check(DNSLookupError):
            request = failure.request
            logging.error(f"DNSLookupError for {request.url}")
        elif failure.check(TimeoutError):
            request = failure.request
            logging.error(f"TimeoutError for {request.url}")
        else:
            logging.error(f"Other error: {failure.value}")
