"""Persist NER entities (persons/places) per document — MVP of docs/ner-integration-plan.md.

Sits between the NER client (library/ner_client.py) and the document_entities
table: extract → aggregate by (type, base form) → replace the document's rows.
Entities are derived data, so a refresh replaces previous rows instead of
merging (unlike doc.tags, which accumulates across runs) — except rows with
source='manual' (set by merge_document_entities()), which survive a refresh.
"""

import datetime
import logging
import re

from sqlalchemy import delete, func, select, update

from library.db.models import (
    Document,
    DocumentEntity,
    DocumentOrganization,
    NerContextClassification,
    NerExclusion,
    NerTemporalCandidate,
)
from library.ner_client import NERServiceUnavailable, aggregate_entities_detailed, extract_entities, is_available
from library.ner_normalization import normalize_ner_text
from library.organization_registry import (
    CONFIDENCE_CONTEXT_LLM_MATCHED,
    ambiguous_alias_candidates,
    merge_ner_groups,
    resolve_or_create,
    select_ambiguous_alias_candidate_with_llm,
)

logger = logging.getLogger(__name__)
TEMPORAL_CONTEXT_WINDOW = 220
COMPACT_DATE_RE = re.compile(
    r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[0-2])"
    r"(?:[./-](?:\d{2}|\d{4}))?(?!\d)"
)


def _temporal_candidate_rows(document_id: int, text: str, raw: list[dict]) -> list[NerTemporalCandidate]:
    """Locate raw NER date/time mentions in the canonical text with local context."""
    lowered = text.casefold()
    cursors: dict[str, int] = {}
    located: list[tuple[int, int, str, str, str | None]] = [
        (match.start(), match.end(), "date", match.group(0), match.group(0))
        for match in COMPACT_DATE_RE.finditer(text)
    ]
    for entity in raw:
        entity_type = entity.get("label")
        raw_text = normalize_ner_text(entity.get("text") or "")
        if entity_type not in {"date", "time"} or not raw_text:
            continue
        key = raw_text.casefold()
        start = lowered.find(key, cursors.get(key, 0))
        if start < 0:
            start = lowered.find(key)
        if start >= 0:
            cursors[key] = start + len(raw_text)
            end = start + len(raw_text)
            if any(start < known_end and end > known_start for known_start, known_end, *_ in located):
                continue
        else:
            end = start
        located.append((
            start, end, entity_type, raw_text,
            normalize_ner_text(entity.get("lemma") or "") or None,
        ))

    rows = []
    for start, end, entity_type, raw_text, lemma in sorted(located, key=lambda item: item[0]):
        excerpt = (
            text[max(0, start - TEMPORAL_CONTEXT_WINDOW):min(len(text), end + TEMPORAL_CONTEXT_WINDOW)].strip()
            if start >= 0 else raw_text
        )
        rows.append(NerTemporalCandidate(
            document_id=document_id,
            entity_type=entity_type,
            raw_text=raw_text,
            lemma=lemma,
            char_start=start if start >= 0 else None,
            context_excerpt=excerpt,
        ))
    return rows


def _record_ner_availability(session, document_id: int, *, unavailable: bool) -> None:
    """Persist doc.ner_unavailable_at immediately (own commit) — see its column comment.

    Committed independently of the caller's transaction so the flag survives
    even when the caller rolls back after refresh_document_entities raises
    (e.g. a caller's except block).
    """
    value = datetime.datetime.utcnow() if unavailable else None
    values = {"ner_unavailable_at": value}
    if not unavailable:
        values["entities_checked_at"] = datetime.datetime.now()
    session.execute(
        update(Document).where(Document.id == document_id).values(**values),
    )
    session.commit()


