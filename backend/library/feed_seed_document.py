"""Deterministic, editable document seeds from feed items."""

from sqlalchemy import select

from library.db.models import Document, FeedItem, FeedSource
from library.document_service import DocumentService, ExistingDocumentError
from library.feed_monitor_service import copy_feed_groups_to_document


def seed_url(item_id: int) -> str:
    return f"lenie://seed/feed-item/{item_id}"


def build_seed_markdown(item, source_name, topic_names) -> str:
    date = item.published_at.strftime("%Y-%m-%d") if item.published_at else "brak daty"
    comment = (item.review_note or "").strip() or "(uzupełnij: co Cię zainteresowało i co zrobić dalej)"
    topics = ", ".join(topic_names) or "brak"
    return (
        f"# Zalążek: {item.title}\n\n"
        f"> Zalążek dokumentu z wpisu feedu #{item.id} ({source_name or 'nieznane źródło'}, {date}). "
        "Punkt wyjścia do dalszej pracy z LLM (ChatGPT / Claude Code).\n\n"
        f"## Co mnie zainteresowało i co dalej\n{comment}\n\n"
        f"## Źródło\n- URL: {item.url}\n- Opublikowano: {date}\n- Tematy: {topics}\n\n"
        f"## Streszczenie ze źródła\n{item.summary or '(brak streszczenia)'}\n\n"
        "## Do ustalenia\n"
        "- [ ] Czy to wymaga osobnego dokumentu lub notatki?\n"
        "- [ ] Co jeszcze sprawdzić w źródle?\n"
    )


def seed_document_ids(session, item_ids) -> dict[int, int]:
    urls = {seed_url(item_id): item_id for item_id in item_ids}
    if not urls:
        return {}
    rows = session.execute(select(Document.id, Document.url).where(
        Document.url.in_(urls), Document.document_type == "text",
    )).all()
    return {urls[url]: document_id for document_id, url in rows}


def create_seed_document(session, item_id: int) -> tuple[Document, bool]:
    item = session.get(FeedItem, item_id)
    if item is None:
        raise ValueError("feed item not found")
    source = session.get(FeedSource, item.feed_source_id)
    topics = sorted({
        membership.group.name for membership in item.group_memberships
        if membership.group.kind == "topic" and membership.group.archived_at is None
    }, key=lambda name: (name.casefold(), name))
    markdown = build_seed_markdown(item, source.name if source else None, topics)
    try:
        document = DocumentService(session).create_document(
            url=seed_url(item_id), url_type="text", title=f"Zalążek: {item.title}"[:200],
            note=f"Zalążek z wpisu feedu #{item.id}: {item.url}", source="own", language="pl",
        )
    except ExistingDocumentError as exc:
        return exc.document, False
    document.text_md = document.text = markdown
    copy_feed_groups_to_document(session, [item], document, "feed_import")
    session.commit()
    return document, True
