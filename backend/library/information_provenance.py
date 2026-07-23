"""Extract and persist where a document's reporting/information originated."""

import json
import logging
import re
from urllib.parse import urlparse

from sqlalchemy import delete, func, select

from library.db.models import (
    DocumentEntity,
    DocumentInformationSource,
    InformationSource,
    InformationSourceAlias,
)

logger = logging.getLogger(__name__)

ALLOWED_ROLES = {"original_reporting", "cited", "republication", "data_source"}

KNOWN_REPORTING_SOURCES = (
    {
        "canonical_name": "The New York Times",
        "source_type": "newspaper",
        "domain": "nytimes.com",
        "aliases": ("The New York Times", "New York Times", "NYT"),
    },
)

# These verbs are deliberately conservative: a bare mention of a newspaper is
# not enough to claim that the document is based on its reporting.
REPORTING_VERBS = re.compile(
    r"\b(?:ujawni(?:ł|ła|ło)|ustali(?:ł|ła|ło)|poda(?:ł|ła|ło)|opisa(?:ł|ła|ło)|"
    r"donosi(?:ł|ła)?|informuje|poinformowa(?:ł|ła|ło)|napisa(?:ł|ła|ło))\b",
    re.IGNORECASE,
)

SOURCE_PREFIX = re.compile(
    r"(?:\bwedług|\bzdaniem|\bza\b|\bjak\s+(?:podaje|informuje|donosi)|"
    r"\bpowołując\s+się\s+na|\bna\s+podstawie|\bdane\s+(?:od|z))\b.{0,100}$",
    re.IGNORECASE | re.DOTALL,
)
SOURCE_SUFFIX = re.compile(
    r"^\s*(?:,?\s*)?(?:podaje|podają|informuje|informują|donosi|donoszą|"
    r"poinformował(?:a|o)?|ustalił(?:a|o)?|ujawnił(?:a|o)?)\b",
    re.IGNORECASE,
)
KNOWN_ORGANIZATION_SOURCES = {
    "bloomberg": {"canonical_name": "Bloomberg", "source_type": "agency", "domain": "bloomberg.com"},
    "kcna": {"canonical_name": "KCNA", "source_type": "agency", "domain": "kcna.kp"},
}


def publisher_domain(url: str) -> str | None:
    host = (urlparse(url or "").hostname or "").lower()
    return host.removeprefix("www.") or None


