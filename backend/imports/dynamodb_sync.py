#!/usr/bin/env python3
"""Sync documents from AWS DynamoDB + S3 to local PostgreSQL.

Pulls new documents from DynamoDB and S3 webpage content,
inserting them into the local Docker PostgreSQL. No VPN, EC2, or RDS needed.

Resource names (DynamoDB table, S3 bucket) are resolved from SSM Parameter Store
using the project/environment convention: /{project}/{env}/...

Usage:
    cd backend
    ./imports/dynamodb_sync.py                                  # auto-detect --since from last successful run
    ./imports/dynamodb_sync.py --since 2026-02-20               # explicit date
    ./imports/dynamodb_sync.py --since 2026-02-20 --dry-run
    ./imports/dynamodb_sync.py --since 2026-02-20 --limit 10
    ./imports/dynamodb_sync.py --since 2026-02-20 --skip-s3
    ./imports/dynamodb_sync.py --since 2026-02-20 --env dev --project lenie
    ./imports/dynamodb_sync.py --since 2026-02-20 --data-dir /custom/cache
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from library.config_loader import load_config
from library.db.engine import get_session
from library.db.models import ImportLog, WebDocument
from library.document_service import DocumentService
from library.import_log_tracker import ImportLogTracker
from library.models.stalker_document_status import StalkerDocumentStatus

cfg = load_config()


def get_ssm_parameter(name: str, region: str = None) -> str:
    """Fetch a single SSM Parameter Store value."""
    region = region or cfg.require("AWS_REGION", "us-east-1")
    ssm = boto3.client("ssm", region_name=region)
    response = ssm.get_parameter(Name=name)
    return response["Parameter"]["Value"]


def resolve_resource_names(project: str, env: str, table_override: str | None,
                           bucket_override: str | None, need_bucket: bool) -> tuple[str, str | None]:
    """Resolve DynamoDB table name and S3 bucket from SSM or CLI overrides."""
    # DynamoDB table
    if table_override:
        table_name = table_override
        print(f"DynamoDB table: {table_name} (CLI override)")
    else:
        ssm_path = f"/{project}/{env}/dynamodb/documents/name"
        try:
            table_name = get_ssm_parameter(ssm_path)
            print(f"DynamoDB table: {table_name} (from SSM: {ssm_path})")
        except ClientError as e:
            print(f"ERROR: cannot read SSM parameter {ssm_path}: {e}")
            sys.exit(1)

    # S3 bucket
    bucket = None
    if need_bucket:
        if bucket_override:
            bucket = bucket_override
            print(f"S3 bucket: {bucket} (CLI override)")
        else:
            ssm_path = f"/{project}/{env}/s3/website-content/name"
            try:
                bucket = get_ssm_parameter(ssm_path)
                print(f"S3 bucket: {bucket} (from SSM: {ssm_path})")
            except ClientError as e:
                print(f"ERROR: cannot read SSM parameter {ssm_path}: {e}")
                sys.exit(1)

    return table_name, bucket


def get_dynamodb_items(table_name: str, since_date: str) -> list[dict]:
    """Query DynamoDB DateIndex GSI day-by-day from since_date to today."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    since = datetime.strptime(since_date, "%Y-%m-%d")
    today = datetime.now()
    all_items = []

    current = since
    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        last_evaluated_key = None

        while True:
            query_kwargs = {
                "IndexName": "DateIndex",
                "KeyConditionExpression": Key("created_date").eq(date_str),
            }
            if last_evaluated_key:
                query_kwargs["ExclusiveStartKey"] = last_evaluated_key

            response = table.query(**query_kwargs)
            all_items.extend(response["Items"])

            last_evaluated_key = response.get("LastEvaluatedKey")
            if not last_evaluated_key:
                break

        current += timedelta(days=1)

    print(f"DynamoDB: found {len(all_items)} items since {since_date}")
    return all_items


