"""Extract and persist where a document's reporting/information originated."""

import json
import logging
import re
from urllib.parse import urlparse

from sqlalchemy import delete, func, select

from library.db.models import (
    DocumentEntity,
    DocumentInformationSource,
    DocumentOrganization,
    InformationSource,
    InformationSourceAlias,
)

logger = logging.getLogger(__name__)

ALLOWED_ROLES = {"original_reporting", "cited", "republication", "data_source"}
ALLOWED_RELATION_PREDICATES = {"issued_statement", "reported_by", "cited_by", "data_provided_to"}

KNOWN_REPORTING_SOURCES = (
    {
        "canonical_name": "AFP",
        "source_type": "agency",
        "domain": "afp.com",
        "aliases": ("AFP", "agencja AFP", "Agence France-Presse"),
    },
    {
        "canonical_name": "France24",
        "source_type": "broadcaster",
        "domain": "france24.com",
        "aliases": ("France24", "France 24"),
    },
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
    r"\bpodają|\binformują|\bdonoszą|"
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
            canonical_name, variants, organization_id = organization, [organization], None
        else:
            canonical_name = str(organization.get("text") or organization.get("canonical_name") or "").strip()
            variants = [
                str(value).strip()
                for value in [canonical_name, *(organization.get("variants") or [])]
                if str(value).strip()
            ]
            organization_id = organization.get("organization_id")
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
            suffix = sentence[match.end():]
            # "EDF poinformował ... — podają AFP" must not turn EDF into a
            # reporting outlet.  The later attribution belongs to the outlets
            # after "podają", which SOURCE_PREFIX will match when their own
            # mentions are visited below.  Keep the suffix form for ordinary
            # "AFP poinformowała", where no later attribution redirects it.
            later_reporting_attribution = re.search(
                r"(?:[-–—]\s*)?podaj(?:e|ą)\s+", suffix, re.IGNORECASE,
            )
            if not (SOURCE_PREFIX.search(prefix_clause)
                    or (SOURCE_SUFFIX.search(suffix) and not later_reporting_attribution)):
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
                "organization_id": organization_id,
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
    match = re.search(r"\[", raw)
    try:
        # raw_decode intentionally accepts harmless prose after the first JSON
        # value. Some providers append a short explanation despite the prompt.
        value, _ = json.JSONDecoder().raw_decode(raw[match.start():]) if match else (None, 0)
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


def analyze_source_relationships(quote: str, model: str, candidates: list[str]) -> list[dict]:
    """Suggest grounded source-chain relations for one reviewer-selected quote.

    Suggestions remain transient: an LLM result must never alter the graph
    until a reviewer gets an explicit accept/reject action.
    """
    # Keep matching strict while tolerating presentation-only differences such
    # as "France 24" vs "France24" or markdown emphasis.
    def compact(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)

    quote_compact = compact(quote)
    candidates_by_compact = {compact(candidate): candidate for candidate in candidates if compact(candidate)}
    # Try deterministic patterns before spending an LLM call.  Both endpoints
    # must already be known document entities and occur verbatim in the quote.
    reporting_match = re.search(r"(?:[-–—]\s*)?podaj(?:ą|e)\s+(.+)", quote, re.IGNORECASE | re.DOTALL)
    if reporting_match:
        before_reporting = quote[:reporting_match.start()]
        after_reporting = reporting_match.group(1)
        reporters = [
            canonical for compact_name, canonical in candidates_by_compact.items()
            if compact_name in compact(after_reporting)
        ]
        deterministic_result = []
        for compact_name, canonical in candidates_by_compact.items():
            if compact_name not in compact(before_reporting):
                continue
            escaped = re.escape(canonical)
            if not re.search(
                rf"(?:w\s+komunikacie\s+)?{escaped}\s+(?:poinformował|poinformowała|poinformowali|oświadczył|oświadczyła)",
                before_reporting,
                re.IGNORECASE,
            ):
                continue
            deterministic_result.extend({
                "subject": canonical,
                "predicate": "issued_statement",
                "object": reporter,
                "evidence_excerpt": quote,
                "confidence": 95,
            } for reporter in reporters if reporter != canonical)
        if deterministic_result:
            return deterministic_result

    from library.chunk_llm_analysis import call_model
    candidate_list = "\n".join(f"- {candidate}" for candidate in candidates)
    prompt = f"""Przeanalizuj wyłącznie zaznaczony cytat pod kątem relacji
pochodzenia informacji. Zwróć relację tylko wtedy, gdy można ją obronić
dosłownym fragmentem tego cytatu. Nie używaj wiedzy spoza cytatu.

Subject i object mogą być wyłącznie pozycjami z listy znanych podmiotów.
Nie wpisuj zdarzeń, przedmiotów, miejsc, ani opisów czynności jako subject lub object.

Znane podmioty:
{candidate_list}

Kierunek relacji:
- issued_statement: organizacja/osoba wydała komunikat, który medium podaje,
- reported_by: źródło pierwotne jest relacjonowane przez medium/agencję,
- cited_by: medium lub źródło jest przywołane przez publikację,
- data_provided_to: instytucja dostarczyła dane medium.

Zwróć wyłącznie JSON:
[{{"subject":"...", "predicate":"issued_statement|reported_by|cited_by|data_provided_to",
   "object":"...", "evidence_excerpt":"...", "confidence":0}}]

subject, object i evidence_excerpt muszą występować dosłownie w cytacie.
Pomiń relację, jeśli cytat nie wskazuje jej jednoznacznie albo confidence < 60.

Cytat:
{quote}"""
    raw, _ = call_model(prompt, model, max_tokens=900, operation="source_relationship_analysis")
    result = []
    for item in _json_array(raw):
        subject = str(item.get("subject") or "").strip()
        predicate = str(item.get("predicate") or "").strip()
        object_name = str(item.get("object") or "").strip()
        evidence = str(item.get("evidence_excerpt") or "").strip()
        try:
            confidence = max(0, min(100, int(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0
        if (predicate not in ALLOWED_RELATION_PREDICATES or confidence < 60
                or not subject or not object_name or not evidence
                or compact(subject) not in quote_compact or compact(object_name) not in quote_compact
                or compact(subject) not in candidates_by_compact or compact(object_name) not in candidates_by_compact
                or compact(evidence) not in quote_compact):
            continue
        result.append({
            "subject": candidates_by_compact[compact(subject)], "predicate": predicate,
            "object": candidates_by_compact[compact(object_name)],
            "evidence_excerpt": evidence, "confidence": confidence,
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


def _find_source_by_organization(session, organization_id: int) -> InformationSource | None:
    return session.scalar(select(InformationSource).where(InformationSource.organization_id == organization_id))


def _get_or_create_source(session, item: dict) -> InformationSource:
    organization_id = item.get("organization_id")
    if organization_id is not None:
        # This source IS an organization already resolved via the
        # organizations registry (library/organization_registry.py) — resolve
        # by that FK, not by name, and don't maintain a second, independent
        # alias set: name variants already live in organization_aliases.
        # See docs/organization-ner-alias-plan.md, "Ustalenia z review".
        source = _find_source_by_organization(session, organization_id)
        if source is None:
            # A source may have been created before the organization registry
            # existed.  Reuse that canonical-name row and attach its missing FK
            # instead of attempting an INSERT that violates canonical_name's
            # global uniqueness (e.g. an existing legacy "MSZ" source).
            source = _find_source(session, item["canonical_name"])
        if source is None:
            source = InformationSource(
                canonical_name=item["canonical_name"],
                source_type=item.get("source_type"),
                domain=item.get("domain"),
                organization_id=organization_id,
            )
            session.add(source)
            session.flush()
        else:
            if source.organization_id is None:
                source.organization_id = organization_id
            if not source.domain and item.get("domain"):
                source.domain = item["domain"]
        return source

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
    """Refresh automatic provenance links without deleting human approvals."""
    from library.relationship_audit import audit_removals

    removable = session.execute(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc.id,
        DocumentInformationSource.review_status != "approved",
    )).scalars().all()
    audit_removals(session, doc.id, "information_source", "llm_refresh", removable, lambda row: {
        "source_id": row.source_id, "role": row.role, "raw_mention": row.raw_mention,
        "review_status": row.review_status, "extraction_method": row.extraction_method,
    })
    for row in removable:
        session.delete(row)

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
    organization_ids_by_entity = {
        link.document_entity_id: link.organization_id
        for link in session.execute(select(DocumentOrganization).where(
            DocumentOrganization.document_id == doc.id,
        )).scalars().all()
    }
    candidates = extract_ner_cited_sources(text, [
        {
            "text": row.entity_text,
            "variants": row.variants or [],
            "organization_id": organization_ids_by_entity.get(row.id),
        }
        for row in organization_rows
    ])
    candidates.extend(extract_known_reporting_sources(text))
    try:
        llm_candidates = extract_information_sources(text, doc.title or "", model)
    except Exception:
        logger.exception("information-source LLM extraction failed for document %s", doc.id)
        llm_candidates = []
    candidates.extend(_normalize_known_source(item) for item in llm_candidates)

    approved_links = session.execute(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc.id,
        DocumentInformationSource.review_status == "approved",
    )).scalars().all()
    seen = {(name.lower(), role) for name, role in created}
    seen.update((link.source.canonical_name.lower(), link.role) for link in approved_links)
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


def refresh_rule_based_sources(session, doc, items: list[dict]) -> dict:
    """Persist deterministic (non-LLM) source links detected during article
    cleanup — e.g. Interia's recurring "bliżej świata" foreign-source
    attribution paragraph (`library/article_cleaner.py`), which is stripped
    from the article text at cleanup time, before `refresh_document_information_sources()`
    (the LLM step) ever runs over it. Additive/idempotent: only replaces rows
    from this same extraction method, leaving publisher/LLM/NER links intact.
    """
    from library.relationship_audit import audit_removals
    removable = session.execute(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc.id,
        DocumentInformationSource.extraction_method == "rule",
        DocumentInformationSource.review_status != "approved",
    )).scalars().all()
    audit_removals(session, doc.id, "information_source", "rule_refresh", removable, lambda row: {
        "source_id": row.source_id, "role": row.role, "raw_mention": row.raw_mention,
        "review_status": row.review_status, "extraction_method": row.extraction_method,
    })
    for row in removable:
        session.delete(row)
    created = []
    for item in items:
        source = _get_or_create_source(session, item)
        session.add(DocumentInformationSource(
            document_id=doc.id,
            source_id=source.id,
            role=item["role"],
            raw_mention=item["raw_mention"],
            source_url=None,
            evidence_excerpt=item.get("evidence_excerpt"),
            confidence=item["confidence"],
            extraction_method="rule",
            review_status="auto_accepted",
        ))
        created.append((source.canonical_name, item["role"]))
    return {"sources": created}


def refresh_ner_cited_sources(session, doc, text: str, organizations: list[dict]) -> dict:
    """Refresh only cheap NER/context source links, preserving URL and LLM provenance."""
    from library.relationship_audit import audit_removals
    removable = session.execute(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == doc.id,
        DocumentInformationSource.extraction_method == "ner_context_rule",
        DocumentInformationSource.review_status != "approved",
    )).scalars().all()
    audit_removals(session, doc.id, "information_source", "ner_refresh", removable, lambda row: {
        "source_id": row.source_id, "role": row.role, "raw_mention": row.raw_mention,
        "review_status": row.review_status, "extraction_method": row.extraction_method,
    })
    for row in removable:
        session.delete(row)
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
