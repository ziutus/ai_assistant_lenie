"""Temporary, NAS-side pull from the legacy AWS document buffer.

The bridge only moves source data into the normal ingest contract.  Markdown
conversion and LLM work are deliberately left to the ``document_prepare`` job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from library.db.models import Document, ImportLog
from library.document_ingest_service import DocumentIngestService, IngestRequest
from library.import_log_tracker import ImportLogTracker


class LegacyAwsPullPartialError(RuntimeError):
    """At least one legacy item could not be imported; retry the whole window."""


def parse_timestamp(value: str | datetime) -> datetime:
    """Return an ISO-8601 timestamp in UTC; naive input is intentionally refused."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("since must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("since must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def last_successful_watermark(session) -> datetime | None:
    value = session.scalar(
        select(ImportLog.started_at)
        .where(ImportLog.script_name == "legacy_aws_pull", ImportLog.status == "success")
        .order_by(ImportLog.finished_at.desc())
        .limit(1)
    )
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _item_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_bool(value: object) -> bool:
    return value in (True, "true", "True", 1, "1")


def ingest_request_from_item(item: dict[str, Any], text: str = "", html: str = "") -> IngestRequest:
    """Map the legacy DynamoDB shape onto the transport-independent contract."""
    document_type = item.get("type", "link")
    requires_login = item.get("requires_login")
    return IngestRequest(
        url=item.get("url", ""),
        document_type=document_type,
        text=text or "",
        html=html or "",
        title=item.get("title") or "",
        language=item.get("language") or "",
        note=item.get("note") or "default_note",
        paywall=_as_bool(item.get("paywall", False)),
        requires_login=(document_type == "social_media_post" if requires_login is None else _as_bool(requires_login)),
        social_platform=item.get("social_platform"),
        source=item.get("source") or "own",
        chapter_list=item.get("chapter_list", False),
        byline=item.get("byline") or "",
        original_id=item.get("original_id"),
        published_on=item.get("published_on"),
        operation="fill_missing_html" if item.get("target_document_id") is not None else "create",
        external_uuid=item.get("uuid") or item.get("s3_uuid"),
        ingested_at=item.get("created_at"),
    )


@dataclass
class LegacyAwsPullService:
    session: Any
    storage: Any
    config: Any
    boto3_module: Any | None = None
    now: Any = lambda: datetime.now(timezone.utc)

    def _boto3(self):
        if self.boto3_module is None:
            import boto3

            self.boto3_module = boto3
        return self.boto3_module

    def _aws_session(self):
        """Build a separate explicit AWS session; never reuse MinIO credentials."""
        kwargs = {
            "aws_access_key_id": self.config.require("AWS_LEGACY_PULL_ACCESS_KEY_ID"),
            "aws_secret_access_key": self.config.require("AWS_LEGACY_PULL_SECRET_ACCESS_KEY"),
            "region_name": self.config.require("AWS_LEGACY_PULL_REGION"),
        }
        token = self.config.get("AWS_LEGACY_PULL_SESSION_TOKEN")
        if token:
            kwargs["aws_session_token"] = token
        return self._boto3().Session(**kwargs)

    def _query_items(self, table, since: datetime, until: datetime) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        items: list[dict] = []
        current = since.date()
        while current <= until.date():
            last_key = None
            while True:
                kwargs = {"IndexName": "DateIndex", "KeyConditionExpression": Key("created_date").eq(current.isoformat())}
                if last_key:
                    kwargs["ExclusiveStartKey"] = last_key
                page = table.query(**kwargs)
                items.extend(
                    item for item in page.get("Items", [])
                    if (created := _item_timestamp(item.get("created_at"))) is None or created >= since
                )
                last_key = page.get("LastEvaluatedKey")
                if not last_key:
                    break
            current += timedelta(days=1)
        return items

    @staticmethod
    def _fetch_sources(s3, bucket: str, external_uuid: str) -> tuple[str, str]:
        from botocore.exceptions import ClientError

        values: dict[str, str] = {}
        for extension in ("txt", "html"):
            try:
                values[extension] = s3.get_object(Bucket=bucket, Key=f"{external_uuid}.{extension}")["Body"].read().decode("utf-8")
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in {"NoSuchKey", "404", "NotFound"}:
                    raise
        return values.get("txt", ""), values.get("html", "")

    def run(self, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        parameters = parameters or {}
        allowed = {"since", "dry_run", "limit"}
        if set(parameters) - allowed:
            raise ValueError("unsupported legacy_aws_pull parameter")
        dry_run = parameters.get("dry_run", False)
        limit = parameters.get("limit", 0)
        if not isinstance(dry_run, bool) or not isinstance(limit, int) or isinstance(limit, bool) or not 0 <= limit <= 1000:
            raise ValueError("invalid legacy_aws_pull parameters")

        explicit_since = parameters.get("since")
        if explicit_since is not None and not isinstance(explicit_since, str):
            raise ValueError("since must be null or an ISO-8601 timestamp")
        watermark = None if dry_run else last_successful_watermark(self.session)
        if explicit_since is None and watermark is None:
            raise ValueError("since is required until legacy_aws_pull has a full successful run")
        base_since = parse_timestamp(explicit_since) if explicit_since is not None else watermark
        overlap = int(self.config.get("AWS_LEGACY_PULL_OVERLAP_SECONDS") or 300)
        if overlap < 0:
            raise ValueError("AWS_LEGACY_PULL_OVERLAP_SECONDS must be non-negative")
        query_since = base_since - timedelta(seconds=overlap)
        started_at = self.now().astimezone(timezone.utc).replace(microsecond=0)

        aws = self._aws_session()
        table = aws.resource("dynamodb").Table(self.config.require("AWS_LEGACY_PULL_DYNAMODB_TABLE"))
        items = self._query_items(table, query_since, started_at)
        if limit:
            items = items[:limit]
        result = {"found": len(items), "added": 0, "skipped": 0, "refreshed": 0, "errors": 0,
                  "watermark": started_at.isoformat(), "query_since": query_since.isoformat(), "dry_run": dry_run}
        if dry_run:
            return result

        s3 = None
        bucket = None
        with ImportLogTracker("legacy_aws_pull", {"since": base_since.isoformat(), "dry_run": False, "limit": limit}) as tracker:
            tracker.set_dates(since_date=query_since.date(), until_date=started_at.date())
            ingest = DocumentIngestService(self.session, self.storage)
            for item in items:
                try:
                    external_uuid = item.get("uuid") or item.get("s3_uuid")
                    if not item.get("url") or not external_uuid:
                        raise ValueError("legacy item is missing url or uuid")
                    # Local NAS documents may have been created without ever
                    # being copied to the legacy AWS bucket.  For normal
                    # creates, UUID is the idempotency boundary: do not probe
                    # S3 before recognising the local document.
                    if item.get("target_document_id") is None and self.session.scalar(
                        select(Document.id).where(Document.uuid == external_uuid).limit(1)
                    ) is not None:
                        result["skipped"] += 1
                        continue
                    if s3 is None:
                        s3 = aws.client("s3")
                        bucket = self.config.require("AWS_LEGACY_PULL_S3_BUCKET")
                    text, html = self._fetch_sources(s3, bucket, external_uuid)
                    outcome = ingest.ingest(ingest_request_from_item(item, text, html), initiated_by_user_id=None)
                    if outcome.status == "added":
                        result["added"] += 1
                    elif outcome.status == "refreshed":
                        result["refreshed"] += 1
                    else:
                        result["skipped"] += 1
                except Exception:
                    result["errors"] += 1
            tracker.set_counts(found=result["found"], added=result["added"] + result["refreshed"],
                               skipped=result["skipped"], error=result["errors"])
            if limit or result["errors"]:
                tracker.mark_partial("diagnostic limit" if limit else "one or more items failed")
            if result["errors"]:
                raise LegacyAwsPullPartialError(f"{result['errors']} legacy AWS item(s) failed")
        return result
