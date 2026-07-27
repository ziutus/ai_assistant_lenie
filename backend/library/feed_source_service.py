"""CRUD and validation for PostgreSQL-backed feed configuration."""

import re
from sqlalchemy import select
from library.db.models import FeedSource, Collection, DiscoverySource

ALLOWED_TYPES = {"rss", "wordpress", "youtube_channel", "json_api"}
ALLOWED_STATES = {"URL_ADDED", "READY_FOR_EMBEDDING"}


def validate_feed_values(values: dict) -> dict:
    result = dict(values)
    if result.get("type") not in ALLOWED_TYPES:
        raise ValueError("type must be rss, wordpress, youtube_channel or json_api")
    if result["type"] == "youtube_channel":
        if not result.get("channel_id") or result.get("url"):
            raise ValueError("youtube_channel requires channel_id and no url")
    elif not result.get("url") or result.get("channel_id"):
        raise ValueError("this feed type requires url and no channel_id")
    if result.get("default_state", "URL_ADDED") not in ALLOWED_STATES:
        raise ValueError("default_state is not allowed")
    for field in ("tags", "field_mapping", "skip_url_patterns", "skip_title_patterns"):
        value = result.get(field, [] if field != "field_mapping" else {})
        if field == "field_mapping":
            if not isinstance(value, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
            ):
                raise ValueError("field_mapping must be an object of strings")
        elif not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ValueError(f"{field} must be a list of strings")
        if field != "field_mapping":
            if len(value) > 100 or any(len(v) > 256 for v in value):
                raise ValueError(f"{field} has too many or too-long patterns")
            for pattern in value:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ValueError(f"invalid regex in {field}: {exc}") from exc
    if result["type"] == "json_api" and not {"url", "title"}.issubset(result.get("field_mapping", {})):
        raise ValueError("json_api field_mapping requires url and title")
    return result


def feed_to_dict(feed: FeedSource) -> dict:
    return {
        "id": feed.id,
        "name": feed.name,
        "type": feed.type,
        "url": feed.url,
        "channel_id": feed.channel_id,
        "language": feed.language,
        "collection_id": feed.collection_id,
        "tags": feed.tags or [],
        "auto_import": feed.auto_import,
        "disabled": feed.disabled,
        "auto_import_after": feed.auto_import_after.isoformat() if feed.auto_import_after else None,
        "discovery_source_id": feed.discovery_source_id,
        "default_state": feed.default_state,
        "field_mapping": feed.field_mapping or {},
        "skip_url_patterns": feed.skip_url_patterns or [],
        "skip_title_patterns": feed.skip_title_patterns or [],
        "last_checked_at": feed.last_checked_at.isoformat() if feed.last_checked_at else None,
        "last_successful_import_at": feed.last_successful_import_at.isoformat()
        if feed.last_successful_import_at
        else None,
        "last_error_at": feed.last_error_at.isoformat() if feed.last_error_at else None,
        "last_error": feed.last_error,
    }


def list_feeds(session):
    return session.scalars(select(FeedSource).order_by(FeedSource.name)).all()


def resolve_references(session, values: dict) -> dict:
    values = validate_feed_values(values)
    if "collection" in values:
        name = values.pop("collection")
        row = session.scalars(select(Collection).where(Collection.name == name)).one_or_none()
        if row is None:
            row = Collection(name=name)
            session.add(row)
            session.flush()
        values["collection_id"] = row.id
    if "discovery_source" in values:
        row = DiscoverySource.ensure(session, values.pop("discovery_source"))
        session.flush()
        values["discovery_source_id"] = row.id
    return values
