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

from sqlalchemy import select

from library.db.models import NerCorrection, NerCorrectionApplication
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
