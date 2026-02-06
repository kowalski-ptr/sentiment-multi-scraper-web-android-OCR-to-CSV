import json
import requests
import base64
from scrapy import Request
from scrapy.exceptions import NotConfigured
from urllib.parse import urlparse

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import ZYTE_API_KEY


class ZyteAPIMiddleware:
    """Middleware for handling requests through Zyte API"""

    def __init__(self, api_key, enabled=True):
        self.api_key = api_key
        self.enabled = enabled
        self.api_url = "https://api.zyte.com/v1/extract"

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('ZYTE_API_ENABLED'):
            raise NotConfigured('Zyte API is not enabled')

        api_key = ZYTE_API_KEY
        if not api_key:
            raise NotConfigured('Missing Zyte API key')

        return cls(api_key)

    def process_request(self, request, spider):
        if not self.enabled:
            return None

        # Basic configuration for HTTP request with custom headers
        payload = {
            "url": request.url,
            "httpResponseBody": True,
            "customHttpRequestHeaders": [
                {"name": key, "value": value}
                for key, value in request.headers.to_unicode_dict().items()
            ]
        }

        try:
            # Execute request through Zyte API
            response = requests.post(
                self.api_url,
                auth=(self.api_key, ""),
                json=payload,
                timeout=30
            )

            spider.logger.info(f"Sent request to Zyte API: {payload}")

            if response.status_code == 200:
                data = response.json()
                spider.logger.info(f"Received response from Zyte API: {data}")

                # Decode base64 response
                try:
                    content = base64.b64decode(data.get('httpResponseBody', '')).decode('utf-8')
                    spider.logger.info(f"Decoded content: {content[:200]}...")
                except Exception as e:
                    spider.logger.error(f"Base64 decoding error: {str(e)}")
                    content = data.get('httpResponseBody', '')

                # Create response for Scrapy
                from scrapy.http import TextResponse
                return TextResponse(
                    url=request.url,
                    body=content.encode('utf-8') if isinstance(content, str) else content,
                    encoding='utf-8',
                    request=request
                )

            else:
                spider.logger.error(f"Zyte API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            spider.logger.error(f"Exception during Zyte API usage: {str(e)}")
            return None