def fetch_s3_content(s3_client, bucket: str, doc_uuid: str) -> tuple[str | None, str | None]:
    """Fetch .txt and .html from S3 into memory (no disk write)."""
    text_content = None
    html_content = None

    for ext, label in [(".txt", "text"), (".html", "html")]:
        key = f"{doc_uuid}{ext}"

        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read().decode("utf-8")

            if ext == ".txt":
                text_content = content
            else:
                html_content = content

            print(f"  S3: fetched {key} ({len(content)} chars)")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                print(f"  S3: {key} not found (skipping)")
            else:
                print(f"  S3: error fetching {key}: {e}")

    return text_content, html_content


def save_cache_files(doc_id: int, text_content: str | None, html_content: str | None, cache_dir: str):
    """Save S3 content to cache in document_prepare convention: {cache_dir}/{doc_id}/{doc_id}.ext"""
    doc_dir = os.path.join(cache_dir, str(doc_id))
    os.makedirs(doc_dir, exist_ok=True)

    if html_content:
        path = os.path.join(doc_dir, f"{doc_id}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  Cache: saved {path} ({len(html_content)} chars)")

    if text_content:
        path = os.path.join(doc_dir, f"{doc_id}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text_content)
        print(f"  Cache: saved {path} ({len(text_content)} chars)")


def process_article_content(doc_id: int, url: str, cache_base_dir: str,
                             session, skip_llm: bool = False) -> tuple[bool, bool]:
    """Convert HTML to markdown and optionally run LLM article extraction.

    Saves files to cache only — no DB writes.
    Returns (markdown_ok, llm_ok).
    """
    from library.db.models import WebDocument
    from library.document_prepare import prepare_markdown, save_document_info
    from library.article_extractor import process_article_with_llm_fallback

    doc_cache_dir = os.path.join(cache_base_dir, str(doc_id))
    html_file = os.path.join(doc_cache_dir, f"{doc_id}.html")

    if not os.path.isfile(html_file):
        print(f"  Process: no HTML in cache, skipping")
        return False, False

    doc = WebDocument.get_by_id(session, doc_id)
    if doc is None:
        return False, False

    os.makedirs(doc_cache_dir, exist_ok=True)
    save_document_info(doc_id, doc, doc_cache_dir)
    markdown_text = prepare_markdown(doc_id, doc, doc_cache_dir, verbose=True)

    if not markdown_text:
        print(f"  Process: markdown conversion failed")
        return False, False

    step1_path = os.path.join(doc_cache_dir, f"{doc_id}_step_1_all.md")
    if not os.path.isfile(step1_path):
        with open(step1_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

    if skip_llm:
        print(f"  Process: markdown OK ({len(markdown_text)} chars), LLM skipped")
        return True, False

    result = process_article_with_llm_fallback(
        markdown_text=markdown_text,
        document_id=doc_id,
        cache_dir=doc_cache_dir,
        url=url,
    )

    if result:
        print(f"  Process: LLM OK ({len(result)} chars)")
        return True, True

    print(f"  Process: LLM failed — no article markers extracted")
    return True, False


def sync_item_to_postgres(item: dict, text_content: str | None, html_content: str | None,
                          dry_run: bool, session=None, service=None) -> tuple[str, int | None]:
    """Insert a DynamoDB item into PostgreSQL via DocumentService. Returns ('added'/'skipped'/'error', doc_id or None)."""
    url = item.get("url")
    if not url:
        print("  SKIP: no url in item")
        return "error", None

    if dry_run:
        doc_type = item.get("type", "link")
        title = item.get("title", "(no title)")
        print(f"  DRY-RUN: would add [{doc_type}] {title[:80]}")
        return "added", None

    doc_type = item.get("type", "link")

    # Convert paywall to bool before passing to service
    paywall = item.get("paywall", False)
    paywall_bool = paywall in (True, "true", "True", 1, "1")

    # Determine document_state based on content availability
    if text_content or html_content:
        doc_state = StalkerDocumentStatus.DOCUMENT_INTO_DATABASE.name
    else:
        doc_state = StalkerDocumentStatus.URL_ADDED.name

    # Build metadata dict for import_document
    metadata = {}
    for field in ("title", "language", "note", "chapter_list", "created_at"):
        value = item.get(field)
        if value is not None:
            metadata[field] = value
    # DynamoDB still uses "s3_uuid"; ORM attribute is now "uuid" (ADR-015)
    uuid_value = item.get("uuid") or item.get("s3_uuid")
    if uuid_value is not None:
        metadata["uuid"] = uuid_value
    metadata["source"] = item.get("source", "own")
    metadata["paywall"] = paywall_bool
    if text_content:
        metadata["text"] = text_content
    if html_content:
        metadata["text_raw"] = html_content

    try:
        if service is None:
            service = DocumentService(session)
        doc, status = service.import_document(
            url=url,
            document_type=doc_type,
            document_state=doc_state,
            skip_if_exists=True,
            **metadata,
        )

        if status == "skipped":
            print(f"  SKIP: already exists (id={doc.id}): {url}")
            return "skipped", None

        print(f"  ADDED (id={doc.id}): [{doc_type}] {doc.title or url}")
        return "added", doc.id

    except SQLAlchemyError as e:
        session.rollback()
        print(f"  ERROR adding {url}: {e}")
        return "error", None


def get_last_successful_sync_date(session: "Session") -> date | None:
    """Get until_date from the most recent successful dynamodb_sync run.

    Uses finished_at (not started_at) for ordering — ensures we get the most
    recently *completed* run, not just the most recently *started* one.
    """
    result = session.scalar(
        select(ImportLog.until_date)
        .where(ImportLog.script_name == "dynamodb_sync")
        .where(ImportLog.status == "success")
        .order_by(ImportLog.finished_at.desc())
        .limit(1)
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="Sync documents from DynamoDB + S3 to local PostgreSQL")
    parser.add_argument("--since", required=False, default=None, metavar="YYYY-MM-DD",
                        help="Sync from this date (YYYY-MM-DD). If omitted, auto-detected from last successful run.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes or S3 downloads")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to sync (0 = unlimited)")
    parser.add_argument("--skip-s3", action="store_true", help="Skip S3 file downloads (metadata only)")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM article extraction (still converts HTML to markdown)")
    parser.add_argument("--project", default="lenie", help="Project code for SSM path (default: lenie)")
    parser.add_argument("--env", default="dev", help="Environment for SSM path (default: dev)")
    parser.add_argument("--table", default=None, help="DynamoDB table name override (skips SSM lookup)")
    parser.add_argument("--bucket", default=None, help="S3 bucket name override (skips SSM lookup)")
    parser.add_argument("--data-dir", default=None, help="Cache dir for S3 files (default: os.path.join(CACHE_DIR, 'markdown'))")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    # Resolve cache dir default from config
    if args.data_dir is None:
        args.data_dir = os.path.join(cfg.get("CACHE_DIR") or "tmp", "markdown")

    # Auto-detect last successful sync date (one DB connection for both paths)
    auto_date = None
    try:
        detect_session = get_session()
        try:
            auto_date = get_last_successful_sync_date(detect_session)
        finally:
            detect_session.close()
    except (SQLAlchemyError, OSError) as e:
        print(f"ERROR: Cannot connect to database: {e}")
        print("Fix the database connection before running this script.")
        sys.exit(1)

    if args.since is None:
        if auto_date is None:
            print("ERROR: No previous sync found. Please provide --since YYYY-MM-DD for the first run.")
            sys.exit(1)
        args.since = auto_date.strftime("%Y-%m-%d")
        print(f"Auto-detected --since {args.since} from last successful sync")
    else:
        try:
            datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: invalid date format '{args.since}', expected YYYY-MM-DD")
            sys.exit(1)
        if auto_date:
            print(f"Using explicit --since {args.since} (overriding auto-detected {auto_date})")
        else:
            print(f"Using explicit --since {args.since}")

    print("=== DynamoDB -> PostgreSQL sync ===")
    print(f"Project: {args.project}, Environment: {args.env}")
    print(f"Since: {args.since}")
    if args.dry_run:
        print("Mode: DRY-RUN (no changes)")
    if args.skip_s3:
        print("S3 downloads: skipped")
    if args.skip_llm:
        print("LLM extraction: skipped (markdown only)")
    if args.limit:
        print(f"Limit: {args.limit}")

    # Show source and target information
    aws_profile = os.environ.get("AWS_PROFILE", "(default)")  # AWS SDK convention — read from env, not config_loader
    aws_region = cfg.require("AWS_REGION", "us-east-1")
    pg_host = cfg.get("POSTGRESQL_HOST") or "(not set)"
    pg_db = cfg.get("POSTGRESQL_DATABASE") or "(not set)"
    pg_port = cfg.get("POSTGRESQL_PORT") or "5432"
    pg_user = cfg.get("POSTGRESQL_USER") or "(not set)"

    print()
    print(f"Source: AWS profile={aws_profile}, region={aws_region}")
    print(f"Target: PostgreSQL {pg_user}@{pg_host}:{pg_port}/{pg_db}")
    print()

    if not args.yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)
        print()

    # Resolve resource names from SSM (or CLI overrides)
    need_bucket = not args.skip_s3 and not args.dry_run
    table_name, bucket = resolve_resource_names(
        args.project, args.env, args.table, args.bucket, need_bucket
    )
    print()

    # Query DynamoDB
    items = get_dynamodb_items(table_name, args.since)
    if not items:
        print("No items found. Done.")
        return

    if args.limit:
        items = items[:args.limit]
        print(f"Limited to {len(items)} items")

    # Init S3 client
    s3_client = None
    if not args.skip_s3 and not args.dry_run:
        s3_client = boto3.client("s3")

    # Sync items
    added = 0
    skipped = 0
    errors = 0
    md_converted = 0
    llm_extracted = 0

    session = None if args.dry_run else get_session()
    doc_service = DocumentService(session) if session else None
    if session and not args.dry_run:
        tracker_params = {
            "since": args.since,
            "limit": args.limit,
            "skip_s3": args.skip_s3,
            "project": args.project,
            "env": args.env,
        }
        tracker_ctx = ImportLogTracker("dynamodb_sync", tracker_params)
    else:
        tracker_ctx = nullcontext()

    try:
        with tracker_ctx as tracker:
            if tracker:
                since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
                tracker.set_dates(since_date=since_date, until_date=datetime.now().date())

            for i, item in enumerate(items, 1):
                url = item.get("url", "(no url)")
                print(f"\n[{i}/{len(items)}] {url}")

                # Check for duplicate before downloading S3 content
                text_content = None
                html_content = None

                if not args.dry_run:
                    try:
                        existing = WebDocument.get_by_url(session, item.get("url", ""))
                    except Exception as e:
                        print(f"  ERROR checking URL: {e}")
                        errors += 1
                        continue
                    if existing is not None:
                        print(f"  SKIP: already exists (id={existing.id})")
                        skipped += 1
                        continue

                # Fetch S3 content into memory (no disk write yet)
                doc_uuid = item.get("uuid") or item.get("s3_uuid")
                doc_type = item.get("type", "link")

                if doc_uuid and doc_type == "webpage" and not args.skip_s3 and not args.dry_run:
                    text_content, html_content = fetch_s3_content(s3_client, bucket, doc_uuid)

                result, doc_id = sync_item_to_postgres(item, text_content, html_content, args.dry_run, session=session, service=doc_service)

                # Save cache files after successful insert (doc_id now available)
                if result == "added" and doc_id and (text_content or html_content):
                    save_cache_files(doc_id, text_content, html_content, args.data_dir)

                # Convert HTML to markdown + LLM extraction (webpage only, saves to cache)
                if result == "added" and doc_id and doc_type == "webpage" and not args.skip_s3:
                    md_ok, llm_ok = process_article_content(
                        doc_id=doc_id,
                        url=item.get("url", ""),
                        cache_base_dir=args.data_dir,
                        session=session,
                        skip_llm=args.skip_llm,
                    )
                    if md_ok:
                        md_converted += 1
                    if llm_ok:
                        llm_extracted += 1

                if result == "added":
                    added += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    errors += 1

            if tracker:
                tracker.set_counts(found=len(items), added=added, skipped=skipped, error=errors)
    finally:
        if session is not None:
            session.close()

    # Summary
    print("\n=== Summary ===")
    print(f"Total processed: {len(items)}")
    print(f"Added: {added}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Errors: {errors}")
    if md_converted or llm_extracted:
        print(f"Markdown converted: {md_converted}")
        print(f"LLM extracted: {llm_extracted}")


if __name__ == "__main__":
    main()
