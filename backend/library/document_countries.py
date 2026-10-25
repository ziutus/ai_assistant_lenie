"""Standalone document country detection and country-tag presentation."""

from library import article_tagging
from library.country_gazetteer import slug_to_name
from library.db.models import Document


def countries_from_tags(tags: str | None) -> list[dict[str, str]]:
    """Present country tags using the same bare slugs as the reader endpoints."""
    slugs = dict.fromkeys(
        tag.strip()[5:] for tag in (tags if isinstance(tags, str) else "").split(",")
        if tag.strip().startswith("kraj-") and tag.strip()[5:]
    )
    return [{"slug": slug, "name_pl": slug_to_name(slug) or slug} for slug in slugs]


def detect_document_countries(session, doc_id: int) -> dict:
    """Detect and merge countries without replacing any existing document tags."""
    doc = Document.get_by_id(session, doc_id)
    if doc is None:
        raise LookupError("Document not found")
    text = doc.text_md or doc.text or ""
    if not text.strip():
        raise ValueError("Document has no text content")

    from library.entity_service import apply_channel_glossary_text

    # Channel euphemisms ("państwo z gwiazdką" = Izrael) are resolved on a copy of the text.
    text = apply_channel_glossary_text(session, doc_id, text)
    detected = article_tagging.extract_countries_hybrid(text, doc.title or "")
    existing = list(dict.fromkeys(t.strip() for t in (doc.tags or "").split(",") if t.strip()))
    seen = set(existing)
    added = []
    for tag in detected:
        if tag.startswith("kraj-") and tag[5:] and tag not in seen:
            existing.append(tag)
            seen.add(tag)
            added.append(tag[5:])
    doc.tags = ",".join(existing)
    countries = countries_from_tags(doc.tags)
    session.commit()
    return {"countries": countries, "added": added}