def is_excluded(exclusions: list[NerExclusion], entity_type: str, entity_text: str,
                author: str | None, raw_terms: list[str] | None = None) -> bool:
    """True when an exclusion rule suppresses this entity.

    Matching is case-insensitive on the normalized base form and, when
    provided, its raw lemmas/surface variants. entity_type='*' matches all
    types; geogName/placeName rules remain interchangeable after place-label
    merging; scope='author' only applies when the document's author matches.
    """
    candidate_keys = {
        normalize_ner_text(value).casefold()
        for value in [entity_text, *(raw_terms or [])]
        if normalize_ner_text(value)
    }
    author_lower = normalize_ner_text(author or "").casefold()
    matching_types = {entity_type}
    if entity_type in {"geogName", "placeName"}:
        matching_types.update({"geogName", "placeName"})
    for exc in exclusions:
        if exc.entity_type != "*" and exc.entity_type not in matching_types:
            continue
        if normalize_ner_text(exc.entity_text).casefold() not in candidate_keys:
            continue
        if exc.scope == "global":
            return True
        if (
            exc.scope == "author"
            and author_lower
            and normalize_ner_text(exc.author or "").casefold() == author_lower
        ):
            return True
    return False


def refresh_document_entities(session, document_id: int, text: str) -> list[DocumentEntity]:
    """Run NER on text and replace the document's rows in document_entities.

    Queues the changes on the session without committing (caller owns the
    transaction) and returns the new DocumentEntity rows. When the raw
    extraction comes back empty, a cheap /healthz probe (ner_client.is_available)
    tells apart two cases — genuinely no entities (probe OK: clears any stale
    doc.ner_unavailable_at, returns []) vs. the service being down (probe
    fails: sets doc.ner_unavailable_at and raises NERServiceUnavailable). Both
    of those writes commit immediately, independent of the caller's
    transaction, so the flag survives even when the caller rolls back on the
    raised exception (e.g. a caller's except block). Existing
    document_entities rows are left untouched on both empty-extraction paths —
    "no fresh data" must never erase previously detected entities. Entities
    matched by an ner_exclusions rule (global, or author-scoped for the
    document's author) are dropped before persisting — they never reach
    person resolution or place verification. Rows with source='manual'
    (merge_document_entities()) are never deleted; a fresh NER group that
    collides with one is dropped instead of inserted.
    """
    # Entity refresh replaces a document's derived rows. It can be triggered by
    # the explicit Entities screen while the analysis worker is enriching the
    # same document. Serialize those refreshes across all application processes
    # before calling NER/LLM helpers; otherwise their deletes can deadlock.
    # The transaction-scoped PostgreSQL lock is released by the caller's commit
    # or rollback, matching this function's existing transaction contract.
    session.execute(select(func.pg_advisory_xact_lock(22_004, document_id)))

    raw = extract_entities(text)
    if not raw:
        if is_available():
            _record_ner_availability(session, document_id, unavailable=False)
            return []
        _record_ner_availability(session, document_id, unavailable=True)
        raise NERServiceUnavailable(f"NER service unreachable while refreshing entities for document {document_id}")

    # Success: clear a stale unavailable flag as part of the caller's own
    # transaction (no isolated commit needed — unlike the branches above,
    # there is no exception here for the caller to roll back).
    doc = session.get(Document, document_id)
    if doc is not None:
        if doc.ner_unavailable_at is not None:
            doc.ner_unavailable_at = None
        doc.entities_checked_at = datetime.datetime.now()

    groups = aggregate_entities_detailed(raw)

    # spaCy can miss outlet names containing digits (for example "France24").
    # Promote only known reporting sources that occur in an explicit grounded
    # attribution phrase; this is a deterministic NER supplement, not a guess.
    from library.information_provenance import extract_known_reporting_sources
    for source in extract_known_reporting_sources(text):
        key = ("orgName", source["canonical_name"])
        existing = groups.get(key)
        if existing is None:
            groups[key] = {"count": 1, "variants": [source["raw_mention"]]}
        else:
            existing["count"] += 1
            if source["raw_mention"] not in existing["variants"]:
                existing["variants"].append(source["raw_mention"])

    # Date/time mentions are not ordinary sidebar entities. Keep them as
    # grounded hints for the later timeline LLM stage.
    session.execute(delete(NerTemporalCandidate).where(
        NerTemporalCandidate.document_id == document_id,
    ))
    temporal_rows = _temporal_candidate_rows(document_id, text, raw)
    if temporal_rows:
        session.add_all(temporal_rows)

    exclusions = list(session.execute(select(NerExclusion)).scalars().all())
    if exclusions:
        author = getattr(doc, "byline", None)
        excluded = [
            key
            for key, group in groups.items()
            if is_excluded(
                exclusions,
                key[0],
                key[1],
                author,
                raw_terms=[*group.get("raw_lemmas", []), *group.get("variants", [])],
            )
        ]
        for key in excluded:
            del groups[key]
        if excluded:
            logger.info("NER exclusions dropped %d entities for doc %s: %s",
                        len(excluded), document_id, [k[1] for k in excluded])

    # Faza 6: human-approved lemma-keyed corrections (ner_corrections table) —
    # runs after exclusions (junk is gone first) and before org-registry
    # resolution below (a correction can retype orgName -> geogName/placeName,
    # which must not have already created a bogus Organization row).
    from library.ner_corrections import apply_ner_corrections

    apply_ner_corrections(session, document_id, groups, getattr(doc, "byline", None))

    # spaCy occasionally labels a capitalized common noun as persName. Verify
    # only ambiguous one-word candidates with cheap, batched Bielik calls.
    # Fail open: malformed/unavailable LLM results leave entities untouched.
    from library.person_context_classifier import classify_single_word_person_candidates

    classifications = classify_single_word_person_candidates(
        text,
        getattr(doc, "title", None) or "",
        groups,
        document_id,
    )
    if classifications:
        session.add_all([
            NerContextClassification(
                document_id=document_id,
                entity_type="persName",
                entity_text=result["entity_text"],
                predicted_class=result["predicted_class"],
                confidence=result["confidence"],
                rationale=result["rationale"],
                context_excerpt=result["context"][:2000],
                model=result["model"],
                dropped=result["dropped"],
            )
            for result in classifications
        ])
        dropped_by_context = [result["key"] for result in classifications if result["dropped"]]
        for key in dropped_by_context:
            groups.pop(key, None)
        if dropped_by_context:
            logger.info(
                "Context verification dropped %d false person entities for doc %s: %s",
                len(dropped_by_context),
                document_id,
                [key[1] for key in dropped_by_context],
            )

    # orgName groups: merge same-organization spelling splits within this one
    # NER result (e.g. "Interia"/"Interii" both present as separate lemma
    # groups), then resolve each merged group against the global organizations
    # registry (docs/organization-ner-alias-plan.md). entity_text for orgName
    # becomes the registry's canonical_name so /webpage, /read and chapter
    # filtering never show the same organization twice.
    org_keys = [key for key in groups if key[0] == "orgName"]
    organization_confidence: dict[str, tuple[int, str]] = {}
    if org_keys:
        org_groups_by_name = {key[1]: groups[key] for key in org_keys}
        merged_org_groups = merge_ner_groups(org_groups_by_name)
        for key in org_keys:
            del groups[key]
        for name, group in merged_org_groups.items():
            # A short all-caps orgName can have multiple known meanings.  It
            # is never a global alias: the LLM gets only the approved local
            # candidates and may decline to choose.  Full names and ordinary
            # spelling variants retain the deterministic registry path.
            candidates = (
                ambiguous_alias_candidates(session, name)
                if " " not in name and 2 <= len(name) <= 10 and name.isupper()
                else []
            )
            organization = select_ambiguous_alias_candidate_with_llm(
                text, getattr(doc, "title", "") or "", name, candidates,
            )
            if organization is not None:
                confidence = CONFIDENCE_CONTEXT_LLM_MATCHED
            else:
                organization, confidence = resolve_or_create(session, name, group["variants"])
            canonical_name = organization.canonical_name
            merged_key = ("orgName", canonical_name)
            existing = groups.get(merged_key)
            surface_forms = [name, *group["variants"]]
            if existing is not None:
                existing["count"] += group["count"]
                combined = dict.fromkeys(existing["variants"])
                for value in surface_forms:
                    if value.casefold() != canonical_name.casefold():
                        combined.setdefault(value, None)
                existing["variants"] = list(combined)
            else:
                distinct_variants = dict.fromkeys(
                    value for value in surface_forms if value.casefold() != canonical_name.casefold()
                )
                groups[merged_key] = {"count": group["count"], "variants": list(distinct_variants)}
            organization_confidence.setdefault(canonical_name, (organization.id, confidence))

    # Manually merged rows (source='manual', set by merge_document_entities())
    # survive the refresh. A fresh NER group colliding with one on
    # (entity_type, casefold(entity_text)/variants) is dropped instead of
    # inserted — otherwise it would either duplicate the merged name or
    # violate the (document_id, entity_type, entity_text) unique constraint.
    # The manual row itself is left completely untouched (no mention_count
    # update) — the user already merged it and knows what they did.
    manual_rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id, DocumentEntity.source == "manual")
        .all()
    )
    manual_keys_by_type: dict[str, set[str]] = {}
    for manual_row in manual_rows:
        names = {manual_row.entity_text.casefold(), *(v.casefold() for v in (manual_row.variants or []))}
        manual_keys_by_type.setdefault(manual_row.entity_type, set()).update(names)

    colliding_keys = [
        key for key in groups
        if key[1].casefold() in manual_keys_by_type.get(key[0], set())
        or any(v.casefold() in manual_keys_by_type.get(key[0], set()) for v in groups[key]["variants"])
    ]
    for key in colliding_keys:
        del groups[key]
    if colliding_keys:
        logger.info(
            "Skipped %d NER groups colliding with manually merged entities for doc %s: %s",
            len(colliding_keys), document_id, [key[1] for key in colliding_keys],
        )

    # Refreshes must not silently erase human decisions.  Explicitly approved
    # organization links (and links backed by a manual entity merge) survive;
    # every automatic row removed below gets an immutable audit record.
    from library.relationship_audit import audit_removals

    removable_entities = session.execute(select(DocumentEntity).where(
        DocumentEntity.document_id == document_id,
        DocumentEntity.source != "manual",
    )).scalars().all()
    audit_removals(session, document_id, "entity", "ner_refresh", removable_entities, lambda row: {
        "entity_type": row.entity_type, "entity_text": row.entity_text,
        "variants": row.variants or [], "source": row.source,
    })
    removable_org_links = []
    manual_entity_ids = {row.id for row in manual_rows}
    for link in session.execute(select(DocumentOrganization).where(
        DocumentOrganization.document_id == document_id,
    )).scalars().all():
        if link.review_status == "approved" or link.document_entity_id in manual_entity_ids:
            continue
        removable_org_links.append(link)
    audit_removals(session, document_id, "organization", "ner_refresh", removable_org_links, lambda row: {
        "organization_id": row.organization_id, "document_entity_id": row.document_entity_id,
        "confidence": row.confidence, "review_status": row.review_status,
    })
    for link in removable_org_links:
        session.delete(link)
    for row in removable_entities:
        session.delete(row)
    # Flush deletes before adding the replacement rows.  Without this explicit
    # boundary SQLAlchemy may INSERT an unchanged key (for example EDF) before
    # its old derived row is deleted, violating the per-document unique key.
    session.flush()
    rows = [
        DocumentEntity(
            document_id=document_id,
            entity_type=entity_type,
            entity_text=entity_text,
            mention_count=group["count"],
            variants=group["variants"],
        )
        for (entity_type, entity_text), group in sorted(
            groups.items(), key=lambda kv: (-kv[1]["count"], kv[0]),
        )
    ]
    session.add_all(rows)
    if organization_confidence:
        session.flush()
        rows_by_key = {(row.entity_type, row.entity_text): row for row in rows}
        preserved_organization_ids = set(session.scalars(select(DocumentOrganization.organization_id).where(
            DocumentOrganization.document_id == document_id,
        )).all())
        for entity_text, (organization_id, confidence) in organization_confidence.items():
            if organization_id in preserved_organization_ids:
                continue
            row = rows_by_key.get(("orgName", entity_text))
            # A candidate may be removed later in the NER pipeline (for
            # example by an exclusion rule).  Do not recreate an orphaned
            # DocumentOrganization link for an entity that is no longer in
            # the final result set.
            if row is None:
                continue
            session.add(DocumentOrganization(
                document_id=document_id,
                organization_id=organization_id,
                document_entity_id=row.id,
                confidence=confidence,
            ))

    organization_groups = [
        {
            "text": entity_text,
            "variants": group["variants"],
            "organization_id": organization_confidence.get(entity_text, (None, None))[0],
        }
        for (entity_type, entity_text), group in groups.items()
        if entity_type == "orgName"
    ]
    if doc is not None and organization_groups:
        from library.information_provenance import refresh_ner_cited_sources

        refresh_ner_cited_sources(session, doc, text, organization_groups)
    # Named facilities are semantic entities assembled from a recognised object
    # type and a NER place ("elektrownia jądrowa Gravelines"), not an extra
    # spaCy label.  Flush first so their links can safely refer to new place rows.
    session.flush()
    from library.facility_service import refresh_document_facilities

    refresh_document_facilities(session, document_id, text)
    return rows


