"""
CNN-IDX Scraper using CloudScraper
FREE alternative with rate limiting & monitoring

Based on proven implementation from cnnbtc project
"""
import cloudscraper
import time
import random
from fake_useragent import UserAgent
import requests
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging
from urllib3.util.ssl_ import create_urllib3_context

logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiter to prevent detection"""
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        """
        Initialize rate limiter with sliding window

        Args:
            max_requests: Maximum requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def wait_if_needed(self):
        """Wait if rate limit exceeded"""
        now = datetime.now()

        # Remove old requests outside time window
        self.requests = [r for r in self.requests
                        if now - r < timedelta(seconds=self.time_window)]

        if len(self.requests) >= self.max_requests:
            oldest = self.requests[0]
            wait_time = (oldest + timedelta(seconds=self.time_window) - now).total_seconds()
            if wait_time > 0:
                logger.info(f"Rate limit: waiting {wait_time:.1f}s")
                time.sleep(wait_time)

        self.requests.append(now)

class CNNScraper:
    """Scraper for CNN-IDX with protection"""

    def __init__(self, max_retries: int = 3):
        self.base_url = "https://url.com/"
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(max_requests=10, time_window=60)

        # Success rate monitoring
        self.stats = {
            "success": 0,
            "failed": 0,
            "cloudflare_blocks": 0,
            "ssl_errors": 0,
            "total_requests": 0
        }

    def get_random_headers(self) -> Dict:
        """Generate random headers with fingerprint rotation"""
        ua = UserAgent()

        return {
            'User-Agent': ua.random,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': random.choice([
                'en-US,en;q=0.9',
                'en-GB,en;q=0.9',
                'pl-PL,pl;q=0.9',
                'de-DE,de;q=0.9',
                'fr-FR,fr;q=0.9'
            ]),
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': random.choice(['keep-alive', 'close']),
            'Referer': 'https://url.com/',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }

    async def fetch_cnn_data(self, date_str: str) -> Optional[Dict]:
        """
        Fetch CNN-IDX data with exponential backoff retry

        Args:
            date_str: Date in format 'YYYY-MM-DD'

        Returns:
            Dict with data or None if failed
        """
        self.stats["total_requests"] += 1

        # Apply rate limiting
        self.rate_limiter.wait_if_needed()

        # Random delay (2-7s) to avoid bot detection
        delay = random.uniform(2, 7)
        logger.info(f"Random delay before CNN request: {delay:.2f}s")
        time.sleep(delay)

        url = f"{self.base_url}{date_str}"
        logger.info(f"Fetching CNN data from: {url}")

        # Exponential backoff retry logic
        for attempt in range(self.max_retries):
            try:
                # PRIMARY METHOD: CloudScraper
                result = await self._fetch_cloudscraper(url)

                if result:
                    self.stats["success"] += 1
                    self._log_success_rate()
                    return result

                # If failed, wait with exponential backoff
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
                    time.sleep(wait_time)

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} error: {e}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    time.sleep(wait_time)

        # All retries failed - try fallback
        logger.warning("All CloudScraper attempts failed, trying fallback method...")
        result = await self._fetch_fallback(url)

        if result:
            self.stats["success"] += 1
        else:
            self.stats["failed"] += 1

        self._log_success_rate()
        return result

    async def _fetch_cloudscraper(self, url: str) -> Optional[Dict]:
        """CloudScraper method with anti-Cloudflare"""
        try:
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                }
            )

            response = scraper.get(url, headers=self.get_random_headers(), timeout=30)

            if response.status_code == 200:
                logger.info("CloudScraper: CNN data fetched successfully")
                return response.json()
            elif response.status_code == 403:
                self.stats["cloudflare_blocks"] += 1
                logger.warning("CloudScraper: 403 Forbidden (possible Cloudflare block)")
            else:
                logger.warning(f"CloudScraper returned status {response.status_code}")

        except requests.exceptions.SSLError as e:
            self.stats["ssl_errors"] += 1
            logger.warning(f"SSL Error in CloudScraper: {e}")
        except Exception as e:
            logger.warning(f"CloudScraper error: {e}")

        return None

    async def _fetch_fallback(self, url: str) -> Optional[Dict]:
        """Fallback method with custom SSL context"""
        try:
            logger.info("Using fallback method with custom SSL context...")

            ctx = create_urllib3_context()
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')

            session = requests.Session()
            session.mount('https://', requests.adapters.HTTPAdapter(ssl_context=ctx))

            response = session.get(
                url,
                headers=self.get_random_headers(),
                verify=False,  # Only for fallback
                timeout=30
            )

            if response.status_code == 200:
                logger.info("Fallback method: CNN data fetched successfully")
                return response.json()
            else:
                logger.error(f"Fallback method failed with status {response.status_code}")

        except Exception as e:
            logger.error(f"Fallback method error: {e}")

        return None

    def _log_success_rate(self):
        """Monitor and log success rate"""
        total = self.stats["success"] + self.stats["failed"]
        if total > 0:
            success_rate = self.stats["success"] / total

            logger.info(f"Success rate: {success_rate*100:.1f}% "
                       f"({self.stats['success']}/{total})")

            # Alert if success rate drops below 80%
            if success_rate < 0.8 and total >= 5:
                logger.warning(f"LOW SUCCESS RATE: {success_rate*100:.1f}% "
                              f"(Cloudflare blocks: {self.stats['cloudflare_blocks']}, "
                              f"SSL errors: {self.stats['ssl_errors']})")

    def get_stats(self) -> Dict:
        """Get scraper statistics"""
        total = self.stats["success"] + self.stats["failed"]
        success_rate = self.stats["success"] / total if total > 0 else 0

        return {
            "total_requests": self.stats["total_requests"],
            "successful": self.stats["success"],
            "failed": self.stats["failed"],
            "success_rate": success_rate,
            "cloudflare_blocks": self.stats["cloudflare_blocks"],
            "ssl_errors": self.stats["ssl_errors"]
        }
