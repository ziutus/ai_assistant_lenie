import json
import re
import requests
from datetime import datetime
from dotenv import load_dotenv

from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType

load_dotenv()

feed_news = "tmp/archiwum.json"


def date1_younger(date1: str, date2: str) -> bool:
    date1_datetime = datetime.strptime(date1, '%Y-%m-%d')
    date2_datetime = datetime.strptime(date2, '%Y-%m-%d')

    return date1_datetime > date2_datetime


print("Download data from https://unknow.news/")
response = requests.get("https://unknow.news/archiwum.json")
with open(feed_news, 'wb') as file:
    file.write(response.content)
print(f"Data saved to {feed_news}")

print("Connecting to database", end=" ")
websites = WebsitesDBPostgreSQL()
print("[DONE]")

source = "https://unknow.news/"
print(f"Last entry from source: {source} is from ", end=" ")
last_date = websites.get_last_unknown_news()
print(last_date)

print(f"Loading data from local cache file: {feed_news}", end=" ")
with open(feed_news, 'r', encoding='utf-8') as file:
    json_data = json.load(file)
print(" [DONE]")
print(f"Loaded {len(json_data)} entries")

add = 0
exist = 0
ignored = 0

for entry in json_data:
    if date1_younger(last_date, entry["date"]):
        ignored += 1
        continue

    if entry['url'].startswith("https://uw7.org/un") or entry['url'].startswith("http://uw7.org/un"):
        print("Will ignore as paid link: " + entry['url'])
        continue

    if re.match("sponsorowane", entry['title']):
        print("Will ignore as 'reklama': " + entry['url'])
        continue

    web_document = StalkerWebDocumentDB(url=entry['url'], )

    if web_document.id:
        print(f"Already exists link (id {web_document.id}): {entry['url']}")
        exist += 1

        if not web_document.date_from:
            web_document.date_from = entry['date']
            print("Correcting date from in DB...", end=' ')
            web_document.save()
            print("[DONE]")

        continue
    else:
        print(f"Will add link {entry['url']}, {entry['title']}")
        add += 1
        web_document.url = entry['url']
        web_document.title = entry['title']
        web_document.summary = entry['info']
        web_document.language = "pl"
        web_document.document_type = StalkerDocumentType.link
        web_document.source = source
        web_document.document_state = StalkerDocumentStatus.READY_FOR_TRANSLATION
        web_document.date_from = entry['date']
        web_document.save()

print("Added: {add}".format(add=add))
print("Exist: {exist}".format(exist=exist))
print("Ignored (imported in past): {ignored}".format(ignored=ignored))

exit(0)