def get_document_entities(session, document_id: int) -> dict[str, list[dict]]:
    """Return the document's stored entities grouped by type, alphabetically.

    Shape: {"persName": [{"text", "count"}, ...], "geogName": [...], "placeName": [...]}.
    Place entities checked by stage-3 verification additionally carry
    "verified" (bool) and — when the geocoder resolved them — "lat"/"lon"/
    "display_name"; entities never checked have no "verified" key. Place
    entities matched to linear infrastructure (infra_geometries, Overpass)
    carry "pipeline": {"kind", "substance", "name", "geojson"}.
    Person entities resolved by stage-4 (document_persons link with
    raw_mention == entity_text) carry "person_id"/"canonical_name"/
    "person_description"/"wikidata_qid"/"confidence".
    Organization entities resolved to the global registry additionally carry
    "organization_description" (Organization.description, e.g. "EDF — francuski
    operator energetyczny"; None until someone fills it in via PATCH
    /organizations/<id> or the backfill script).
    geogName/placeName/orgName entities additionally carry "is_country" (bool)
    — country_gazetteer.canonical_country_name() on entity_text (the whole
    entity_text must BE a country, not merely contain one as a substring —
    detect_countries() was tried here first and wrongly flagged "Port Sudan"/
    "Al-Faszirze Emiraty" as countries because they contain "Sudan"/"Emiraty";
    it's deliberately a candidate generator elsewhere, e.g.
    article_tagging.extract_countries_hybrid()'s LLM-filtered prescreen, but
    that over-matching is wrong for an exact-identity check), the same check
    place_verification.py uses to skip geocoding a country. Callers use it to
    keep country mentions out of "Miejsca"/"Organizacje": they belong to the
    separate, LLM-vetted kraj-* tag pipeline (article_tagging.extract_countries_hybrid),
    not this NER-derived list.
    """
    from library.country_gazetteer import canonical_country_name
    from library.db.models import DocumentFacility, DocumentInformationSource, DocumentOrganization, InfraGeometry
    from library.person_registry import get_document_persons

    rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.entity_text)
        .all()
    )
    persons_by_mention = {p["raw_mention"]: p for p in get_document_persons(session, document_id)}
    source_links = session.scalars(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == document_id,
        DocumentInformationSource.role == "cited",
    )).all()
    sources_by_name = {}
    for link in source_links:
        for name in [link.source.canonical_name, link.raw_mention]:
            sources_by_name[normalize_ner_text(name).casefold()] = link
    organization_links_by_entity = {
        link.document_entity_id: link
        for link in session.scalars(select(DocumentOrganization).where(
            DocumentOrganization.document_id == document_id,
        )).all()
    }
    facilities = session.scalars(select(DocumentFacility).where(
        DocumentFacility.document_id == document_id,
    )).all()

    place_types = {"geogName", "placeName"}
    place_names = [r.entity_text for r in rows if r.entity_type in place_types]
    pipelines_by_query: dict[str, InfraGeometry] = {}
    if place_names:
        infra_rows = (
            session.query(InfraGeometry)
            .filter(InfraGeometry.query.in_(place_names), InfraGeometry.resolved.is_(True))
            .all()
        )
        pipelines_by_query = {r.query: r for r in infra_rows}

    grouped: dict[str, list[dict]] = {
        "persName": [], "orgName": [], "geogName": [], "placeName": [], "facility": [],
    }
    for row in rows:
        item: dict = {"id": row.id, "text": row.entity_text, "count": row.mention_count,
                      "variants": row.variants or []}
        if row.entity_type in {*place_types, "orgName"}:
            item["is_country"] = canonical_country_name(row.entity_text) is not None
        if row.geocode is not None:
            item["verified"] = row.geocode.resolved
            if row.geocode.resolved:
                item["lat"] = float(row.geocode.lat) if row.geocode.lat is not None else None
                item["lon"] = float(row.geocode.lon) if row.geocode.lon is not None else None
                item["display_name"] = row.geocode.display_name
        if row.entity_type in place_types and row.entity_text in pipelines_by_query:
            infra = pipelines_by_query[row.entity_text]
            item["pipeline"] = {
                "kind": infra.kind,
                "substance": infra.substance,
                "name": infra.name,
                "geojson": infra.geojson,
            }
        if row.entity_type == "persName" and row.entity_text in persons_by_mention:
            link = persons_by_mention[row.entity_text]
            item["link_id"] = link["link_id"]
            item["person_id"] = link["person_id"]
            item["canonical_name"] = link["canonical_name"]
            item["person_description"] = link["description"]
            item["wikidata_qid"] = link["wikidata_qid"]
            item["confidence"] = link["confidence"]
        if row.entity_type == "orgName":
            source_link = next((
                sources_by_name.get(normalize_ner_text(name).casefold())
                for name in [row.entity_text, *(row.variants or [])]
                if sources_by_name.get(normalize_ner_text(name).casefold()) is not None
            ), None)
            if source_link is not None:
                item["information_source_id"] = source_link.source_id
                item["source_evidence"] = source_link.evidence_excerpt
            organization_link = organization_links_by_entity.get(row.id)
            if organization_link is not None:
                item["organization_id"] = organization_link.organization_id
                item["organization_link_id"] = organization_link.id
                item["organization_review_status"] = organization_link.review_status
                item["organization_description"] = organization_link.organization.description
        grouped.setdefault(row.entity_type, []).append(item)
    for link in facilities:
        facility = link.facility
        grouped["facility"].append({
            "id": link.id,
            "text": facility.canonical_name,
            "count": link.mention_count,
            # Preserve the surface form from this document.  It lets chapter
            # filtering and the reader tooltip match inflected mentions such
            # as "elektrowni jądrowej Gravelines".
            "variants": list(dict.fromkeys([
                link.raw_mention, *(facility.aliases or []), facility.canonical_name,
            ])),
            "facility_type": facility.facility_type,
            "place_name": facility.place_name,
            "lat": float(facility.latitude) if facility.latitude is not None else None,
            "lon": float(facility.longitude) if facility.longitude is not None else None,
            "facility_description": facility.description,
            "operator_name": facility.operator_name,
            "source_url": facility.source_url,
            "wikidata_qid": facility.wikidata_qid,
            "confidence": link.confidence,
        })
    return grouped