def extract_known_reporting_sources(text: str) -> list[dict]:
    """Detect well-known reporting sources using grounded, conservative rules."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    result = []
    for known in KNOWN_REPORTING_SOURCES:
        for sentence in sentences:
            mention = next((
                alias for alias in known["aliases"]
                if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", sentence, re.IGNORECASE)
            ), None)
            if mention and REPORTING_VERBS.search(sentence):
                result.append({
                    "canonical_name": known["canonical_name"],
                    "raw_mention": mention,
                    "role": "original_reporting",
                    "source_type": known["source_type"],
                    "domain": known["domain"],
                    "evidence_excerpt": sentence.strip(),
                    "confidence": 100,
                    "extraction_method": "rule",
                })
                break
    return result


def extract_ner_cited_sources(text: str, organizations: list[dict] | list[str]) -> list[dict]:
    """Classify NER organizations as cited sources using grounded attribution phrases."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    result: list[dict] = []
    seen: set[str] = set()
    for organization in organizations:
        if isinstance(organization, str):
            canonical_name, variants = organization, [organization]
        else:
            canonical_name = str(organization.get("text") or organization.get("canonical_name") or "").strip()
            variants = [
                str(value).strip()
                for value in [canonical_name, *(organization.get("variants") or [])]
                if str(value).strip()
            ]
        if not canonical_name:
            continue
        for sentence in sentences:
            match = next((
                match
                for variant in variants
                if (match := re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", sentence, re.IGNORECASE))
            ), None)
            if match is None:
                continue
            prefix_clause = re.split(r"[,;:]", sentence[:match.start()])[-1]
            if not (SOURCE_PREFIX.search(prefix_clause) or SOURCE_SUFFIX.search(sentence[match.end():])):
                continue
            known = KNOWN_ORGANIZATION_SOURCES.get(canonical_name.casefold(), {})
            normalized_name = known.get("canonical_name", canonical_name)
            key = normalized_name.casefold()
            if key in seen:
                break
            seen.add(key)
            result.append({
                "canonical_name": normalized_name,
                "raw_mention": match.group(0),
                "role": "cited",
                "source_type": known.get("source_type", "organization"),
                "domain": known.get("domain"),
                "evidence_excerpt": sentence[:1000],
                "confidence": 90,
                "extraction_method": "ner_context_rule",
            })
            break
    return result


def _normalize_known_source(item: dict) -> dict:
    """Map LLM spelling variants onto the same canonical source record."""
    names = {
        str(item.get("canonical_name") or "").strip().lower(),
        str(item.get("raw_mention") or "").strip().lower(),
    }
    for known in KNOWN_REPORTING_SOURCES:
        if names & {alias.lower() for alias in known["aliases"]}:
            return {
                **item,
                "canonical_name": known["canonical_name"],
                "source_type": known["source_type"],
                "domain": known["domain"],
            }
    return item


def _json_array(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    try:
        value = json.loads(match.group()) if match else None
    except json.JSONDecodeError:
        value = None
    if value is None:
        # Odpowiedź bywa ucięta limitem tokenów — odzyskaj kompletne obiekty
        # z prefiksu tablicy (ten sam mechanizm co przy wydarzeniach).
        from library.timeline_events import _complete_array_prefix

        repaired = _complete_array_prefix(raw)
        if repaired is None:
            raise ValueError("LLM response contains no recoverable JSON array")
        value = json.loads(repaired)
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
    # 1200 tokenów nie starczało na artykuły z długą listą źródeł — odpowiedź
    # była ucinana w połowie obiektu JSON.
    raw, _ = call_model(prompt, model, max_tokens=2400, operation="information_provenance")
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

    organization_rows = session.execute(select(DocumentEntity).where(
        DocumentEntity.document_id == doc.id,
        DocumentEntity.entity_type == "orgName",
    )).scalars().all()
    candidates = extract_ner_cited_sources(text, [
        {"text": row.entity_text, "variants": row.variants or []}
        for row in organization_rows
    ])
    candidates.extend(extract_known_reporting_sources(text))
    try:
        llm_candidates = extract_information_sources(text, doc.title or "", model)
    except Exception:
        logger.exception("information-source LLM extraction failed for document %s", doc.id)
        llm_candidates = []
    candidates.extend(_normalize_known_source(item) for item in llm_candidates)

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
            extraction_method=item.get("extraction_method", "llm"),
            review_status="auto_accepted" if item["confidence"] >= 80 else "needs_review",
        ))
        created.append((source.canonical_name, item["role"]))
    return {"sources": created}


def refresh_ner_cited_sources(session, doc, text: str, organizations: list[dict]) -> dict:
    """Refresh only cheap NER/context source links, preserving URL and LLM provenance."""
    session.execute(delete(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc.id,
        DocumentInformationSource.extraction_method == "ner_context_rule",
    ))
    created = []
    for item in extract_ner_cited_sources(text, organizations):
        source = _get_or_create_source(session, item)
        existing = session.scalar(select(DocumentInformationSource).where(
            DocumentInformationSource.document_id == doc.id,
            DocumentInformationSource.source_id == source.id,
            DocumentInformationSource.role == "cited",
        ))
        if existing is not None:
            continue
        session.add(DocumentInformationSource(
            document_id=doc.id,
            source_id=source.id,
            role="cited",
            raw_mention=item["raw_mention"],
            source_url=None,
            evidence_excerpt=item["evidence_excerpt"],
            confidence=item["confidence"],
            extraction_method="ner_context_rule",
            review_status="auto_accepted",
        ))
        created.append(source.canonical_name)
    return {"sources": created}
