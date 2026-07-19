"""Safely rebuild normalized NER entities and their derived dependencies.

Windows: PYTHONPATH=. .venv/Scripts/python imports/refresh_entities.py --document-id 9204 --dry-run
WSL:     PYTHONPATH=. .venv/bin/python imports/refresh_entities.py --document-id 9204 --dry-run
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, select

from library.db.engine import get_session
from library.db.models import DocumentEntity, DocumentPerson, NerExclusion, WebDocument
from library.entity_service import is_excluded
from library.ner_client import aggregate_entities_detailed, extract_entities_strict
from library.ner_normalization import normalize_ner_text
from library.overpass_client import attach_document_pipelines
from library.person_registry import reject_review_link, resolve_document_persons
from library.place_verification import verify_document_places

def _family(entity_type: str) -> str:
    return "person" if entity_type == "persName" else "place"


def _terms(entity_text: str, variants: list[str] | None) -> set[str]:
    return {
        normalize_ner_text(value).casefold()
        for value in [entity_text, *(variants or [])]
        if normalize_ner_text(value)
    }


def build_canonical_map(old_rows: list, new_groups: dict[tuple[str, str], dict]) -> dict[str, str]:
    """Map old entity_text to one new canonical text via shared variants/lemmas."""
    lookup: dict[tuple[str, str], set[str]] = {}
    for (entity_type, canonical), group in new_groups.items():
        for term in _terms(canonical, [*group.get("variants", []), *group.get("raw_lemmas", [])]):
            lookup.setdefault((_family(entity_type), term), set()).add(canonical)

    mapping: dict[str, str] = {}
    for row in old_rows:
        candidates: set[str] = set()
        for term in _terms(row.entity_text, row.variants):
            candidates.update(lookup.get((_family(row.entity_type), term), set()))
        if len(candidates) == 1:
            mapping[row.entity_text] = next(iter(candidates))
    return mapping


def classify_entity_changes(old_rows: list, new_groups: dict, mapping: dict[str, str]) -> dict:
    """Return deterministic removed/renamed/merged/count-change decisions."""
    new_counts = {text: group["count"] for (_entity_type, text), group in new_groups.items()}
    target_counts = Counter(mapping.values())
    changed = sorted((old, new) for old, new in mapping.items() if old != new)
    removed = sorted(row.entity_text for row in old_rows if row.entity_text not in mapping)
    merged = sorted(target for target, count in target_counts.items() if count > 1)
    count_changes = sorted(
        (row.entity_text, row.mention_count, new_counts.get(mapping.get(row.entity_text, ""), 0))
        for row in old_rows
        if row.entity_text in mapping
        and row.mention_count != new_counts.get(mapping[row.entity_text], 0)
    )
    return {
        "removed": removed,
        "removed_count": len(removed),
        "changed": changed,
        "changed_count": len(changed),
        "merged": merged,
        "merged_count": len(merged),
        "count_changes": count_changes,
    }


def _slug(value: str) -> str:
    from unidecode import unidecode

    return re.sub(r"[^a-z0-9]+", "-", unidecode(value).lower()).strip("-")


def _orphan_tag_audit(doc, new_groups: dict) -> list[str]:
    supported = {_slug(text) for (entity_type, text) in new_groups if entity_type != "persName"}
    entity_tags = [
        tag.strip()
        for tag in (doc.tags or "").split(",")
        if tag.strip().startswith(("miejsce-", "kraj-"))
    ]
    return sorted(tag for tag in entity_tags if tag.split("-", 1)[1] not in supported)


def _filtered_groups(session, doc, raw: list[dict]) -> dict:
    groups = aggregate_entities_detailed(raw)
    exclusions = list(session.scalars(select(NerExclusion)).all())
    for key, group in list(groups.items()):
        raw_terms = [*group.get("raw_lemmas", []), *group.get("variants", [])]
        if is_excluded(exclusions, key[0], key[1], doc.byline, raw_terms=raw_terms):
            del groups[key]
    return groups


def _repair_person_links(session, doc_id: int, old_rows: list, mapping: dict[str, str]) -> dict:
    person_terms = {
        term: row.entity_text
        for row in old_rows
        if row.entity_type == "persName"
        for term in _terms(row.entity_text, row.variants)
    }
    updated = removed = deduplicated = 0
    seen_people: set[int] = set()
    links = list(session.scalars(select(DocumentPerson).where(DocumentPerson.document_id == doc_id)).all())
    for link in links:
        if link.person_id in seen_people:
            reject_review_link(session, link)
            deduplicated += 1
            continue
        seen_people.add(link.person_id)
        old_text = person_terms.get(normalize_ner_text(link.raw_mention).casefold())
        target = mapping.get(old_text) if old_text else None
        if target:
            if link.raw_mention != target:
                link.raw_mention = target
                updated += 1
        elif old_text:
            reject_review_link(session, link)
            removed += 1
    return {"updated": updated, "removed": removed, "deduplicated": deduplicated}


def repair_document(session, doc: WebDocument, *, dry_run: bool) -> dict:
    text = doc.text_md or doc.text or ""
    if not text.strip():
        raise ValueError("document has no text")
    raw = extract_entities_strict(text)
    groups = _filtered_groups(session, doc, raw)
    old_rows = list(session.scalars(select(DocumentEntity).where(DocumentEntity.document_id == doc.id)).all())
    mapping = build_canonical_map(old_rows, groups)
    changes = classify_entity_changes(old_rows, groups, mapping)
    report = {
        "document_id": doc.id,
        "dry_run": dry_run,
        "old_entities": len(old_rows),
        "new_entities": len(groups),
        "old_mentions": sum(row.mention_count for row in old_rows),
        "new_mentions": sum(group["count"] for group in groups.values()),
        **changes,
        "person_links_affected": sum(
            1
            for row in old_rows
            if row.entity_type == "persName"
            and (row.entity_text not in mapping or mapping[row.entity_text] != row.entity_text)
        ),
        "geocodes_affected": sum(
            1
            for row in old_rows
            if row.geocode_id is not None and (row.entity_text in changes["removed"] or row.entity_text in mapping)
        ),
        "suspicious_orphan_tags": _orphan_tag_audit(doc, groups),
    }
    if dry_run:
        return report

    session.execute(delete(DocumentEntity).where(DocumentEntity.document_id == doc.id))
    session.add_all([
        DocumentEntity(
            document_id=doc.id,
            entity_type=entity_type,
            entity_text=entity_text,
            mention_count=group["count"],
            variants=group["variants"],
        )
        for (entity_type, entity_text), group in groups.items()
    ])
    report["person_links"] = _repair_person_links(session, doc.id, old_rows, mapping)
    session.flush()
    report["places"] = verify_document_places(session, doc, text)
    report["persons"] = resolve_document_persons(session, doc, text)
    report["pipelines"] = attach_document_pipelines(session, doc.id)
    return report


def _load_state(path: Path) -> set[int]:
    if not path.exists():
        return set()
    return {int(value) for value in json.loads(path.read_text(encoding="utf-8"))}


def _save_state(path: Path, completed: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(completed), indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--document-id", type=int, action="append")
    selection.add_argument("--all", action="store_true", help="Documents already having document_entities rows")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-ids", type=int, nargs="*", default=[])
    parser.add_argument("--state-file", type=Path, default=Path("tmp/refresh_entities_state.json"))
    args = parser.parse_args()

    with get_session() as session:
        if args.all:
            ids = list(session.scalars(select(DocumentEntity.document_id).distinct().order_by(DocumentEntity.document_id)))
        else:
            ids = list(dict.fromkeys(args.document_id))
    completed = _load_state(args.state_file)
    ids = [doc_id for doc_id in ids if doc_id not in completed and doc_id not in set(args.skip_ids)]
    if args.limit is not None:
        ids = ids[:args.limit]

    failures = 0
    for doc_id in ids:
        with get_session() as session:
            try:
                doc = session.get(WebDocument, doc_id)
                if doc is None:
                    raise ValueError("document not found")
                report = repair_document(session, doc, dry_run=args.dry_run)
                if args.dry_run:
                    session.rollback()
                else:
                    session.commit()
                    completed.add(doc_id)
                    _save_state(args.state_file, completed)
                print(json.dumps(report, ensure_ascii=False, default=str))
            except Exception as exc:
                session.rollback()
                failures += 1
                print(json.dumps({"document_id": doc_id, "error": str(exc)}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