def filter_entities_to_text(grouped: dict[str, list[dict]], text: str) -> dict[str, list[dict]]:
    """Subset of get_document_entities() output actually mentioned in text.

    Chapter-scoped attribution: the expensive verification (geocoder, Wikidata,
    LLM) stays document-level; this only checks which of the already-verified
    entities appear in the given fragment. Stored surface variants match as
    complete tokens (Unicode-aware boundaries on both sides). Rows without
    stored variants (predating the variants column) retain the legacy
    word-start prefix fallback against entity_text until the next refresh.
    Matching is case-insensitive, except that a capitalized needle only matches
    a surface form that is also capitalized.

    Kept items get their "count" REPLACED with the local mention count — the
    reader chip "Putin ×50" in chapter scope used to show the whole-book count,
    misleading for a chapter with a single mention. They remain alphabetically
    sorted so the reader sidebar is easy to verify against an expected list.
    Original dicts are not mutated (document-level callers keep global counts).
    """
    filtered: dict[str, list[dict]] = {}
    for entity_type, items in grouped.items():
        kept = []
        for item in items:
            variants = item.get("variants") or []
            raw_needles = variants or [item["text"]]
            needles_by_key: dict[str, str] = {}
            for raw_needle in raw_needles:
                needle = raw_needle.strip()
                if needle:
                    needles_by_key.setdefault(needle.casefold(), needle)
            needles = sorted(needles_by_key.values(), key=len, reverse=True)
            if not needles:
                continue

            alternatives = "|".join(f"(?P<v{i}>{re.escape(needle)})" for i, needle in enumerate(needles))
            right_boundary = r"(?!\w)" if variants else ""
            pattern = re.compile(rf"(?<!\w)(?:{alternatives}){right_boundary}", re.IGNORECASE)

            matched_variant_indexes: set[int] = set()
            local_count = 0
            for match in pattern.finditer(text):
                variant_index = int(match.lastgroup[1:])
                needle = needles[variant_index]
                matched_text = match.group(0)
                if needle[0].isupper() and not matched_text[0].isupper():
                    continue
                matched_variant_indexes.add(variant_index)
                local_count += 1

            if local_count:
                chapter_variants = [
                    needle for i, needle in enumerate(needles) if i in matched_variant_indexes
                ]
                kept.append({**item, "count": local_count, "chapter_variants": chapter_variants})
        kept.sort(key=lambda i: i["text"])
        filtered[entity_type] = kept
    return filtered


