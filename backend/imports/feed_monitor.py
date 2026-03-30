#!/usr/bin/env python3
"""Monitor RSS/Atom/JSON feeds and curate items for import into Lenie.

Supports feed types:
  - youtube_channel: YouTube channel Atom feed
  - wordpress/rss: RSS 2.0 / Atom feeds
  - json_api: JSON API (e.g. unknow.news archiwum.json)

Usage:
    cd backend
    python imports/feed_monitor.py --list                              # Show configured feeds
    python imports/feed_monitor.py --check                             # List new items from all feeds
    python imports/feed_monitor.py --check --db                        # Same, marking NEW / IN DB
    python imports/feed_monitor.py --check --source "malak.cloud"      # Single feed
    python imports/feed_monitor.py --check --since 2026-03-01          # Only items after date
    python imports/feed_monitor.py --import                            # Interactive: pick items to add
    python imports/feed_monitor.py --import --source "unknow.news"     # Auto-import (if auto_import=true)
    python imports/feed_monitor.py --import --dry-run                  # Preview without DB writes
    python imports/feed_monitor.py --review --source 12 --since "last 2 weeks"  # Interactive review
    python imports/feed_monitor.py --review --source 12 --db           # Review with DB duplicate check
"""

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse

import requests
import yaml
from sqlalchemy.exc import OperationalError as SAOperationalError

from sqlalchemy import select

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import ImportLog, WebDocument
from library.import_log_tracker import ImportLogTracker
from library.models.stalker_document_status import StalkerDocumentStatus
from library.models.stalker_document_type import StalkerDocumentType
from library.stalker_web_documents_db_postgresql import WebsitesDBPostgreSQL

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IMPORTS_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_CONFIG = os.path.join(_IMPORTS_DIR, "feeds.yaml")
FEEDS_STATE = os.path.join(_IMPORTS_DIR, "feeds_state.yaml")
DEFAULT_LOOKBACK_DAYS = 14

