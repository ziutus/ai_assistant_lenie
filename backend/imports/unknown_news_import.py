#!/usr/bin/env python3
"""Import curated links from unknow.news into PostgreSQL.

Downloads the full archive JSON and imports new entries that are newer
than the last imported date (auto-detected from DB or overridden via --since).

Usage:
    cd backend
    ./imports/unknown_news_import.py
    ./imports/unknown_news_import.py --since 2026-02-01
    ./imports/unknown_news_import.py --since 2026-02-01 --dry-run
    ./imports/unknown_news_import.py --since 2026-02-01 --dry-run --limit 5
"""

import argparse
from urllib.parse import urlparse
import json
import os
import re
import sys
from datetime import datetime

import psycopg2
import requests

from library.config_loader import load_config
from library.stalker_web_document_db import StalkerWebDocumentDB
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL
from library.stalker_web_document import StalkerDocumentStatus, StalkerDocumentType

FEED_URL = "https://unknow.news/archiwum.json"
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED_CACHE = os.path.join(_BACKEND_DIR, "tmp", "archiwum.json")
SOURCE = "https://unknow.news/"


def date1_younger(date1: str, date2: str) -> bool:
    date1_datetime = datetime.strptime(date1, '%Y-%m-%d')
    date2_datetime = datetime.strptime(date2, '%Y-%m-%d')
    return date1_datetime > date2_datetime


def download_feed(cache_path: str) -> list[dict]:
    print("Download data from https://unknow.news/")
    response = requests.get(FEED_URL)
    response.raise_for_status()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'wb') as file:
        file.write(response.content)
    print(f"Data saved to {cache_path}")

    with open(cache_path, 'r', encoding='utf-8') as file:
        json_data = json.load(file)
    print(f"Loaded {len(json_data)} entries")
    return json_data


def main():
    parser = argparse.ArgumentParser(description="Import curated links from unknow.news into PostgreSQL")
    parser.add_argument("--since", default=None, help="Import entries from this date onward (YYYY-MM-DD). "
                                                       "Overrides automatic detection from DB.")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to add (0 = unlimited)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()

    # Validate --since format
    if args.since:
        try:
            datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: invalid date format '{args.since}', expected YYYY-MM-DD")
            sys.exit(1)

    cfg = load_config()
    backend_name = cfg.get('SECRETS_BACKEND', 'env')

    print("=== unknow.news import ===")
    print(f"Config backend: {backend_name}")

    # Show config source so the user knows where DB credentials come from
    try:
        from dotenv import find_dotenv
        dotenv_path = find_dotenv(usecwd=True)
    except ImportError:
        dotenv_path = None
    print(f"Bootstrap .env: {dotenv_path or '(not found)'}")

    if backend_name == "vault":
        project = cfg.get("PROJECT_CODE", "lenie")
        env = cfg.get("SECRETS_ENV") or cfg.get("VAULT_ENV", "dev")
        print(f"Secrets source: Vault at {cfg.get('VAULT_ADDR', '(not set)')} path secret/{project}/{env}")
    elif backend_name == "aws":
        project = cfg.get("PROJECT_CODE", "lenie")
        env = cfg.get("SECRETS_ENV", "dev")
        region = cfg.get("AWS_REGION", "eu-central-1")
        print(f"Secrets source: AWS SSM /{project}/{env}/ (region: {region})")
    else:
        print(f"Secrets source: {dotenv_path or 'environment variables'}")

    print(f"DB host: {cfg.get('POSTGRESQL_HOST', '(not set — will use local socket)')}")
    print(f"DB name: {cfg.get('POSTGRESQL_DATABASE', '(not set)')}")
    print(f"DB port: {cfg.get('POSTGRESQL_PORT', '(not set)')}")
    if args.dry_run:
        print("Mode: DRY-RUN (no changes)")
    if args.limit:
        print(f"Limit: {args.limit}")

    # Download feed
    json_data = download_feed(FEED_CACHE)

    # Determine last_date cutoff
    if args.since:
        last_date = args.since
        print(f"Using --since date: {last_date}")
    else:
        print("Connecting to database", end=" ")
        try:
            websites = WebsitesDBPostgreSQL()
        except psycopg2.OperationalError as e:
            print("[FAILED]")
            print(f"ERROR: cannot connect to PostgreSQL: {e}")
            print("Check POSTGRESQL_HOST/DATABASE/USER/PASSWORD/PORT in your .env file.")
            print("Hint: use --since YYYY-MM-DD to skip the DB lookup for last imported date.")
            sys.exit(1)
        print("[DONE]")
        last_date = websites.get_last_unknown_news()
        if last_date is None:
            print("WARNING: no existing entries found in DB — will import all entries")
            print("  (use --since YYYY-MM-DD to restrict the date range)")
        else:
            print(f"Last entry from source: {SOURCE} is from {last_date}")

    # Process entries
    add = 0
    exist = 0
    ignored = 0

    for entry in json_data:
        if last_date is not None and date1_younger(last_date, entry["date"]):
            ignored += 1
            continue

        #  noinspection HttpUrlsUsage
        unsecure_address = "http://uw7.org/un"
        if entry['url'].startswith("https://uw7.org/un") or entry['url'].startswith(unsecure_address):
            print("Will ignore as paid link: " + entry['url'])
            continue

        if re.match("sponsorowane", entry['title']):
            print("Will ignore as 'reklama': " + entry['url'])
            continue

        if args.dry_run:
            print(f"  DRY-RUN: would add [{entry['date']}] {entry['title'][:80]} — {entry['url']}")
            add += 1
            if args.limit and add >= args.limit:
                print(f"Limit reached ({args.limit})")
                break
            continue

        try:
            web_document = StalkerWebDocumentDB(url=entry['url'])
        except psycopg2.OperationalError as e:
            print(f"ERROR: lost database connection: {e}")
            print("Aborting import.")
            break

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
            hostname = urlparse(entry['url']).hostname or ""
            if hostname in ("youtube.com", "www.youtube.com", "m.youtube.com") or hostname == "youtu.be":
                web_document.document_type = StalkerDocumentType.youtube
                web_document.document_state = StalkerDocumentStatus.URL_ADDED
            else:
                web_document.document_type = StalkerDocumentType.link
                web_document.document_state = StalkerDocumentStatus.READY_FOR_EMBEDDING
            web_document.source = SOURCE
            web_document.date_from = entry['date']
            web_document.save()

            if args.limit and add >= args.limit:
                print(f"Limit reached ({args.limit})")
                break

    # Summary
    print("\n=== Summary ===")
    print(f"Added: {add}")
    print(f"Exist: {exist}")
    print(f"Ignored (imported in past): {ignored}")


if __name__ == "__main__":
    main()
