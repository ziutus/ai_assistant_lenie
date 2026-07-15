"""Extract and persist where a document's reporting/information originated."""

import json
import logging
import re
from urllib.parse import urlparse

from sqlalchemy import delete, func, select

from library.db.models import (
    DocumentInformationSource,
    InformationSource,
    InformationSourceAlias,
)

logger = logging.getLogger(__name__)

ALLOWED_ROLES = {"original_reporting", "cited", "republication", "data_source"}


def publisher_domain(url: str) -> str | None:
    host = (urlparse(url or "").hostname or "").lower()
    return host.removeprefix("www.") or None


def _json_array(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("LLM response contains no JSON array")
    value = json.loads(match.group())
    if not isinstance(value, list):
        raise ValueError("LLM response is not a JSON array")
    return [item for item in value if isinstance(item, dict)]


def extract_information_sources(text: str, title: str, model: str) -> list[dict]:
    """Use the LLM to classify explicitly attributed sources in an article."""
    from library.chunk_llm_analysis import call_model

    prompt = f"""Wykryj źródła informacji jawnie wymienione w artykule.
Nie wpisuj autora artykułu ani portalu publikującego, jeśli nie jest on źródłem cytowanych ustaleń.
Rozróżnij role:
- original_reporting: artykuł przypisuje źródłu pierwotne ustalenia/śledztwo,
- cited: źródło jest cytowane lub przywołane,
- republication: tekst jest przedrukiem lub opracowaniem materiału źródła,
- data_source: raport, urząd, badanie albo baza dostarczająca dane.

Ujednolicaj nazwy (np. WSJ -> The Wall Street Journal), ale raw_mention zachowaj tak jak w tekście.
evidence_excerpt musi być dokładnym, krótkim cytatem z tekstu potwierdzającym relację.
Zwróć wyłącznie JSON:
[{{"canonical_name":"...", "raw_mention":"...", "role":"original_reporting|cited|republication|data_source",
   "source_type":"newspaper|portal|agency|institution|report|database|other",
   "domain":null, "evidence_excerpt":"...", "confidence":0}}]
Pomiń niepewne pozycje poniżej confidence 60. Nie dopowiadaj domen ani URL-i.

Tytuł: {title}
Tekst:
{text}"""
    raw, _ = call_model(prompt, model, max_tokens=1200)
    candidates = _json_array(raw)
    result = []
    for item in candidates:
        name = str(item.get("canonical_name") or "").strip()
        mention = str(item.get("raw_mention") or "").strip()
        evidence = str(item.get("evidence_excerpt") or "").strip()
        role = item.get("role")
        try:
            confidence = max(0, min(100, int(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0
        # Grounding guard: never persist an invented quote/name.
        if (not name or not mention or role not in ALLOWED_ROLES or confidence < 60
                or mention.lower() not in text.lower() or evidence not in text):
            continue
        result.append({
            "canonical_name": name,
            "raw_mention": mention,
            "role": role,
            "source_type": str(item.get("source_type") or "other")[:30],
            "domain": (str(item.get("domain")).strip() if item.get("domain") else None),
            "evidence_excerpt": evidence,
            "confidence": confidence,
        })
    return result


def _find_source(session, canonical_name: str) -> InformationSource | None:
    lowered = canonical_name.lower()
    source = session.scalar(select(InformationSource).where(
        func.lower(InformationSource.canonical_name) == lowered
    ))
    if source is not None:
        return source
    alias = session.scalar(select(InformationSourceAlias).where(
        func.lower(InformationSourceAlias.alias) == lowered
    ))
    return alias.source if alias is not None else None


def _get_or_create_source(session, item: dict) -> InformationSource:
    source = _find_source(session, item["canonical_name"])
    if source is None:
        source = InformationSource(
            canonical_name=item["canonical_name"],
            source_type=item.get("source_type"),
            domain=item.get("domain"),
        )
        session.add(source)
        session.flush()
    elif not source.domain and item.get("domain"):
        source.domain = item["domain"]
    mention = item.get("raw_mention", "").strip()
    known = {a.alias.lower() for a in source.aliases}
    if mention and mention.lower() != source.canonical_name.lower() and mention.lower() not in known:
        session.add(InformationSourceAlias(source=source, alias=mention))
    return source


def refresh_document_information_sources(session, doc, text: str, model: str) -> dict:
    """Replace document provenance links, always including the URL publisher."""
    session.execute(delete(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc.id
    ))

    created = []
    domain = publisher_domain(doc.url)
    if domain:
        publisher_item = {
            "canonical_name": domain,
            "raw_mention": domain,
            "source_type": "portal",
            "domain": domain,
        }
        publisher = _get_or_create_source(session, publisher_item)
        session.add(DocumentInformationSource(
            document_id=doc.id,
            source_id=publisher.id,
            role="publisher",
            raw_mention=domain,
            source_url=doc.url,
            evidence_excerpt=None,
            confidence=100,
            extraction_method="url",
            review_status="auto_accepted",
        ))
        created.append((publisher.canonical_name, "publisher"))

    try:
        candidates = extract_information_sources(text, doc.title or "", model)
    except Exception:
        logger.exception("information-source LLM extraction failed for document %s", doc.id)
        candidates = []

    seen = {(name.lower(), role) for name, role in created}
    for item in candidates:
        source = _get_or_create_source(session, item)
        key = (source.canonical_name.lower(), item["role"])
        if key in seen:
            continue
        seen.add(key)
        session.add(DocumentInformationSource(
            document_id=doc.id,
            source_id=source.id,
            role=item["role"],
            raw_mention=item["raw_mention"],
            source_url=None,
            evidence_excerpt=item["evidence_excerpt"],
            confidence=item["confidence"],
            extraction_method="llm",
            review_status="auto_accepted" if item["confidence"] >= 80 else "needs_review",
        ))
        created.append((source.canonical_name, item["role"]))
    return {"sources": created}
