"""Trial run of narrative detection on a sample of public library documents.

Read-only: reads webpage documents from the database, scores them against a
narrative set seed file via Fabryka Basal and writes a JSON report. Nothing is
written to the database. Private document types (obsidian_note, email, ...) are
never selected: the free Fabryka tier may retain submitted content.

Usage (from backend/):
    PYTHONPATH=. python imports/narrative_trial.py --out report.json \
        [--seed data/narratives/ru_viedm_2026_10.json] [--related 20] [--control 6] \
        [--max-pieces 4] [--ids 10774,123]
"""

import argparse
import json
import logging

from sqlalchemy import func, select

from library.db.engine import get_session
from library.db.models import Document
from library.narrative_service import load_seed, score_text

logger = logging.getLogger(__name__)

PUBLIC_TYPES = ("webpage",)
MIN_CHARS = 1500
MAX_CHARS = 60000


def _text_of(doc: Document) -> str:
    return doc.text_md or doc.text or ""


def pick_documents(session, related: int, control: int, ids: list[int]) -> list[tuple[str, Document]]:
    """Explicit ids first, then newest Russia/Ukraine-related pages, then random unrelated controls."""
    picked: dict[int, tuple[str, Document]] = {}

    def add(label: str, docs) -> None:
        for d in docs:
            if d.id not in picked and MIN_CHARS <= len(_text_of(d)) <= MAX_CHARS:
                picked[d.id] = (label, d)

    base = select(Document).where(Document.document_type.in_(PUBLIC_TYPES))
    if ids:
        add("explicit", session.execute(select(Document).where(Document.id.in_(ids))).scalars())
    topical = base.where(Document.text.ilike("%Rosj%"), Document.text.ilike("%Ukrain%")) \
        .order_by(Document.id.desc()).limit(related * 3)
    add("related", list(session.execute(topical).scalars())[: related * 3])
    # trim "related" to the requested count (explicit ids are kept in addition)
    related_ids = [i for i, (lbl, _) in picked.items() if lbl == "related"][related:]
    for i in related_ids:
        del picked[i]
    unrelated = base.where(~Document.text.ilike("%Rosj%"), ~Document.text.ilike("%Ukrain%")) \
        .order_by(func.random()).limit(control * 3)
    before = len(picked)
    for d in session.execute(unrelated).scalars():
        if len(picked) - before >= control:
            break
        add("control", [d])
    return list(picked.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", default="data/narratives/ru_viedm_2026_10.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--related", type=int, default=20)
    parser.add_argument("--control", type=int, default=6)
    parser.add_argument("--max-pieces", type=int, default=4)
    parser.add_argument("--ids", default="", help="comma-separated document ids to include")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    narrative_set, narratives = load_seed(args.seed)
    ids = [int(x) for x in args.ids.split(",") if x.strip()]

    report = {"set": narrative_set["slug"], "documents": []}
    session = get_session()
    try:
        for label, doc in pick_documents(session, args.related, args.control, ids):
            text = _text_of(doc)
            logger.info("[%s] #%s %s (%d chars)", label, doc.id, (doc.title or "")[:70], len(text))
            try:
                scores = score_text(text, narratives, max_pieces=args.max_pieces)
            except Exception as e:  # noqa: BLE001 - trial script: record and continue
                logger.warning("  failed: %s", e)
                report["documents"].append({"id": doc.id, "label": label, "title": doc.title, "error": str(e)})
                continue
            top = sorted(scores.items(), key=lambda kv: kv[1]["probability"], reverse=True)[:5]
            logger.info("  top: %s", ", ".join(f"{c}={s['probability']:.2f}" for c, s in top))
            report["documents"].append({
                "id": doc.id, "label": label, "title": doc.title, "url": doc.url, "chars": len(text),
                "scores": {c: {"p": round(s["probability"], 3), "confidence": s["confidence"], "piece": s["piece"]}
                           for c, s in scores.items()},
            })
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
