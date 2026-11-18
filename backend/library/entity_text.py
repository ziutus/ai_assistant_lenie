"""Canonical input for document NER and entity enrichment."""

from library.transcript_chapter_boundaries import parse_sections, resolve_chapter_types


def _without_author_block(base: str, doc) -> str:
    if getattr(doc, "document_type", None) not in ("webpage", "link"):
        return base
    from library.author_biography import extract_trailing_author_biography, split_author_block

    byline = getattr(doc, "byline", None)
    if byline:
        body, block = extract_trailing_author_biography(base, byline)
        if block is not None:
            return body
    return split_author_block(base)[0]


def document_ner_text(doc) -> str:
    """Exclude portal author blocks or typed chapters without changing the document."""
    base = doc.text_md or doc.text or ""
    if doc.text_md:
        return _without_author_block(base, doc)
    types = resolve_chapter_types(base, getattr(doc, "chapter_types", None))
    if not any(chapter_type != "TEMAT" for chapter_type in types):
        return _without_author_block(base, doc)
    kept = []
    chapter = iter(types)
    for section in parse_sections(base):
        if not section.heading or next(chapter) == "TEMAT":
            content = (section.heading + section.body).strip()
            if content:
                kept.append(content)
    return "\n\n".join(kept)
