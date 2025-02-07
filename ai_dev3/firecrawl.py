from dotenv import load_dotenv
import os
from pprint import pprint
from firecrawl import FirecrawlApp

# dotenv.load_dotenv(".env", override=True)
load_dotenv()

# pprint(os.environ.get('FIRECRAWL_API_KEY'))
#
# app = FirecrawlApp(api_key=os.environ.get('FIRECRAWL_API_KEY'))
#
page="https://xyz.ag3nts.org/"
#
# # Crawl a website:
# crawl_status = app.crawl_url(
#   page,
#   params={
#     'limit': 100,
#     'scrapeOptions': {'formats': ['markdown', 'html']}
#   },
#   poll_interval=30
# )
# pprint(crawl_status)