PLACE_TYPES = ("geogName", "placeName")
# orgName is accepted as a merge *source* (not target) to cover NER
# misclassifications where the same real-world place was tagged orgName in
# one mention and geogName/placeName in another within the same document
# (e.g. "Kijów" — see docs discussion, no dedicated doc file yet).
MERGEABLE_PLACE_SOURCE_TYPES = (*PLACE_TYPES, "orgName")


def merge_document_entities(source: DocumentEntity, target: DocumentEntity, *, target_source: str = "manual") -> None:
    """Fold source into target: sum mention_count, union variants, adopt a
    missing geocode_id from source. Caller deletes source from the session and
    owns the transaction/validation (document/type checks) — see
    POST /document/<id>/places/merge in server.py. Unlike orgName merges,
    places have no cross-document registry, so this is per-document only.
    Marks target as source=target_source (default 'manual') so
    refresh_document_entities() never overwrites this merge on the next NER
    run for a human-made merge. Automatic callers (place_verification.py's
    geocoder-driven canonicalization, Faza 3) pass target_source='geocoded'
    instead — that merge is cheap to redo on every place-verification pass,
    so it deliberately does NOT get the same refresh-survival protection as
    a human decision.
    """
    combined_variants = dict.fromkeys(target.variants or [])
    for value in [source.entity_text, *(source.variants or [])]:
        if value.casefold() != target.entity_text.casefold():
            combined_variants.setdefault(value)
    target.variants = list(combined_variants)
    target.mention_count += source.mention_count
    if target.geocode_id is None and source.geocode_id is not None:
        target.geocode_id = source.geocode_id
    target.source = target_source
