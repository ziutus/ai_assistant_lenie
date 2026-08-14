"""Domain rules for shared content groups and their memberships."""

import datetime as dt

from sqlalchemy import func, select

from library.db.models import (
    ContentGroup,
    Document,
    DocumentChunk,
    DocumentChunkGroupMembership,
    DocumentGroupMembership,
    FeedItem,
    FeedItemGroupMembership,
)


GROUP_KINDS = {"topic", "priority"}
MEMBERSHIP_SOURCES = {
    "feed": {"manual", "llm_suggestion"},
    "document": {"manual", "feed_import", "chrome_link", "llm_suggestion"},
}


def _validate_name(name: object) -> str:
    if not isinstance(name, str):
        raise ValueError("name must be a string")
    value = name.strip()
    if not 1 <= len(value) <= 80:
        raise ValueError("name must contain 1-80 characters")
    return value


def validate_group_values(name: object, kind: object, priority_rank: object = None) -> tuple[str, str, int | None]:
    value = _validate_name(name)
    if kind not in GROUP_KINDS:
        raise ValueError("kind must be topic or priority")
    if kind == "topic":
        if priority_rank is not None:
            raise ValueError("topic groups cannot have priority_rank")
        return value, kind, None
    if isinstance(priority_rank, bool) or not isinstance(priority_rank, int) or not 1 <= priority_rank <= 100:
        raise ValueError("priority_rank must be an integer from 1 to 100")
    return value, kind, priority_rank


def validate_group_ids(group_ids: object) -> list[int]:
    if not isinstance(group_ids, list):
        raise ValueError("group_ids must be an array")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in group_ids):
        raise ValueError("group_ids must contain integers")
    if len(set(group_ids)) != len(group_ids):
        raise ValueError("group_ids must be unique")
    return group_ids


def get_active_groups(session, group_ids: list[int]) -> list[ContentGroup]:
    groups = session.scalars(
        select(ContentGroup).where(ContentGroup.id.in_(group_ids), ContentGroup.archived_at.is_(None))
    ).all() if group_ids else []
    if len(groups) != len(group_ids):
        raise ValueError("all group IDs must reference active groups")
    by_id = {group.id: group for group in groups}
    ordered = [by_id[group_id] for group_id in group_ids]
    if sum(group.kind == "priority" for group in ordered) > 1:
        raise ValueError("a material can have at most one priority group")
    return ordered


def create_group(session, name: object, kind: object, priority_rank: object = None) -> ContentGroup:
    name, kind, priority_rank = validate_group_values(name, kind, priority_rank)
    row = ContentGroup(name=name, kind=kind, priority_rank=priority_rank)
    session.add(row)
    session.flush()
    return row


def update_group(session, group: ContentGroup, **changes) -> ContentGroup:
    if group.archived_at is not None:
        raise RuntimeError("archived group cannot be edited")
    values = {
        "name": changes.get("name", group.name),
        "kind": changes.get("kind", group.kind),
        "priority_rank": changes.get("priority_rank", group.priority_rank),
    }
    name, kind, priority_rank = validate_group_values(**values)
    group.name, group.kind, group.priority_rank = name, kind, priority_rank
    session.flush()
    return group


def _replace_memberships(session, target, membership_model, target_column, group_ids, *, source="manual", commit=True):
    group_ids = validate_group_ids(group_ids)
    if source not in MEMBERSHIP_SOURCES["feed" if isinstance(target, FeedItem) else "document"]:
        raise ValueError("invalid membership source")
    locked = session.execute(
        select(type(target)).where(type(target).id == target.id).with_for_update()
    ).scalar_one()
    groups = get_active_groups(session, group_ids)
    current = session.scalars(select(membership_model).where(target_column == target.id)).all()
    desired = set(group_ids)
    for membership in current:
        if membership.group_id not in desired:
            session.delete(membership)
        elif membership.source == "llm_suggestion" and source == "manual":
            membership.source = "manual"
            membership.source_suggestion_id = None
    existing = {membership.group_id for membership in current}
    for group in groups:
        if group.id not in existing:
            session.add(membership_model(**{target_column.key: target.id, "group_id": group.id, "source": source}))
    session.flush()
    if commit:
        session.commit()
    return locked


def replace_feed_item_groups(session, item: FeedItem, group_ids, *, source="manual", commit=True) -> FeedItem:
    return _replace_memberships(session, item, FeedItemGroupMembership, FeedItemGroupMembership.feed_item_id, group_ids, source=source, commit=commit)


def replace_document_groups(session, document: Document, group_ids, *, source="manual", commit=True) -> Document:
    return _replace_memberships(session, document, DocumentGroupMembership, DocumentGroupMembership.document_id, group_ids, source=source, commit=commit)


def replace_chunk_groups(session, chunk: DocumentChunk, group_ids, *, commit=True) -> DocumentChunk:
    """Replace manual categories of a reader chunk.

    A priority belongs to a whole material, so a chapter can only receive
    topic groups.
    """
    group_ids = validate_group_ids(group_ids)
    locked = session.execute(
        select(DocumentChunk).where(DocumentChunk.id == chunk.id).with_for_update()
    ).scalar_one()
    groups = get_active_groups(session, group_ids)
    if any(group.kind != "topic" for group in groups):
        raise ValueError("chapter categories must be topic groups")
    current = session.scalars(
        select(DocumentChunkGroupMembership).where(
            DocumentChunkGroupMembership.chunk_id == chunk.id,
        )
    ).all()
    desired = set(group_ids)
    for membership in current:
        if membership.group_id not in desired:
            session.delete(membership)
    existing = {membership.group_id for membership in current}
    for group in groups:
        if group.id not in existing:
            session.add(DocumentChunkGroupMembership(chunk_id=chunk.id, group_id=group.id))
    session.flush()
    if commit:
        session.commit()
    return locked


def group_usage_counts(session, group: ContentGroup) -> dict[str, int]:
    saved = session.scalar(
        select(func.count()).select_from(FeedItemGroupMembership).join(FeedItem).where(
            FeedItemGroupMembership.group_id == group.id, FeedItem.status == "saved_for_later"
        )
    ) or 0
    documents = session.scalar(
        select(func.count()).select_from(DocumentGroupMembership).where(DocumentGroupMembership.group_id == group.id)
    ) or 0
    chunks = session.scalar(
        select(func.count()).select_from(DocumentChunkGroupMembership).where(
            DocumentChunkGroupMembership.group_id == group.id,
        )
    ) or 0
    provenance = session.scalar(
        select(func.count()).select_from(FeedItemGroupMembership).where(FeedItemGroupMembership.group_id == group.id)
    ) or 0
    return {"saved_item_count": saved, "document_count": documents, "chunk_count": chunks, "provenance_item_count": provenance}


def archive_group(session, group: ContentGroup) -> ContentGroup:
    counts = group_usage_counts(session, group)
    if counts["saved_item_count"] or counts["document_count"] or counts["chunk_count"]:
        error = RuntimeError("group is in active use")
        error.counts = counts
        raise error
    group.archived_at = dt.datetime.now(dt.timezone.utc)
    group.updated_at = group.archived_at
    session.commit()
    return group


def group_to_dict(group: ContentGroup, session=None) -> dict:
    result = {
        "id": group.id,
        "name": group.name,
        "kind": group.kind,
        "priority_rank": group.priority_rank,
        "archived_at": group.archived_at.isoformat() if group.archived_at else None,
    }
    if session is not None:
        result.update(group_usage_counts(session, group))
    return result