# XML namespaces used in YouTube Atom feeds
ATOM_NS = "http://www.w3.org/2005/Atom"
MEDIA_NS = "http://search.yahoo.com/mrss/"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_feeds_config(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("feeds", [])


def load_feeds_state(path: str) -> dict:
    """Load per-feed state (last_checked dates) from YAML file."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def save_feeds_state(path: str, state: dict):
    """Save per-feed state to YAML file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


def update_feed_last_checked(state: dict, feed_name: str, checked_date: Optional[date] = None):
    """Update last_checked for a feed in state dict."""
    if checked_date is None:
        checked_date = date.today()
    state[feed_name] = {"last_checked": checked_date.isoformat()}


def get_feed_last_checked(state: dict, feed_name: str) -> Optional[date]:
    """Get last_checked date for a feed from state."""
    feed_state = state.get(feed_name, {})
    last_checked = feed_state.get("last_checked")
    if last_checked:
        if isinstance(last_checked, date):
            return last_checked
        return datetime.strptime(str(last_checked), "%Y-%m-%d").date()
    return None


def build_feed_url(feed_config: dict) -> str:
    feed_type = feed_config["type"]
    if feed_type == "youtube_channel":
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={feed_config['channel_id']}"
    elif feed_type in ("wordpress", "rss", "json_api"):
        return feed_config["url"]
    else:
        raise ValueError(f"Unknown feed type: {feed_type}")


# ---------------------------------------------------------------------------
# Fetching & parsing
# ---------------------------------------------------------------------------

def fetch_feed_xml(url: str) -> ET.Element:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return ET.fromstring(response.content)


def fetch_json_feed(url: str, cache_path: Optional[str] = None) -> list[dict]:
    """Download JSON feed, optionally caching to disk."""
    print(f"  Downloading {url}...")
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    if cache_path:
        abs_cache = os.path.join(_BACKEND_DIR, cache_path) if not os.path.isabs(cache_path) else cache_path
        os.makedirs(os.path.dirname(abs_cache), exist_ok=True)
        with open(abs_cache, "wb") as f:
            f.write(response.content)

    return response.json()


def parse_atom_entries(root: ET.Element) -> list[dict]:
    """Parse Atom feed (YouTube channels)."""
    entries = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        link_el = entry.find(f"{{{ATOM_NS}}}link")
        published_el = entry.find(f"{{{ATOM_NS}}}published")
        description_el = entry.find(f"{{{MEDIA_NS}}}group/{{{MEDIA_NS}}}description")

        entries.append({
            "title": title_el.text.strip() if title_el is not None and title_el.text else "",
            "url": link_el.get("href", "") if link_el is not None else "",
            "published": published_el.text.strip() if published_el is not None and published_el.text else "",
            "summary": strip_html(description_el.text.strip() if description_el is not None and description_el.text
                                  else ""),
        })
    return entries


def parse_rss_entries(root: ET.Element) -> list[dict]:
    """Parse RSS 2.0 feed (WordPress, generic)."""
    entries = []
    channel = root.find("channel")
    if channel is None:
        return entries
    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_date_el = item.find("pubDate")
        desc_el = item.find("description")

        published = ""
        if pub_date_el is not None and pub_date_el.text:
            try:
                dt = parsedate_to_datetime(pub_date_el.text.strip())
                published = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                published = pub_date_el.text.strip()

        entries.append({
            "title": title_el.text.strip() if title_el is not None and title_el.text else "",
            "url": link_el.text.strip() if link_el is not None and link_el.text else "",
            "published": published,
            "summary": strip_html(desc_el.text.strip() if desc_el is not None and desc_el.text else ""),
        })
    return entries


def parse_xml_feed(root: ET.Element) -> list[dict]:
    """Auto-detect XML feed format and parse entries."""
    if root.tag == f"{{{ATOM_NS}}}feed":
        return parse_atom_entries(root)
    elif root.tag == "rss":
        return parse_rss_entries(root)
    else:
        print(f"  WARNING: Unknown feed format (root tag: {root.tag}), trying RSS...")
        return parse_rss_entries(root)


def parse_json_entries(raw_entries: list[dict], feed_config: dict) -> list[dict]:
    """Convert JSON feed entries to normalized format using field_mapping from config."""
    mapping = feed_config.get("field_mapping", {})
    url_field = mapping.get("url", "url")
    title_field = mapping.get("title", "title")
    summary_field = mapping.get("summary", "summary")
    date_field = mapping.get("date", "date")

    entries = []
    for raw in raw_entries:
        entries.append({
            "title": str(raw.get(title_field, "")).strip(),
            "url": str(raw.get(url_field, "")).strip(),
            "published": str(raw.get(date_field, "")).strip(),
            "summary": str(raw.get(summary_field, "")).strip(),
        })
    return entries


def fetch_entries(feed_config: dict) -> list[dict]:
    """Fetch and parse entries from any supported feed type."""
    feed_type = feed_config["type"]
    url = build_feed_url(feed_config)

    if feed_type == "json_api":
        raw = fetch_json_feed(url, cache_path=feed_config.get("cache_path"))
        return parse_json_entries(raw, feed_config)
    else:
        root = fetch_feed_xml(url)
        return parse_xml_feed(root)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def apply_skip_filters(entries: list[dict], feed_config: dict) -> list[dict]:
    """Filter out entries matching skip_url_patterns or skip_title_patterns."""
    url_patterns = feed_config.get("skip_url_patterns", [])
    title_patterns = feed_config.get("skip_title_patterns", [])

    if not url_patterns and not title_patterns:
        return entries

    filtered = []
    for entry in entries:
        skip = False
        for pattern in url_patterns:
            if entry["url"].startswith(pattern):
                skip = True
                break
        if not skip:
            for pattern in title_patterns:
                if re.search(pattern, entry["title"], re.IGNORECASE):
                    skip = True
                    break
        if not skip:
            filtered.append(entry)
    return filtered


def filter_by_date(entries: list[dict], since_date: Optional[date]) -> list[dict]:
    if not since_date:
        return entries
    return [e for e in entries if (parse_date(e["published"]) or since_date) >= since_date]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_html(text: str) -> str:
    """Convert HTML to plain text: strip tags, convert <br> to newlines, decode entities."""
    if not text or "<" not in text:
        return text
    import html
    # <br> / <br/> -> newline
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # <p>, </p> -> newline
    text = re.sub(r"</?p\s*>", "\n", text, flags=re.IGNORECASE)
    # <li> -> newline + bullet, </li> -> nothing
    text = re.sub(r"<li\s*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "", text, flags=re.IGNORECASE)
    # <ul>, </ul>, <ol>, </ol> -> newline
    text = re.sub(r"</?[uo]l\s*>", "\n", text, flags=re.IGNORECASE)
    # <a href="...">text</a> -> text (URL)
    text = re.sub(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"\2 (\1)", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities (&amp; &lt; etc.)
    text = html.unescape(text)
    # Strip trailing whitespace from each line
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    # Collapse multiple blank lines to single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_date(date_str: str) -> Optional[date]:
    """Try to parse date string to date object."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S+00:00", "%Y-%m-%dT%H:%M:%S.%f+00:00"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date()
    except (ValueError, TypeError):
        return None


def is_feed_active(feed_config: dict, source_filter: Optional[str] = None) -> bool:
    """Check if feed should be processed (not disabled, matches source filter)."""
    if source_filter and feed_config["name"] != source_filter:
        return False
    if feed_config.get("disabled") and not source_filter:
        return False
    return True


def detect_document_type(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    if hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"):
        return StalkerDocumentType.youtube.name
    return StalkerDocumentType.link.name


def resolve_default_state(feed_config: dict, doc_type: str) -> str:
    """Determine initial document_state from feed config or defaults."""
    configured = feed_config.get("default_state")
    if configured:
        return configured
    if doc_type == StalkerDocumentType.youtube.name:
        return StalkerDocumentStatus.URL_ADDED.name
    return StalkerDocumentStatus.URL_ADDED.name


def check_existing(session, url: str) -> Optional[WebDocument]:
    try:
        return WebDocument.get_by_url(session, url)
    except SAOperationalError:
        return None


def get_db_session():
    """Connect to DB and return session, printing connection info."""
    cfg = load_config()
    print(f"DB: {cfg.get('POSTGRESQL_HOST', '?')}:{cfg.get('POSTGRESQL_PORT', '?')}"
          f"/{cfg.get('POSTGRESQL_DATABASE', '?')}")
    return get_session()


def print_entry(idx: int, entry: dict, status: str = ""):
    status_str = f" [{status}]" if status else ""
    date_str = entry["published"][:10] if entry["published"] else "????"
    print(f"  {idx:3d}. [{date_str}]{status_str} {entry['title'][:90]}")
    print(f"       {entry['url']}")


def determine_since_date(feed_config: dict, session, explicit_since: Optional[str],
                         state: Optional[dict] = None) -> Optional[date]:
    """Determine the cutoff date. Priority:
    1. Explicit --since from CLI
    2. DB last import date (for auto_import feeds with DB connection)
    3. last_checked from feeds_state.yaml
    4. Default: 14 days ago
    """
    if explicit_since:
        return datetime.strptime(explicit_since, "%Y-%m-%d").date()

    feed_name = feed_config["name"]

    # Try DB for auto_import feeds
    if feed_config.get("auto_import") and session:
        source_name = feed_config.get("source_id", feed_name)
        websites = WebsitesDBPostgreSQL(session=session)
        last_date = websites.get_last_by_source(source_name)
        if last_date:
            # Show import_logs date as informational context
            try:
                log_date = session.scalar(
                    select(ImportLog.until_date)
                    .where(ImportLog.script_name == "feed_monitor")
                    .where(ImportLog.status == "success")
                    .order_by(ImportLog.finished_at.desc())
                    .limit(1)
                )
                if log_date:
                    print(f"  Last import in DB: {last_date} (import_logs: {log_date})")
                else:
                    print(f"  Last import in DB: {last_date}")
            except Exception:
                print(f"  Last import in DB: {last_date}")
            return last_date

    # Try state file
    if state:
        last_checked = get_feed_last_checked(state, feed_name)
        if last_checked:
            print(f"  Last checked: {last_checked}")
            return last_checked

    # Default: 14 days ago
    default_date = date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    print(f"  No history — defaulting to last {DEFAULT_LOOKBACK_DAYS} days (since {default_date})")
    return default_date


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(feeds: list[dict]):
    active = [f for f in feeds if not f.get("disabled")]
    disabled = [f for f in feeds if f.get("disabled")]
    print(f"\nConfigured feeds ({len(feeds)} total, {len(active)} active, {len(disabled)} disabled):\n")
    for i, feed in enumerate(feeds, 1):
        status_flags = []
        if feed.get("auto_import"):
            status_flags.append("auto_import")
        if feed.get("disabled"):
            status_flags.append("DISABLED")
        flags_str = f"  | {', '.join(status_flags)}" if status_flags else ""
        feed_url = build_feed_url(feed)
        print(f"  {i}. {feed['name']}")
        print(f"     Type: {feed['type']} | Language: {feed.get('language', '?')} "
              f"| Project: {feed.get('project', '-')}{flags_str}")
        print(f"     URL: {feed_url}")
        if feed.get("tags"):
            print(f"     Tags: {', '.join(feed['tags'])}")
        print()


def cmd_check(feeds: list[dict], since: Optional[str] = None, source_filter: Optional[str] = None,
              check_db: bool = False, only_ignored: bool = False, state_path: str = FEEDS_STATE):
    state = load_feeds_state(state_path)

    session = None
    if check_db:
        try:
            session = get_db_session()
        except Exception as e:
            print(f"WARNING: cannot connect to DB ({e}), showing all entries without status")

    total_new = 0
    total_existing = 0
    checked_feeds = []

    for feed in feeds:
        if not is_feed_active(feed, source_filter):
            continue

        print(f"\n{'='*60}")
        print(f"Feed: {feed['name']} ({feed['type']})")
        print(f"{'='*60}")

        try:
            all_entries = fetch_entries(feed)
        except Exception as e:
            print(f"  ERROR fetching feed: {e}")
            continue
        entries = apply_skip_filters(all_entries, feed)
        ignored_entries = [e for e in all_entries if e not in entries]

        effective_since = determine_since_date(feed, session, since, state)

        if effective_since:
            entries = filter_by_date(entries, effective_since)
            ignored_entries = filter_by_date(ignored_entries, effective_since)

        # --ignored: show only filtered-out entries
        if only_ignored:
            if not ignored_entries:
                print("  No ignored entries.")
                checked_feeds.append(feed["name"])
                continue
            print(f"  Ignored entries ({len(ignored_entries)}):\n")
            for i, entry in enumerate(ignored_entries, 1):
                print_entry(i, entry)
            checked_feeds.append(feed["name"])
            print()
            continue

        if not entries:
            print("  No entries found.")
            checked_feeds.append(feed["name"])
            continue

        new_count = 0
        existing_count = 0
        print(f"  Found {len(entries)} entries"
              + (f" ({len(ignored_entries)} ignored)" if ignored_entries else "")
              + (f" (since {effective_since})" if effective_since else "") + ":\n")
        for i, entry in enumerate(entries, 1):
            if session:
                existing = check_existing(session, entry["url"])
                if existing:
                    status = f"IN DB id={existing.id}"
                    existing_count += 1
                else:
                    status = "NEW"
                    new_count += 1
            else:
                status = ""
            print_entry(i, entry, status=status)

        if session:
            print(f"\n  Summary: {new_count} new, {existing_count} already in DB")
            total_new += new_count
            total_existing += existing_count

        checked_feeds.append(feed["name"])
        print()

    # Update state with today's date for all checked feeds
    for name in checked_feeds:
        update_feed_last_checked(state, name)
    save_feeds_state(state_path, state)

    if session:
        session.close()
        print(f"Total: {total_new} new, {total_existing} already in DB")

    print(f"State saved to {state_path}")


def cmd_import(feeds: list[dict], since: Optional[str] = None, source_filter: Optional[str] = None,
               dry_run: bool = False, limit: int = 0, state_path: str = FEEDS_STATE):
    state = load_feeds_state(state_path)

    # Connect to DB first (needed for auto_import since-detection and duplicate check)
    session = None
    if not dry_run:
        try:
            session = get_db_session()
        except Exception as e:
            print(f"ERROR: cannot connect to DB: {e}")
            sys.exit(1)

    # Collect entries from all feeds
    all_items: list[tuple[dict, dict]] = []  # (feed_config, entry)
    checked_feeds = []

    for feed in feeds:
        if not is_feed_active(feed, source_filter):
            continue

        print(f"\nFetching: {feed['name']}...", end=" ")
        try:
            entries = fetch_entries(feed)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        entries = apply_skip_filters(entries, feed)

        # Determine date cutoff
        effective_since = determine_since_date(feed, session, since, state)
        if effective_since:
            entries = filter_by_date(entries, effective_since)

        checked_feeds.append(feed["name"])

        print(f"{len(entries)} entries")
        for entry in entries:
            all_items.append((feed, entry))

    if not all_items:
        print("\nNo entries found.")
        if session:
            session.close()
        return

    # Filter out already existing items
    new_items: list[tuple[int, dict, dict]] = []
    existing_count = 0

    for feed, entry in all_items:
        if session:
            existing = check_existing(session, entry["url"])
            if existing:
                existing_count += 1
                # Correct missing date_from (like unknown_news_import.py did)
                pub_date = parse_date(entry["published"])
                if pub_date and not existing.date_from:
                    existing.date_from = pub_date
                    try:
                        session.commit()
                    except SAOperationalError:
                        session.rollback()
                continue
        new_items.append((len(new_items) + 1, feed, entry))

    if existing_count:
        print(f"Skipped {existing_count} items already in database.")

    if not new_items:
        print("No new items to import.")
        if session:
            session.close()
        return

    # Separate auto_import items from curated items
    auto_items = [(idx, f, e) for idx, f, e in new_items if f.get("auto_import")]
    curated_items = [(idx, f, e) for idx, f, e in new_items if not f.get("auto_import")]

    added = 0
    errors = 0

    # Set up import log tracking
    if session and not dry_run:
        tracker_params = {"source_filter": source_filter, "limit": limit}
        if since:
            tracker_params["since"] = since
        tracker_ctx = ImportLogTracker("feed_monitor", tracker_params)
    else:
        tracker_ctx = nullcontext()

    try:
        with tracker_ctx as tracker:
            if tracker and since:
                try:
                    tracker.set_dates(
                        since_date=datetime.strptime(since, "%Y-%m-%d").date(),
                        until_date=datetime.now().date(),
                    )
                except ValueError:
                    pass  # since not in expected format — skip dates

            # --- Auto-import feeds (no user interaction) ---
            if auto_items:
                print(f"\n{'='*60}")
                print(f"Auto-importing {len(auto_items)} items:")
                print(f"{'='*60}")

                for idx, feed, entry in auto_items:
                    if limit and added >= limit:
                        print(f"Limit reached ({limit})")
                        break

                    if dry_run:
                        print(f"  DRY-RUN: [{entry['published'][:10]}] {entry['title'][:80]}")
                        added += 1
                        continue

                    result = _import_entry(session, feed, entry)
                    if result == "added":
                        added += 1
                        print(f"  Added: {entry['title'][:70]}")
                    elif result == "error":
                        errors += 1

            # --- Curated feeds (interactive selection) ---
            if curated_items:
                # Re-number for display
                display_items = [(i + 1, f, e) for i, (_, f, e) in enumerate(curated_items)]

                print(f"\n{'='*60}")
                print(f"New items for review ({len(display_items)}):")
                print(f"{'='*60}\n")

                for idx, feed, entry in display_items:
                    date_str = entry["published"][:10] if entry["published"] else "????"
                    doc_type = detect_document_type(entry["url"])
                    print(f"  {idx:3d}. [{date_str}] [{doc_type}] {entry['title'][:80]}")
                    print(f"       Source: {feed['name']}")
                    print(f"       {entry['url']}")
                    if entry.get("summary"):
                        print(f"       {entry['summary'][:120]}")
                    print()

                if dry_run:
                    print("DRY-RUN mode — no changes made.")
                else:
                    print("Which items to import?")
                    print("  Enter numbers (e.g.: 1,3,5 or 1-5 or 'all' or 'none'):")
                    try:
                        selection = input("> ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print("\nCancelled.")
                        if session:
                            session.close()
                        return

                    selected_indices = _parse_selection(selection, {idx for idx, _, _ in display_items})

                    for idx, feed, entry in display_items:
                        if idx not in selected_indices:
                            continue
                        if limit and added >= limit:
                            print(f"Limit reached ({limit})")
                            break

                        result = _import_entry(session, feed, entry)
                        if result == "added":
                            added += 1
                            print(f"  Added: {entry['title'][:70]}")
                        elif result == "error":
                            errors += 1

            if tracker:
                tracker.set_counts(
                    found=len(all_items),
                    added=added,
                    skipped=existing_count,
                    error=errors,
                )
    finally:
        if session:
            session.close()

    # Update state for all checked feeds
    for name in checked_feeds:
        update_feed_last_checked(state, name)
    if not dry_run:
        save_feeds_state(state_path, state)
        print(f"State saved to {state_path}")

    print("\n=== Summary ===")
    print(f"Added: {added}")
    if errors:
        print(f"Errors: {errors}")


def _import_entry(session, feed_config: dict, entry: dict) -> str:
    """Import a single entry into the database. Returns 'added' or 'error'."""
    url = entry["url"]
    doc_type = detect_document_type(url)

    doc = WebDocument(url=url)
    doc.title = entry["title"]
    if entry.get("summary"):
        doc.summary = entry["summary"]
    doc.language = feed_config.get("language", "pl")
    doc.document_type = doc_type
    doc.source = feed_config.get("source_id", feed_config["name"])
    doc.project = feed_config.get("project")
    doc.document_state = resolve_default_state(feed_config, doc_type)

    pub_date = parse_date(entry["published"])
    if pub_date:
        doc.date_from = pub_date

    session.add(doc)
    try:
        session.commit()
        return "added"
    except SAOperationalError as e:
        session.rollback()
        print(f"  ERROR: {entry['title'][:70]} — {e}")
        return "error"


def _parse_selection(selection: str, valid_indices: set) -> set:
    """Parse user selection string into a set of indices."""
    if not selection or selection.lower() == "none":
        return set()
    if selection.lower() == "all":
        return valid_indices

    selected = set()
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                selected.update(range(int(start), int(end) + 1))
            except ValueError:
                print(f"  WARNING: cannot parse '{part}', skipping")
        else:
            try:
                selected.add(int(part))
            except ValueError:
                print(f"  WARNING: cannot parse '{part}', skipping")
    return selected


# ---------------------------------------------------------------------------
# Review (interactive per-entry loop)
# ---------------------------------------------------------------------------

def _add_skip_title_pattern(config_path: str, feed_name: str, pattern: str):
    """Add a skip_title_patterns entry to a feed in feeds.yaml."""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()
    data = yaml.safe_load(raw)

    for feed in data.get("feeds", []):
        if feed["name"] == feed_name:
            if "skip_title_patterns" not in feed:
                feed["skip_title_patterns"] = []
            feed["skip_title_patterns"].append(pattern)
            break

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
    print(f"  Added pattern '{pattern}' to {feed_name} in {os.path.basename(config_path)}")


DISCUSS_FILE = os.path.join(_BACKEND_DIR, "tmp", "feed_review_discuss.md")


def _save_to_discuss(entry: dict, feed_config: dict, note: str = ""):
    """Append an entry to the discuss file for later Claude Code session."""
    os.makedirs(os.path.dirname(DISCUSS_FILE), exist_ok=True)

    is_new = not os.path.exists(DISCUSS_FILE) or os.path.getsize(DISCUSS_FILE) == 0
    with open(DISCUSS_FILE, "a", encoding="utf-8") as f:
        if is_new:
            f.write("# Feed Review - articles to discuss\n\n")
            f.write("Open a Claude Code session and ask about these articles.\n")
            f.write(f"File: `{DISCUSS_FILE}`\n\n---\n\n")

        date_str = entry["published"][:10] if entry["published"] else "????"
        f.write(f"## {entry['title']}\n\n")
        f.write(f"- **Date**: {date_str}\n")
        f.write(f"- **Source**: {feed_config['name']}\n")
        f.write(f"- **URL**: {entry['url']}\n")
        if entry.get("summary"):
            f.write(f"- **Summary**: {entry['summary']}\n")
        if note:
            f.write(f"- **Note**: {note}\n")
        f.write("\n---\n\n")

    print(f"  -> Saved to {DISCUSS_FILE}")


def cmd_review(feeds: list[dict], since: Optional[str] = None, source_filter: Optional[str] = None,
               check_db: bool = False, config_path: str = FEEDS_CONFIG, state_path: str = FEEDS_STATE):
    """Interactive review: browse entries one by one with actions."""
    state = load_feeds_state(state_path)

    session = None
    if check_db:
        try:
            session = get_db_session()
        except Exception as e:
            print(f"WARNING: cannot connect to DB ({e}), continuing without DB check")

    # Collect entries from matching feeds
    review_items: list[tuple[dict, dict]] = []  # (feed_config, entry)
    checked_feeds = []

    for feed in feeds:
        if not is_feed_active(feed, source_filter):
            continue

        print(f"Fetching: {feed['name']}...", end=" ")
        try:
            all_entries = fetch_entries(feed)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        entries = apply_skip_filters(all_entries, feed)
        effective_since = determine_since_date(feed, session, since, state)
        if effective_since:
            entries = filter_by_date(entries, effective_since)

        print(f"{len(entries)} entries")
        checked_feeds.append(feed["name"])
        for entry in entries:
            review_items.append((feed, entry))

    if not review_items:
        print("\nNo entries to review.")
        if session:
            session.close()
        return

    # Filter out already-in-DB items if session available
    if session:
        filtered = []
        skipped = 0
        for feed, entry in review_items:
            existing = check_existing(session, entry["url"])
            if existing:
                skipped += 1
            else:
                filtered.append((feed, entry))
        if skipped:
            print(f"Skipped {skipped} entries already in DB.")
        review_items = filtered

    if not review_items:
        print("All entries already in DB.")
        if session:
            session.close()
        return

    print(f"\n{len(review_items)} entries to review. Commands:")
    print("  [n]ext / Enter  - skip to next entry")
    print("  [a]dd           - add to Lenie database")
    print("  [d]iscuss       - save to tmp file for later Claude Code discussion")
    print("  [i]gnore        - add title pattern to skip_title_patterns")
    print("  [e]xplain       - open Claude Code to explain this article")
    print("  [q]uit          - stop review")
    print()

    added = 0
    ignored = 0
    discussed = 0

    for idx, (feed, entry) in enumerate(review_items, 1):
        os.system("cls" if os.name == "nt" else "clear")
        date_str = entry["published"][:10] if entry["published"] else "????"
        doc_type = detect_document_type(entry["url"])

        print(f"--- [{idx}/{len(review_items)}] ---")
        print(f"  Date:    {date_str}")
        print(f"  Title:   {entry['title']}")
        print(f"  URL:     {entry['url']}")
        print(f"  Source:  {feed['name']}  |  Type: {doc_type}")
        if entry.get("summary"):
            print(f"  Summary: {entry['summary']}")
        print()
        print("  [n]ext  [a]dd  [d]iscuss  [i]gnore  [e]xplain  [q]uit")

        while True:
            try:
                action = input(f"  [{idx}] Action [n/a/d/i/e/q]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nReview stopped.")
                if session:
                    session.close()
                return

            if action in ("n", "next", ""):
                break

            elif action in ("a", "add"):
                if not session:
                    try:
                        session = get_db_session()
                    except Exception as e:
                        print(f"  ERROR: cannot connect to DB: {e}")
                        break
                result = _import_entry(session, feed, entry)
                if result == "added":
                    added += 1
                    print("  -> Added to Lenie (id assigned by DB)")
                else:
                    print("  -> Error adding entry")
                break

            elif action in ("d", "discuss"):
                try:
                    note = input("  Note (optional, Enter to skip): ").strip()
                except (KeyboardInterrupt, EOFError):
                    note = ""
                _save_to_discuss(entry, feed, note=note)
                discussed += 1
                break

            elif action in ("i", "ignore"):
                print(f"  Current title: {entry['title']}")
                try:
                    pattern = input("  Enter regex pattern to ignore (or Enter to skip): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    break
                if pattern:
                    # Verify pattern matches current title
                    if re.search(pattern, entry["title"], re.IGNORECASE):
                        _add_skip_title_pattern(config_path, feed["name"], pattern)
                        ignored += 1
                    else:
                        print(f"  WARNING: pattern '{pattern}' does NOT match this title.")
                        try:
                            confirm = input("  Add anyway? [y/N]: ").strip().lower()
                        except (KeyboardInterrupt, EOFError):
                            print()
                            break
                        if confirm == "y":
                            _add_skip_title_pattern(config_path, feed["name"], pattern)
                            ignored += 1
                break

            elif action in ("e", "explain"):
                url = entry["url"]
                print("  Opening Claude Code...")
                try:
                    subprocess.run(
                        ["claude", "-p", f"Pobierz i wyjasn mi po polsku ten artykul: {url}"],
                        check=False,
                    )
                except FileNotFoundError:
                    print("  ERROR: 'claude' command not found. Is Claude Code installed?")
                # After explain, let user choose again
                continue

            elif action in ("q", "quit"):
                print("Review stopped.")
                # Update state before exit
                for name in checked_feeds:
                    update_feed_last_checked(state, name)
                save_feeds_state(state_path, state)
                if session:
                    session.close()
                print(f"\nReview summary: {added} added, {discussed} to discuss, {ignored} ignore patterns added")
                return

            else:
                print("  Unknown command. Use: n, a, d, i, e, q")
                continue

    # Update state
    for name in checked_feeds:
        update_feed_last_checked(state, name)
    save_feeds_state(state_path, state)

    if session:
        session.close()

    print(f"\nReview summary: {added} added, {discussed} to discuss, {ignored} ignore patterns added")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Monitor RSS/Atom/JSON feeds and curate items for Lenie")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List configured feeds")
    group.add_argument("--check", action="store_true", help="Check feeds for new entries")
    group.add_argument("--import", dest="do_import", action="store_true",
                       help="Interactive import: pick items to add to DB")
    group.add_argument("--review", action="store_true",
                       help="Interactive review: browse entries one by one with actions (add/ignore/explain)")

    parser.add_argument("--source", default=None, help="Filter by feed name")
    parser.add_argument("--since", default=None,
                        help="Date cutoff: YYYY-MM-DD or natural language (e.g. 'last 2 weeks', '3 days ago')")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to add (0 = unlimited)")
    parser.add_argument("--db", action="store_true",
                        help="Connect to DB to check which entries are already imported (for --check)")
    parser.add_argument("--ignored", action="store_true",
                        help="Show only entries filtered out by skip_title_patterns (spam check)")
    parser.add_argument("--dry-run", action="store_true", help="Preview import without DB writes")
    parser.add_argument("--config", default=FEEDS_CONFIG, help="Path to feeds.yaml config")
    args = parser.parse_args()

    if args.since:
        # Try YYYY-MM-DD first, then natural language via dateparser
        try:
            datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            original = args.since
            # Normalize "last N units" -> "N units ago" (dateparser understands the latter)
            normalized = re.sub(r"^last\s+(\d+)\s+", r"\1 ", original, flags=re.IGNORECASE)
            if normalized != original and "ago" not in normalized:
                normalized += " ago"
            import dateparser
            parsed = dateparser.parse(normalized, settings={"PREFER_DATES_FROM": "past"})
            if parsed:
                args.since = parsed.strftime("%Y-%m-%d")
                print(f"Parsed '{original}' -> {args.since}")
            else:
                print(f"ERROR: cannot parse date '{original}'")
                sys.exit(1)

    feeds = load_feeds_config(args.config)
    if not feeds:
        print(f"No feeds configured in {args.config}")
        sys.exit(1)

    # Resolve --source: accept number (from --list) or name
    source_filter = args.source
    if source_filter and source_filter.isdigit():
        idx = int(source_filter)
        if 1 <= idx <= len(feeds):
            source_filter = feeds[idx - 1]["name"]
            print(f"Source #{idx}: {source_filter}")
        else:
            print(f"ERROR: feed number {idx} out of range (1-{len(feeds)})")
            sys.exit(1)

    if args.list:
        cmd_list(feeds)
    elif args.check:
        cmd_check(feeds, since=args.since, source_filter=source_filter, check_db=args.db,
                  only_ignored=args.ignored)
    elif args.do_import:
        cmd_import(feeds, since=args.since, source_filter=source_filter, dry_run=args.dry_run, limit=args.limit)
    elif args.review:
        cmd_review(feeds, since=args.since, source_filter=source_filter, check_db=args.db,
                   config_path=args.config)


if __name__ == "__main__":
    main()
