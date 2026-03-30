#!/usr/bin/env python3
"""Push recent documents to a Notion page as a changelog.

Fetches the N most recently added documents from PostgreSQL and publishes
them as a formatted list on a Notion page.

Usage:
    cd backend
    PYTHONPATH=. python scripts/notion_changelog.py --dry-run
    PYTHONPATH=. python scripts/notion_changelog.py --limit 10
"""

import argparse
import io
import logging
import sys
from datetime import datetime

# Ensure stdout handles Unicode on Windows (cp1250 cannot encode some chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import psycopg2
from notion_client import Client as NotionClient
from notion_client.errors import APIResponseError

from library.config_loader import load_config


def get_recent_documents(conn, limit: int) -> list[dict]:
    """Fetch the most recently added documents from the database."""
    sql = """
        SELECT id, url, title, document_type, created_at
        FROM public.web_documents
        ORDER BY created_at DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (limit,))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _rich_text(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": content}}]


def _rich_text_link(content: str, url: str) -> list[dict]:
    return [{"type": "text", "text": {"content": content, "link": {"url": url}}}]


def _table_row(cells: list[list[dict]]) -> dict:
    return {"object": "block", "type": "table_row", "table_row": {"cells": cells}}


def build_notion_blocks(documents: list[dict]) -> list[dict]:
    """Build Notion block children from a list of documents."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    header_row = _table_row([
        _rich_text("Type"),
        _rich_text("Title"),
        _rich_text("URL"),
        _rich_text("Date"),
    ])

    data_rows = []
    for doc in documents:
        doc_type = doc.get("document_type", "?")
        title = doc.get("title") or "(no title)"
        url = doc.get("url") or ""
        created = ""
        if doc.get("created_at"):
            created = doc["created_at"].strftime("%Y-%m-%d") if isinstance(doc["created_at"], datetime) else str(doc["created_at"])

        url_cell = _rich_text_link(url, url) if url else _rich_text("")

        data_rows.append(_table_row([
            _rich_text(doc_type),
            _rich_text(title),
            url_cell,
            _rich_text(created),
        ]))

    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 4,
            "has_column_header": True,
            "has_row_header": False,
            "children": [header_row] + data_rows,
        },
    }

    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": _rich_text(f"Changelog — {now}")},
        },
        table_block,
    ]


def clear_page_children(notion: NotionClient, page_id: str) -> int:
    """Delete all existing children blocks from a Notion page (handles pagination)."""
    deleted = 0
    start_cursor = None
    while True:
        kwargs = {"block_id": page_id}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        children = notion.blocks.children.list(**kwargs)
        for block in children.get("results", []):
            notion.blocks.delete(block_id=block["id"])
            deleted += 1
        if not children.get("has_more"):
            break
        start_cursor = children.get("next_cursor")
    return deleted


def update_notion_page(token: str, page_id: str, blocks: list[dict]) -> None:
    """Clear a Notion page and append new blocks."""
    notion = NotionClient(auth=token)

    deleted = clear_page_children(notion, page_id)
    print(f"Cleared {deleted} existing block(s) from page.")

    notion.blocks.children.append(block_id=page_id, children=blocks)
    print(f"Appended {len(blocks)} block(s) to page.")


def main():
    parser = argparse.ArgumentParser(description="Push recent documents changelog to Notion")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent documents to include (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and display documents without pushing to Notion")
    args = parser.parse_args()

    config = load_config()

    db_host = config.get("POSTGRESQL_HOST", "localhost")
    db_port = config.get("POSTGRESQL_PORT", "5432")
    db_name = config.get("POSTGRESQL_DATABASE", "lenie")
    db_user = config.get("POSTGRESQL_USER", "lenie")
    db_pass = config.get("POSTGRESQL_PASSWORD", "")
    print(f"Database: {db_host}:{db_port}/{db_name}")

    try:
        conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
    except psycopg2.OperationalError as exc:
        print(f"ERROR: Cannot connect to database: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        documents = get_recent_documents(conn, args.limit)
    finally:
        conn.close()

    print(f"\nFetched {len(documents)} document(s):\n")
    for doc in documents:
        created = doc.get("created_at", "")
        print(f"  [{doc.get('document_type', '?')}] {doc.get('title', '(no title)')} -- {doc.get('url', '')} ({created})")

    if args.dry_run:
        print("\n--dry-run: skipping Notion update.")
        return

    notion_token = config.get("NOTION_API_TOKEN")
    notion_page_id = config.get("NOTION_PAGE_ID")

    if not notion_token:
        print("ERROR: NOTION_API_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)
    if not notion_page_id:
        print("ERROR: NOTION_PAGE_ID is not set.", file=sys.stderr)
        sys.exit(1)

    blocks = build_notion_blocks(documents)

    try:
        update_notion_page(notion_token, notion_page_id, blocks)
    except APIResponseError as exc:
        if exc.status == 401:
            print("ERROR: Notion API token is invalid or expired.", file=sys.stderr)
        elif exc.status == 404:
            print(f"ERROR: Notion page not found (id: {notion_page_id}). Check NOTION_PAGE_ID.", file=sys.stderr)
        elif exc.status == 429:
            print("ERROR: Notion API rate limit exceeded. Try again later.", file=sys.stderr)
        else:
            print(f"ERROR: Notion API error ({exc.status}): {exc.message}", file=sys.stderr)
        sys.exit(1)

    print("\nDone — changelog published to Notion.")


if __name__ == "__main__":
    main()
