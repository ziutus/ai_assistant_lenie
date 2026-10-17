"""Canonical input for document NER and entity enrichment."""

from library.transcript_chapter_boundaries import parse_sections, resolve_chapter_types


def document_ner_text(doc) -> str:
    """Exclude typed transcript chapters only when types align with Document.text."""
    base = doc.text_md or doc.text or ""
    if doc.text_md:
        return base
    types = resolve_chapter_types(base, getattr(doc, "chapter_types", None))
    if not any(chapter_type != "TEMAT" for chapter_type in types):
        return base
    kept = []
    chapter = iter(types)
    for section in parse_sections(base):
        if not section.heading or next(chapter) == "TEMAT":
            content = (section.heading + section.body).strip()
            if content:
                kept.append(content)
    return "\n\n".join(kept)
