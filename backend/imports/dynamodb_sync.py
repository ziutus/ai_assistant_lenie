#!/usr/bin/env python3
"""Sync documents from AWS DynamoDB + S3 to local PostgreSQL.

Pulls new documents from DynamoDB and S3 webpage content,
inserting them into the local Docker PostgreSQL. No VPN, EC2, or RDS needed.

Resource names (DynamoDB table, S3 bucket) are resolved from SSM Parameter Store
using the project/environment convention: /{project}/{env}/...

Usage:
    cd backend
    ./imports/dynamodb_sync.py --since 2026-02-20
    ./imports/dynamodb_sync.py --since 2026-02-20 --dry-run
    ./imports/dynamodb_sync.py --since 2026-02-20 --limit 10
    ./imports/dynamodb_sync.py --since 2026-02-20 --skip-s3
    ./imports/dynamodb_sync.py --since 2026-02-20 --env dev --project lenie
    ./imports/dynamodb_sync.py --since 2026-02-20 --data-dir /custom/cache
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from sqlalchemy.exc import SQLAlchemyError

from library.config_loader import load_config
from library.db.models import WebDocument
from library.db.engine import get_session
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


def fetch_s3_content(s3_client, bucket: str, s3_uuid: str) -> tuple[str | None, str | None]:
    """Fetch .txt and .html from S3 into memory (no disk write)."""
    text_content = None
    html_content = None

    for ext, label in [(".txt", "text"), (".html", "html")]:
        key = f"{s3_uuid}{ext}"

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


def sync_item_to_postgres(item: dict, text_content: str | None, html_content: str | None,
                          dry_run: bool, session=None) -> tuple[str, int | None]:
    """Insert a DynamoDB item into PostgreSQL via ORM. Returns ('added'/'skipped'/'error', doc_id or None)."""
    url = item.get("url")
    if not url:
        print("  SKIP: no url in item")
        return "error", None

    if dry_run:
        doc_type = item.get("type", "link")
        title = item.get("title", "(no title)")
        print(f"  DRY-RUN: would add [{doc_type}] {title[:80]}")
        return "added", None

    try:
        existing = WebDocument.get_by_url(session, url)
    except Exception as e:
        print(f"  ERROR checking URL {url}: {e}")
        return "error", None

    if existing is not None:
        print(f"  SKIP: already exists (id={existing.id}): {url}")
        return "skipped", None

    try:
        doc = WebDocument(url=url)
        doc.title = item.get("title")
        doc.language = item.get("language")
        doc.source = item.get("source", "own")
        doc.note = item.get("note")
        doc.s3_uuid = item.get("s3_uuid")
        doc.chapter_list = item.get("chapter_list")
        doc.created_at = item.get("created_at")

        doc_type = item.get("type", "link")
        doc.set_document_type(doc_type)

        paywall = item.get("paywall", False)
        doc.paywall = paywall in (True, "true", "True", 1, "1")

        if text_content:
            doc.text = text_content
        if html_content:
            doc.text_raw = html_content

        if text_content or html_content:
            doc.document_state = StalkerDocumentStatus.DOCUMENT_INTO_DATABASE.name
        else:
            doc.document_state = StalkerDocumentStatus.URL_ADDED.name

        session.add(doc)
        session.commit()

        print(f"  ADDED (id={doc.id}): [{doc_type}] {doc.title or url}")
        return "added", doc.id

    except SQLAlchemyError as e:
        session.rollback()
        print(f"  ERROR adding {url}: {e}")
        return "error", None


def main():
    parser = argparse.ArgumentParser(description="Sync documents from DynamoDB + S3 to local PostgreSQL")
    parser.add_argument("--since", required=True, metavar="YYYY-MM-DD",
                        help="Sync documents from this date, e.g. --since 2026-02-20")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes or S3 downloads")
    parser.add_argument("--limit", type=int, default=0, help="Max documents to sync (0 = unlimited)")
    parser.add_argument("--skip-s3", action="store_true", help="Skip S3 file downloads (metadata only)")
    parser.add_argument("--project", default="lenie", help="Project code for SSM path (default: lenie)")
    parser.add_argument("--env", default="dev", help="Environment for SSM path (default: dev)")
    parser.add_argument("--table", default=None, help="DynamoDB table name override (skips SSM lookup)")
    parser.add_argument("--bucket", default=None, help="S3 bucket name override (skips SSM lookup)")
    parser.add_argument("--data-dir", default=None, help="Cache dir for S3 files (default: CACHE_DIR config or tmp/markdown)")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    # Resolve cache dir default from config
    if args.data_dir is None:
        args.data_dir = cfg.get("CACHE_DIR") or "tmp/markdown"

    # Validate date format
    try:
        datetime.strptime(args.since, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: invalid date format '{args.since}', expected YYYY-MM-DD")
        sys.exit(1)

    print("=== DynamoDB -> PostgreSQL sync ===")
    print(f"Project: {args.project}, Environment: {args.env}")
    print(f"Since: {args.since}")
    if args.dry_run:
        print("Mode: DRY-RUN (no changes)")
    if args.skip_s3:
        print("S3 downloads: skipped")
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

    session = None if args.dry_run else get_session()
    try:
        for i, item in enumerate(items, 1):
            url = item.get("url", "(no url)")
            print(f"\n[{i}/{len(items)}] {url[:100]}")

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
            s3_uuid = item.get("s3_uuid")
            doc_type = item.get("type", "link")

            if s3_uuid and doc_type == "webpage" and not args.skip_s3 and not args.dry_run:
                text_content, html_content = fetch_s3_content(s3_client, bucket, s3_uuid)

            result, doc_id = sync_item_to_postgres(item, text_content, html_content, args.dry_run, session=session)

            # Save cache files after successful insert (doc_id now available)
            if result == "added" and doc_id and (text_content or html_content):
                save_cache_files(doc_id, text_content, html_content, args.data_dir)

            if result == "added":
                added += 1
            elif result == "skipped":
                skipped += 1
            else:
                errors += 1
    finally:
        if session is not None:
            session.close()

    # Summary
    print("\n=== Summary ===")
    print(f"Total processed: {len(items)}")
    print(f"Added: {added}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Errors: {errors}")


if __name__ == "__main__":
    main()
