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
from collections import Counter

from sqlalchemy import delete, func, select, update
from unidecode import unidecode

from library.db.models import (
    Document,
    DocumentEntity,
    DocumentOrganization,
    NerChannelGlossaryEntry,
    NerContextClassification,
    NerExclusion,
    NerGlossaryApplication,
    NerTemporalCandidate,
)
from library.ner_channel_glossary import GlossaryEntry, apply_glossary, restore_original_variants
from library.ner_client import NERServiceUnavailable, aggregate_entities_detailed, extract_entities, is_available
from library.ner_normalization import normalize_ner_text, strip_content_markers, strip_markdown_emphasis
from library.org_compound_names import merge_compound_org_names
from library.organization_registry import (
    CONFIDENCE_CONTEXT_LLM_MATCHED,
    ambiguous_alias_candidates_for_forms,
    merge_ner_groups,
    resolve_or_create,
    select_ambiguous_alias_candidate_with_llm,
)

logger = logging.getLogger(__name__)


def _organization_document_context(doc) -> str:
    """Short cues about the document (channel, publication date, country tags) for resolving
    an ambiguous organization name. Country tags are only a hint: they are missing on many
    documents (doc #11237 is entirely about the USA and has none), so an empty result is normal."""
    if doc is None:
        return ""
    parts = []
    byline = getattr(doc, "byline", None)
    if isinstance(byline, str) and byline:
        parts.append(f"autor/kanał: {byline}")
    published = getattr(doc, "published_on", None)
    if isinstance(published, datetime.date):
        parts.append(f"data publikacji: {published:%Y-%m-%d}")
    tags = getattr(doc, "tags", None)
    if isinstance(tags, str):
        countries = [tag.strip() for tag in tags.split(",") if tag.strip().startswith("kraj-")]
        if countries:
            parts.append("tagi krajów: " + ", ".join(countries[:8]))
    return "; ".join(parts)


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
                author: str | None, raw_terms: list[str] | None = None,
                document_id: int | None = None) -> bool:
    """True when an exclusion rule suppresses this entity.

    Matching is case-insensitive on the normalized base form and, when
    provided, its raw lemmas/surface variants. entity_type='*' matches all
    types; geogName/placeName rules remain interchangeable after place-label
    merging; scope='author' only applies when the document's author matches and
    scope='document' only for the rule's own document_id.
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
        if exc.scope == "document" and document_id is not None and exc.document_id == document_id:
            return True
        if (
            exc.scope == "author"
            and author_lower
            and normalize_ner_text(exc.author or "").casefold() == author_lower
        ):
            return True
    return False


def _apply_channel_glossary(session, document_id: int, text: str) -> tuple[str, Counter | None]:
    """The text with the document channel's glossary applied, plus the replacements made.

    The replacements are None when the document has no channel (byline), i.e. no glossary applies."""
    doc = session.get(Document, document_id)
    author = getattr(doc, "byline", None)
    if not isinstance(author, str) or not author.strip():
        return text, None
    rows = session.execute(
        select(NerChannelGlossaryEntry).where(func.lower(NerChannelGlossaryEntry.author) == author.strip().lower())
    ).scalars().all()
    entries = [
        GlossaryEntry(row.id, row.canonical_name, tuple(row.aliases or ()), bool(row.fuzzy))
        for row in rows if isinstance(row, NerChannelGlossaryEntry)
    ]
    if not entries:
        return text, Counter()
    result = apply_glossary(text, entries)
    if result.replacements:
        logger.info("NER channel glossary: %d replacements for doc %s (%s)", sum(result.replacements.values()),
                    document_id, ", ".join(f"{o}->{r}" for (_i, o, r) in list(result.replacements)[:10]))
    return result.text, result.replacements


def apply_channel_glossary_text(session, document_id: int, text: str) -> str:
    """The text with the document channel's glossary applied, for non-NER consumers (country detection).

    Same copy-only semantics as the NER refresh: the stored transcript never changes. Never raises —
    a glossary problem must not break tagging, the unmodified text is returned instead."""
    try:
        return _apply_channel_glossary(session, document_id, text)[0]
    except Exception:
        logger.warning("Channel glossary could not be applied for doc %s", document_id, exc_info=True)
        return text


def _record_glossary_replacements(session, document_id: int, groups: dict, replacements: Counter) -> None:
    """Audit the glossary replacements (replace semantics per document) and restore original variants."""
    if replacements is None:  # the document has no channel, so no glossary was ever consulted
        return
    session.execute(delete(NerGlossaryApplication).where(NerGlossaryApplication.document_id == document_id))
    if not replacements:
        return
    restore_original_variants(groups, replacements)
    session.add_all([
        NerGlossaryApplication(document_id=document_id, glossary_id=entry_id, original_text=original,
                               replacement_text=replacement, occurrences=count)
        for (entry_id, original, replacement), count in replacements.items()
    ])


def _add_place_mentions(groups: dict[tuple[str, str], dict], text: str, raw: list[dict]) -> None:
    """Fold gazetteer-detected place mentions (place_mention_gazetteer) into `groups` in place."""
    from library.place_mention_gazetteer import detect_place_mentions

    for name, surfaces in detect_place_mentions(text, raw).items():
        count = sum(surfaces.values())
        existing_key = next(
            (key for key in groups if key[0] in {"placeName", "geogName"} and key[1].casefold() == name.casefold()),
            None,
        )
        if existing_key is None:
            groups[("placeName", name)] = {"count": count, "variants": list(surfaces), "raw_lemmas": [name]}
            continue
        group = groups[existing_key]
        group["count"] += count
        for surface in surfaces:
            if surface not in group["variants"] and surface.casefold() != existing_key[1].casefold():
                group["variants"].append(surface)


def _extend_places_to_registry_names(session, groups, text, raw):
    """Promote place fragments to registry organization names, atomically."""
    from copy import deepcopy

    from library.named_event_detector import capitalized_word_ends
    from library.organization_registry import find_organization_by_phrase

    try:
        updated = deepcopy(groups)
        seen = set()
        for mention in raw:
            if mention.get("label") not in {"geogName", "placeName"}:
                continue
            start, end = mention.get("start"), mention.get("end")
            if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text):
                continue
            if (start, end) in seen:
                continue
            seen.add((start, end))
            forms = {str(mention.get(field) or "").casefold() for field in ("text", "lemma")}
            key = next((key for key, group in updated.items()
                        if key[0] in {"placeName", "geogName"} and forms.intersection(
                            value.casefold() for value in
                            [key[1], *group.get("variants", []), *group.get("raw_lemmas", [])])), None)
            if key is None:
                continue
            for phrase_end in reversed(capitalized_word_ends(text, end, 2)):
                phrase = text[start:phrase_end]
                organization = find_organization_by_phrase(session, phrase)
                if organization is None:
                    continue
                updated[key]["count"] -= 1
                if updated[key]["count"] <= 0:
                    del updated[key]
                name = organization.canonical_name
                group = updated.setdefault(("orgName", name), {"count": 0, "variants": [], "raw_lemmas": []})
                group["count"] += 1
                if phrase.casefold() != name.casefold() and phrase not in group["variants"]:
                    group["variants"].append(phrase)
                if name not in group["raw_lemmas"]:
                    group["raw_lemmas"].append(name)
                break
        groups.clear()
        groups.update(updated)
    except Exception:
        logger.exception("Failed to extend place mentions to organization names; retaining groups")


def _add_named_events(session, groups, text):
    """Fold detected event mentions into groups without partial updates on failure."""
    from copy import deepcopy

    from library.named_event_detector import detect_named_events
    from library.organization_registry import find_organization_by_phrase

    try:
        def lookup(phrase):
            organization = find_organization_by_phrase(session, phrase)
            return (organization.canonical_name, organization.id) if organization is not None else None

        events = detect_named_events(text, lookup)
        updated = deepcopy(groups)
        for name, event in events.items():
            group = updated.setdefault(("eventName", name), {"count": 0, "variants": [], "raw_lemmas": []})
            group["count"] += event["count"]
            group["variants"] = list(dict.fromkeys([*group["variants"], *event["variants"]]))
            group["raw_lemmas"] = list(dict.fromkeys([*group["raw_lemmas"], name]))
        groups.clear()
        groups.update(updated)
    except Exception:
        logger.exception("Failed to detect named events; retaining groups")


def _merge_lemma_split_places(groups: dict[tuple[str, str], dict]) -> list[tuple[str, str]]:
    """Fold a place group into another one that already lists its name as a surface variant.

    spaCy sometimes leaves one inflected mention unlemmatized ("Adenu", "Teksasu", "Mekki"),
    so it becomes a group of its own next to the properly lemmatized "Aden"/"Teksas"/"Mekka"
    whose `variants` already contain exactly that spelling. Left alone the split group is
    geocoded separately and can land on an unrelated village. Only same-type groups are merged;
    the group with more mentions survives. Returns the keys that were folded away.
    """
    removed: list[tuple[str, str]] = []
    keys = sorted(
        (key for key in groups if key[0] in {"placeName", "geogName"}),
        key=lambda key: (groups[key]["count"], key[1]),
    )
    for source_key in keys:
        if source_key in removed:
            continue
        name = source_key[1].casefold()
        target_key = next(
            (
                key for key in reversed(keys)
                if key != source_key and key[0] == source_key[0] and key not in removed
                and name in {value.casefold() for value in groups[key].get("variants", [])}
            ),
            None,
        )
        if target_key is None:
            continue
        source, target = groups[source_key], groups[target_key]
        target["count"] += source["count"]
        known = {value.casefold() for value in target.get("variants", [])}
        for value in [source_key[1], *source.get("variants", [])]:
            if value.casefold() not in known and value.casefold() != target_key[1].casefold():
                target.setdefault("variants", []).append(value)
                known.add(value.casefold())
        if source.get("raw_lemmas"):
            lemmas = target.setdefault("raw_lemmas", [])
            lemmas.extend(value for value in source["raw_lemmas"] if value not in lemmas)
        if source.get("country_mentions"):
            mentions = target.setdefault("country_mentions", Counter())
            mentions.update(source["country_mentions"])
        del groups[source_key]
        removed.append(source_key)
    return removed


def _add_pseudonyms(groups, text):
    """Add explicit pseudonyms as persons, atomically and without external lookups."""
    from copy import deepcopy

    try:
        from library.pseudonym_detector import detect_pseudonyms

        updated = deepcopy(groups)
        for pair in detect_pseudonyms(text):
            name = pair["pseudonym"]
            occurrences = []
            for match in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.IGNORECASE):
                surface = match.group()
                quoted = (text[max(0, match.start() - 1):match.start()] in {'"', "„", "“", "«", "'"}
                          and text[match.end():match.end() + 1] in {'"', "”", "»", "'"})
                if surface[0].isupper() or quoted:
                    occurrences.append(surface)
            variants = list(dict.fromkeys(occurrences))
            existing = next((key for key in updated if key[0] == "persName"
                             and key[1].casefold() == name.casefold()), None)
            if existing is not None:
                group = updated[existing]
                group["variants"] = list(dict.fromkeys([*group["variants"], *variants]))
                group["pseudonym"] = True
                continue
            wrong = [key for key in updated if key[0] in {"orgName", "placeName", "geogName"}
                     and key[1].casefold() == name.casefold()]
            count = max([1, len(occurrences), *(updated[key]["count"] for key in wrong)])
            for key in wrong:
                del updated[key]
            updated[("persName", name)] = {
                "count": count, "variants": variants, "raw_lemmas": [name], "pseudonym": True,
            }
        groups.clear()
        groups.update(updated)
    except Exception:
        logger.exception("Failed to detect pseudonyms; retaining groups")


def _apply_country_abbreviations(
    groups: dict[tuple[str, str], dict], text: str, title: str, document_id: int,
) -> None:
    """Turn abbreviations the LLM confirmed as a country ("DRK" = Kongo) into that country's place group.

    spaCy types such an abbreviation as an organization or person (or misses it); here the group
    of that spelling is dropped and its mentions counted from the text go to a `placeName` group
    named after the country, the abbreviation staying as a surface form. Fails open.
    """
    from library.country_abbreviations import confirmed_country_abbreviations

    for abbreviation, info in confirmed_country_abbreviations(text, title, document_id).items():
        for key in [key for key in groups if key[1].casefold() == abbreviation.casefold()]:
            del groups[key]
        country = info["country"]
        existing_key = next(
            (key for key in groups if key[0] in {"placeName", "geogName"} and key[1].casefold() == country.casefold()),
            None,
        )
        if existing_key is None:
            groups[("placeName", country)] = {"count": info["count"], "variants": [abbreviation], "raw_lemmas": [country]}
            continue
        group = groups[existing_key]
        group["count"] += info["count"]
        if abbreviation not in group["variants"]:
            group["variants"].append(abbreviation)


def _apply_state_descriptors(
    groups: dict[tuple[str, str], dict], text: str, title: str, document_id: int,
) -> None:
    """Count "królestwo"/"sułtanat"/"księstwo" as a mention of the fitting country named in the same chapter.

    The model must confirm the pair (see library/state_descriptor_countries.py); the descriptor
    stays a surface form of the country's `placeName` group, and the mentions are taken away from a
    NER group of the same spelling ("Królestwo" typed as organization or place). Fails open.
    """
    from library.state_descriptor_countries import confirmed_state_descriptors

    try:
        confirmed = confirmed_state_descriptors(text, title, document_id)
    except Exception:  # noqa: BLE001 — a classifier failure must never fail the entity refresh
        logger.warning("State descriptor step failed for document %s", document_id, exc_info=True)
        return
    for country, info in confirmed.items():
        remaining = info["count"]
        for key in [key for key in groups if key[0] in {"orgName", "placeName", "geogName"}
                    and key[1].casefold() in {variant.casefold() for variant in info["variants"]}]:
            taken = min(remaining, groups[key]["count"])
            groups[key]["count"] -= taken
            if groups[key]["count"] <= 0:
                del groups[key]
        existing_key = next(
            (key for key in groups if key[0] in {"placeName", "geogName"} and key[1].casefold() == country.casefold()),
            None,
        )
        if existing_key is None:
            groups[("placeName", country)] = {
                "count": info["count"], "variants": list(info["variants"]), "raw_lemmas": [country],
            }
            continue
        group = groups[existing_key]
        group["count"] += info["count"]
        for variant in info["variants"]:
            if variant not in group["variants"]:
                group["variants"].append(variant)


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
    from library.llm_usage.context import document_usage_context

    with document_usage_context(document_id):
        session.execute(select(func.pg_advisory_xact_lock(22_004, document_id)))

        # Channel glossary: repair known speech-to-text slips in a COPY of the text (the stored
        # transcript is untouched); every later step works on the repaired copy so offsets agree.
        text, glossary_replacements = _apply_channel_glossary(session, document_id, text)

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
        _record_glossary_replacements(session, document_id, groups, glossary_replacements)

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

        # Places spaCy never reports (lowercase "królewca", the adjective-only
        # "obwód kaliningradzki", "przesmyk suwalski"): a closed, text-grounded list.
        _add_place_mentions(groups, text, raw)
        _extend_places_to_registry_names(session, groups, text, raw)
        _add_named_events(session, groups, text)
        _add_pseudonyms(groups, text)

        # Abbreviations shared with something else ("DRK": Kongo vs the German Red Cross) become the
        # country only when a contextual LLM check confirms it.
        _apply_country_abbreviations(groups, text, getattr(doc, "title", None) or "", document_id)
        # "Królestwo" after "Arabia Saudyjska" in the same chapter is that country (model-confirmed).
        _apply_state_descriptors(groups, text, getattr(doc, "title", None) or "", document_id)

        merged_orgs = merge_compound_org_names(
            strip_content_markers(strip_markdown_emphasis(text)), groups,
        )
        if merged_orgs:
            logger.info("NER compound organization names merged %d groups for doc %s", len(merged_orgs), document_id)

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
            for key, group in groups.items():
                mentions = group.get("country_mentions", {})
                removed = {
                    mention for mention in mentions
                    if mention[2] and is_excluded(
                        exclusions, key[0], mention[0], author,
                        raw_terms=[mention[1]], document_id=document_id,
                    )
                }
                if not removed:
                    continue
                # A term shared with a retained mention must keep its original
                # whole-group exclusion semantics (even if its spelling differs).
                retained_terms = {
                    value.casefold() for mention in mentions if mention not in removed
                    for value in mention[:2]
                }
                removed_terms = {
                    value.casefold() for mention in removed for value in mention[:2]
                } - retained_terms
                other_terms = [
                    value for value in [*group.get("raw_lemmas", []), *group.get("variants", [])]
                    if value.casefold() not in removed_terms
                ]
                if is_excluded(exclusions, key[0], key[1], author,
                               raw_terms=other_terms, document_id=document_id):
                    continue  # The ordinary check below still drops the whole group.
                group["count"] -= sum(mentions[mention] for mention in removed)
                for field in ("raw_lemmas", "variants"):
                    group[field] = [value for value in group.get(field, []) if value.casefold() not in removed_terms]
                for mention in removed:
                    del mentions[mention]
            excluded = [
                key
                for key, group in groups.items()
                if group["count"] == 0 or is_excluded(
                    exclusions,
                    key[0],
                    key[1],
                    author,
                    raw_terms=[*group.get("raw_lemmas", []), *group.get("variants", [])],
                    document_id=document_id,
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

        folded_places = _merge_lemma_split_places(groups)
        if folded_places:
            logger.info("NER place lemma splits folded for doc %s: %s", document_id, [k[1] for k in folded_places])

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
        # Resolve country senses before the person verdicts remove their groups.
        from library.entity_sense_classifier import apply_country_sense

        sense_results = apply_country_sense(groups, text, getattr(doc, "title", None) or "", document_id)
        if sense_results:
            session.add_all([
                NerContextClassification(
                    document_id=document_id, entity_type="persName", entity_text=result["entity_text"],
                    predicted_class="country" if result["sense"] == "kraj" else result["sense"],
                    confidence=result["confidence"], rationale=result["rationale"],
                    context_excerpt=result["context"][:2000], model=result["provider"][:100],
                    dropped=result["dropped"],
                )
                for result in sense_results
            ])
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
                # Any orgName text (a short all-caps abbreviation like "RSF", or a
                # full multi-word name that happens to collide with an unrelated
                # organization's name — e.g. "Africa Corps" meaning either the
                # Russian 2023+ formation or a rendering of WWII's "Afrika
                # Korps") can have more than one known meaning. This lookup is
                # cheap (organization_ambiguous_aliases is small and indexed) and
                # returns nothing for the vast majority of names, which never had
                # a collision curated for them — it is never a global alias, so
                # the LLM only sees the approved local candidates and may decline
                # to choose. Ordinary, uncontested names fall straight through to
                # the deterministic registry path below.
                #
                # The group is named after spaCy's lemma, which for proper names is
                # often still inflected ("Kongresie"), so the curated alias is looked
                # up under the name AND every surface variant.
                ambiguous_form, candidates = ambiguous_alias_candidates_for_forms(
                    session, [name, *group["variants"]],
                )
                organization = select_ambiguous_alias_candidate_with_llm(
                    text, getattr(doc, "title", "") or "", ambiguous_form or name, candidates,
                    extra_context=_organization_document_context(doc),
                )
                confidence = CONFIDENCE_CONTEXT_LLM_MATCHED
                if organization is None and len(candidates) >= 2:
                    # A name with several curated meanings that the context did not
                    # settle stays UNRESOLVED: no global alias, no new registry row.
                    # The entity is kept (unlinked) so a reviewer can pick the meaning.
                    logger.info("Organization %r left unresolved in doc %s: ambiguous alias %r",
                                name, document_id, ambiguous_form)
                elif organization is None:
                    organization, confidence = resolve_or_create(session, name, group["variants"])
                canonical_name = organization.canonical_name if organization is not None else name
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
                if organization is not None:
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
        # After a reopen-for-editing every place row is fresh NER output; re-apply the
        # human renames/merges/deletions recorded in entity_review_decisions so those
        # corrections of the automation are not lost with the derived data.
        session.flush()
        from library.entity_overrides import (
            replay_manual_added_entities, replay_manual_organization_decisions, replay_manual_place_decisions,
            replay_entity_relevance_decisions, replay_product_merges,
        )

        replay_manual_place_decisions(session, document_id, doc)
        replay_manual_organization_decisions(session, document_id)
        replay_manual_added_entities(session, document_id, doc)
        replay_product_merges(session, document_id)
        replay_entity_relevance_decisions(session, document_id, doc)
        # Named facilities are semantic entities assembled from a recognised object
        # type and a NER place ("elektrownia jądrowa Gravelines"), not an extra
        # spaCy label.  Flush first so their links can safely refer to new place rows.
        session.flush()
        from library.facility_service import refresh_document_facilities

        refresh_document_facilities(session, document_id, text)
        return rows


def _wikipedia_url_from_links(links) -> str | None:
    """Wikipedia article among an organization's ``links`` (imported lazily: organization_location pulls in the geocoder)."""
    from library.organization_location import wikipedia_url

    return wikipedia_url(links)


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
    from library.person_registry import get_document_persons, person_link_for_mention

    rows = (
        session.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.entity_text)
        .all()
    )
    document_person_links = get_document_persons(session, document_id)
    persons_by_mention = {p["raw_mention"]: p for p in document_person_links}
    source_links = session.scalars(select(DocumentInformationSource).where(
        DocumentInformationSource.document_id == document_id,
        DocumentInformationSource.role == "cited",
        DocumentInformationSource.review_status != "rejected",
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

    from library.place_registry import name_key, profile_index

    place_profiles = profile_index(session)
    from library.geopolitics_service import name_key as event_name_key

    registry_events_by_key: dict[str, dict] = {}
    if any(r.entity_type == "eventName" for r in rows):
        from library.db.models import GeoEvent, GeoEventMentionLink

        for link, event in session.execute(
            select(GeoEventMentionLink, GeoEvent)
            .join(GeoEvent, GeoEvent.id == GeoEventMentionLink.event_id)
            .where(GeoEventMentionLink.document_id == document_id, GeoEventMentionLink.status == "confirmed")
        ).all():
            registry_events_by_key[link.name_key] = {
                "id": event.id, "title": event.title, "status": event.status, "surface": link.surface,
            }
    registry_concepts_by_key: dict[str, dict] = {}
    if any(r.entity_type == "conceptName" for r in rows):
        from library.db.models import Concept, ConceptMentionLink

        for link, concept in session.execute(
            select(ConceptMentionLink, Concept)
            .join(Concept, Concept.id == ConceptMentionLink.concept_id)
            .where(ConceptMentionLink.document_id == document_id, ConceptMentionLink.status == "confirmed")
        ).all():
            registry_concepts_by_key[link.name_key] = {
                "id": concept.id, "name": concept.name, "surface": link.surface,
            }
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
        "persName": [], "orgName": [], "geogName": [], "placeName": [], "facility": [], "eventName": [],
        "productName": [], "conceptName": [],
    }
    for row in rows:
        item: dict = {"id": row.id, "text": row.entity_text, "count": row.mention_count,
                      "variants": row.variants or [], "relevance": row.relevance or "central"}
        if row.entity_type in {*place_types, "orgName"}:
            item["is_country"] = canonical_country_name(row.entity_text) is not None
        status = row.place_verification_status
        if row.entity_type in place_types:
            item["place_verification_status"] = status
            place_profile = next((place_profiles[k] for k in (name_key(row.entity_text),
                                                              *(name_key(v) for v in (row.variants or [])))
                                  if k in place_profiles), None)
            if place_profile is not None and place_profile.wikipedia_url:
                item["wikipedia_url"] = place_profile.wikipedia_url
            item["place_review_reason"] = row.place_review_reason
            if not item["is_country"] and (split := suggest_place_split(row.entity_text, row.variants)):
                item["split_suggestion"] = split
            if status in ("needs_review", "rejected"):
                item["verified"] = False
        if row.geocode is not None:
            item["verified"] = row.geocode.resolved and status not in ("needs_review", "rejected")
            if status == "needs_review":
                item["proposed_geocode_id"] = row.geocode.id
                item["proposed_lat"] = float(row.geocode.lat) if row.geocode.lat is not None else None
                item["proposed_lon"] = float(row.geocode.lon) if row.geocode.lon is not None else None
                item["proposed_display_name"] = row.geocode.display_name
            elif item["verified"]:
                item["lat"] = float(row.geocode.lat) if row.geocode.lat is not None else None
                item["lon"] = float(row.geocode.lon) if row.geocode.lon is not None else None
                item["display_name"] = row.geocode.display_name
                historical = (row.geocode.raw or {}).get("historical") if row.geocode.osm_type == "historical_state" else None
                if historical:
                    item["historical"] = historical
        if row.entity_type in place_types and row.entity_text in pipelines_by_query:
            infra = pipelines_by_query[row.entity_text]
            item["pipeline"] = {
                "kind": infra.kind,
                "substance": infra.substance,
                "name": infra.name,
                "geojson": infra.geojson,
            }
        if row.entity_type == "eventName":
            item["description"] = row.description
            # The registry event this name was linked to FOR THIS DOCUMENT (null = not linked yet), so the
            # chip can say so instead of looking unrelated to the registry entry.
            item["registry_event"] = next((
                registry_events_by_key[key]
                for key in (event_name_key(row.entity_text), *(event_name_key(v) for v in (row.variants or [])))
                if key in registry_events_by_key
            ), None)
        if row.entity_type == "conceptName":
            # The registry concept this name was linked to FOR THIS DOCUMENT (null = not linked yet).
            item["registry_concept"] = next((
                registry_concepts_by_key[key]
                for key in (event_name_key(row.entity_text), *(event_name_key(v) for v in (row.variants or [])))
                if key in registry_concepts_by_key
            ), None)
        link = None
        if row.entity_type == "persName":
            # Exact mention first; otherwise another form of a person already linked to this document.
            link = persons_by_mention.get(row.entity_text) or person_link_for_mention(
                row.entity_text, row.variants, document_person_links)
        if link is not None:
            item["link_id"] = link["link_id"]
            item["person_id"] = link["person_id"]
            item["canonical_name"] = link["canonical_name"]
            item["person_description"] = link["description"]
            item["wikidata_qid"] = link["wikidata_qid"]
            if link.get("wikipedia_url"):
                item["wikipedia_url"] = link["wikipedia_url"]
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
                item["information_source_name"] = source_link.source.canonical_name
                item["information_source_type"] = source_link.source.source_type
                item["information_source_domain"] = source_link.source.domain
                item["information_source_description"] = source_link.source.description
            organization_link = organization_links_by_entity.get(row.id)
            if organization_link is not None:
                item["organization_id"] = organization_link.organization_id
                item["organization_link_id"] = organization_link.id
                item["organization_review_status"] = organization_link.review_status
                item["organization_description"] = organization_link.organization.description
                links = organization_link.organization.links or []
                item["organization_links"] = links
                wikipedia = organization_link.organization.wikipedia_url or _wikipedia_url_from_links(links)
                if wikipedia:
                    item["wikipedia_url"] = wikipedia
        grouped.setdefault(row.entity_type, []).append(item)
    for event in grouped["eventName"]:
        event_name = unidecode(event["text"]).casefold()
        related = [
            {"text": org["text"], **({"organization_id": org["organization_id"]}
                                   if "organization_id" in org else {})}
            for org in grouped["orgName"]
            if org["text"] and unidecode(org["text"]).casefold() in event_name
        ]
        if related:
            event["related_organizations"] = related
    for link in facilities:
        facility = link.facility
        grouped["facility"].append({
            "id": link.id,
            "relevance": "central",
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


_INFLECTION_TYPES = ("geogName", "placeName", "orgName")


def inflected_phrases(name: str, text: str) -> list[str]:
    """Inflected forms of a multi-word name found in ``text`` ("Stanach Zjednoczonych" for "Stany Zjednoczone").

    Every word of the name is reduced to a stem (its length minus a 3-letter ending, at least 4 letters) and
    the words must follow each other in the text. A form is returned as written, capitalised like the name.
    """
    words = name.split()
    if not 2 <= len(words) <= 4 or any(len(re.sub(r"\W", "", word)) < 4 for word in words):
        return []
    stems = [re.escape(word[:max(4, len(word) - 3)]) for word in words]
    pattern = re.compile(r"(?<!\w)" + r"\s+".join(f"{stem}\\w*" for stem in stems) + r"(?!\w)", re.IGNORECASE)
    return list(dict.fromkeys(
        match.group(0) for match in pattern.finditer(text)
        if all(w[0].isupper() == m[0].isupper() for w, m in zip(words, match.group(0).split(), strict=False))
    ))


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
            # The canonical name is a needle too: a manual row can list only some forms ("Stany") and
            # would otherwise never match the full name; inflected multi-word forms are found by stem.
            raw_needles = [*variants, item["text"]]
            if entity_type in _INFLECTION_TYPES:
                raw_needles.extend(inflected_phrases(item["text"], text))
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
_SPLIT_CONJUNCTIONS = {"i", "oraz", "a", "z", "and"}
_SPLIT_TOKEN = re.compile(r"[^\s,;/]+")


def split_place_tokens(text: str) -> list[str]:
    """Words of a place mention without list separators ("Pakistanem i Afganistanem" -> 2 tokens)."""
    return [t for t in _SPLIT_TOKEN.findall(text or "") if t.casefold() not in _SPLIT_CONJUNCTIONS and t != "-"]


def suggest_place_split(text: str, variants: list[str] | None = None) -> list[str] | None:
    """Canonical country names when a place mention is only a list of countries.

    "Pakistanem Afganistanem" -> ["Pakistan", "Afganistan"]. Greedy longest match so a
    two-word country ("Korea Południowa") is never cut in half; every token must belong
    to a country and at least two distinct countries must come out, otherwise None.
    Only a suggestion: the reviewer confirms (and may edit) the parts.
    """
    from library.country_gazetteer import canonical_country_name

    for form in [text, *(variants or [])]:
        tokens = split_place_tokens(form)
        if len(tokens) < 2:
            continue
        parts: list[str] = []
        index = 0
        while index < len(tokens):
            for end in range(len(tokens), index, -1):
                name = canonical_country_name(" ".join(tokens[index:end]))
                if name is not None:
                    parts.append(name)
                    index = end
                    break
            else:
                parts = []
                break
        if len(set(parts)) >= 2:
            return list(dict.fromkeys(parts))
    return None


# orgName is accepted as a merge *source* (not target) to cover NER
# misclassifications where the same real-world place was tagged orgName in
# one mention and geogName/placeName in another within the same document
# (e.g. "Kijów" — see docs discussion, no dedicated doc file yet).
MERGEABLE_PLACE_SOURCE_TYPES = (*PLACE_TYPES, "orgName")


def merge_document_entities(
    source: DocumentEntity, target: DocumentEntity, *, target_source: str = "manual", add_count: bool = True,
) -> None:
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
    if add_count:  # False when replaying onto a manual row that already carries this count
        target.mention_count += source.mention_count
    if target.geocode_id is None and source.geocode_id is not None:
        target.geocode_id = source.geocode_id
    target.source = target_source
