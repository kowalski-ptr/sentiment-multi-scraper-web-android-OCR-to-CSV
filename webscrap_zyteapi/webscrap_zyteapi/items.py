import scrapy

class SentimentItem(scrapy.Item):
    # CurrencyPair Name
    pair = scrapy.Field()
    # long %
    long_percentage = scrapy.Field()
    # short %
    short_percentage = scrapy.Field()
    # Date
    timestamp = scrapy.Field()
