"""Human-curated NER correction dictionary (Faza 6, entity-refresh time).

Complements the algorithmic fixes in ner_client.py (nominative-surface
preference, country reclassification) and place_verification.py's geocoder
canonicalization: those generalize automatically but have documented gaps
(no nominative anywhere in the text and the geocoder can't resolve it, a
single unlemmatized word, spaCy inconsistently lemmatizing the same real name
into unrelated groups). This module lets a human approve a one-off fix — once
approved it applies automatically to every future document whose NER run
produces the same (spaCy-deterministic) lemma, with a full audit trail: why
the rule was approved (NerCorrection.reason/approved_by) and every time it
actually fired (NerCorrectionApplication).
"""

import logging

from sqlalchemy import func, select

from library.db.models import NerCorrection, NerCorrectionApplication, NerExclusion
from library.ner_normalization import normalize_ner_text

logger = logging.getLogger(__name__)


def _candidate_keys(entity_text: str, group: dict) -> set[str]:
    """Every lemma this group could plausibly be matched under.

    A NerCorrection.match_lemma is checked against raw_lemmas (the actual
    spaCy lemma(s) that produced this group) first and foremost — that's the
    stable, deterministic value a human curates against. entity_text/variants
    are included too so a rule can also be written against an already
    resolved display name (e.g. to retarget a Faza-1-picked surface form).
    """
    return {
        normalize_ner_text(value).casefold()
        for value in [entity_text, *group.get("raw_lemmas", []), *group.get("variants", [])]
        if normalize_ner_text(value)
    }


def _find_matching_rule(
    rules: list[NerCorrection], entity_type: str, candidate_keys: set[str], author: str | None,
) -> NerCorrection | None:
    author_lower = normalize_ner_text(author or "").casefold()
    matching_types = {entity_type}
    if entity_type in {"geogName", "placeName"}:
        matching_types.update({"geogName", "placeName"})
    for rule in rules:
        if rule.match_entity_type != "*" and rule.match_entity_type not in matching_types:
            continue
        if normalize_ner_text(rule.match_lemma).casefold() not in candidate_keys:
            continue
        if rule.scope == "global":
            return rule
        if rule.scope == "author" and author_lower and normalize_ner_text(rule.author or "").casefold() == author_lower:
            return rule
    return None


def apply_ner_corrections(session, document_id: int, groups: dict[tuple[str, str], dict], author: str | None) -> None:
    """Apply approved corrections to `groups` in place; record one audit row per application.

    `groups` is the same {(entity_type, entity_text): {"count", "variants",
    "raw_lemmas", ...}} shape entity_service.refresh_document_entities()
    already works with — mutated the same way its own orgName-merge block
    does (delete the old key, write the corrected key, merging into an
    existing group at that key when the correction causes a collision).
    """
    rules = list(session.execute(select(NerCorrection)).scalars().all())
    if not rules:
        return

    applications: list[NerCorrectionApplication] = []
    for key in list(groups.keys()):
        entity_type, entity_text = key
        group = groups[key]
        candidate_keys = _candidate_keys(entity_text, group)
        rule = _find_matching_rule(rules, entity_type, candidate_keys, author)
        if rule is None:
            continue

        new_type = rule.corrected_entity_type or entity_type
        new_text = rule.corrected_text
        new_key = (new_type, new_text)
        if new_key == key:
            # Matched via accumulated raw_lemmas/variants after an earlier
            # merge already produced the corrected spelling — nothing left
            # to do, and logging it would just be audit-log noise.
            continue
        del groups[key]
        if new_key in groups and new_key != key:
            target = groups[new_key]
            target["count"] += group["count"]
            target["variants"] = list(dict.fromkeys([*target.get("variants", []), *group.get("variants", [])]))
            target["raw_lemmas"] = list(dict.fromkeys([*target.get("raw_lemmas", []), *group.get("raw_lemmas", [])]))
        else:
            groups[new_key] = group

        applications.append(NerCorrectionApplication(
            document_id=document_id,
            correction_id=rule.id,
            entity_type_before=entity_type,
            entity_text_before=entity_text,
            entity_type_after=new_type,
            entity_text_after=new_text,
        ))
        logger.info(
            "NER correction applied for doc %s: (%s, %r) -> (%s, %r) [rule %s]",
            document_id, entity_type, entity_text, new_type, new_text, rule.id,
        )

    if applications:
        session.add_all(applications)


def build_corrections_stats(rules, usage_by_rule: dict, pair_rows: list, exclusion_rows: list) -> dict:
    """Shape raw query results into the payload behind GET /ner_corrections/stats.

    `usage_by_rule`: {correction_id: (applications, distinct_documents, last_applied_at)};
    `pair_rows`: [(type_before, type_after, applications, distinct_documents)];
    `exclusion_rows`: [(entity_type, rules_count)]. Pure — no DB access — so it is unit-testable.
    """
    items = []
    for rule in rules:
        applications, documents, last_applied = usage_by_rule.get(rule.id, (0, 0, None))
        items.append({
            "id": rule.id, "match_lemma": rule.match_lemma, "match_entity_type": rule.match_entity_type,
            "corrected_text": rule.corrected_text, "corrected_entity_type": rule.corrected_entity_type,
            "scope": rule.scope, "reason": rule.reason, "approved_by": rule.approved_by,
            "source_document_id": rule.source_document_id,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "applications": applications, "documents": documents,
            "last_applied_at": last_applied.isoformat() if last_applied else None,
        })
    items.sort(key=lambda item: (-item["applications"], item["id"]))
    return {
        "totals": {
            "rules": len(items),
            "unused_rules": sum(1 for item in items if item["applications"] == 0),
            "applications": sum(item["applications"] for item in items),
            "exclusions": sum(count for _, count in exclusion_rows),
        },
        "rules": items,
        "by_type": [
            {"type_before": before, "type_after": after, "applications": applications, "documents": documents}
            for before, after, applications, documents in pair_rows
        ],
        "exclusions_by_type": [{"entity_type": entity_type, "rules": count} for entity_type, count in exclusion_rows],
    }


def corrections_stats(session) -> dict:
    """How often each approved NER correction actually fired — input for deciding which classes of
    mistake deserve a code fix instead of yet another manual rule."""
    rules = list(session.execute(select(NerCorrection)).scalars().all())
    app = NerCorrectionApplication
    usage = {
        correction_id: (applications, documents, last_applied)
        for correction_id, applications, documents, last_applied in session.execute(
            select(app.correction_id, func.count(app.id), func.count(func.distinct(app.document_id)),
                   func.max(app.applied_at))
            .where(app.correction_id.isnot(None)).group_by(app.correction_id)
        ).all()
    }
    pairs = [tuple(row) for row in session.execute(
        select(app.entity_type_before, app.entity_type_after, func.count(app.id),
               func.count(func.distinct(app.document_id)))
        .group_by(app.entity_type_before, app.entity_type_after)
        .order_by(func.count(app.id).desc())
    ).all()]
    exclusions = [tuple(row) for row in session.execute(
        select(NerExclusion.entity_type, func.count(NerExclusion.id))
        .group_by(NerExclusion.entity_type).order_by(func.count(NerExclusion.id).desc())
    ).all()]
    return build_corrections_stats(rules, usage, pairs, exclusions)
