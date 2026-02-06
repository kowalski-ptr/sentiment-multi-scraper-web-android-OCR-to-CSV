import sys
from pathlib import Path

# Add project root to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import ZYTE_API_KEY, PUBLIC_REPO_URL

# Scrapy settings for webscrap_zyteapi project
BOT_NAME = "webscrap_zyteapi"

SPIDER_MODULES = ["webscrap_zyteapi.spiders"]
NEWSPIDER_MODULE = "webscrap_zyteapi.spiders"

# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performing at the same time to the same domain
CONCURRENT_REQUESTS = 1

# Configure a delay for requests for the same website
DOWNLOAD_DELAY = 3

# Zyte API settings (loaded from config module)
ZYTE_API_ENABLED = True

# Configure downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
    'webscrap_zyteapi.middlewares.ZyteAPIMiddleware': 100,
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
    'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': 700
}

# Configure item pipelines
ITEM_PIPELINES = {
    "webscrap_zyteapi.pipelines.JsonHistoryPipeline": 300,
}

# Set settings whose default value is deprecated to a future-proof value
TWISTED_REACTOR = "twisted.internet.selectreactor.SelectReactor"
FEED_EXPORT_ENCODING = "utf-8"

# Cache settings
HTTPCACHE_ENABLED = False

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 400, 403, 404, 408]

# Additional settings
COOKIES_ENABLED = True
DOWNLOAD_TIMEOUT = 180

# Logging settings
LOG_LEVEL = 'DEBUG'

# Default request headers
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br'
}
