"""Read-only import of existing Obsidian notes as Document rows (Epic 42, Story 42.1).

Walks the pilot vault subfolders for ``.md`` files and creates a new,
read-only ``Document`` (``document_type="obsidian_note"``) for each file not
already imported, through the existing ``DocumentService.import_document()``
pipeline — no new text-extraction mechanism. Embeddings are generated via the
same whole-document split+embed fallback ``documents_pipeline.py`` already
uses for documents without an approved chunk-analysis run (no LLM chunk
classification, no human review gate — required for an unattended bulk
import of hundreds of notes).

Detecting file changes and updating already-imported notes is Story 42.2's
scope; this module only ever creates new documents (``skip_if_exists=True``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Job
from library.document_repository import DocumentRepository
from library.document_service import DocumentService
from library.job_queue import heartbeat

logger = logging.getLogger(__name__)

OBSIDIAN_REIMPORT = "obsidian_reimport"

# Pilot scope per PRD (913 notes) -- Informatyka + Geopolityka only, not all
# of 02-wiedza. Broadening this is a deliberate future decision, out of scope
# for this story.
PILOT_SUBFOLDERS = ("02-wiedza/Informatyka", "02-wiedza/Geopolityka")


def _note_url(relative_path: str) -> str:
    """Synthetic, stable identity key for dedup via Document.get_by_url().

    Mirrors the existing gmail://... (email import) and
    file:///ksiazki/<slug>.pdf (book PDF import) synthetic-URL conventions.
    """
    return f"obsidian://{relative_path}"


def _embed_note(repo: DocumentRepository, doc, model: str) -> int:
    """Whole-document split + embed, no chunk_id.

    Same fallback path documents_pipeline.py's _embed_document_from_markdown()
    uses for youtube/webpage documents without an approved chunk-analysis
    run -- deliberately not document_analysis_service.create_run(), which
    defaults chunks to status="pending" and would block an unattended import
    of hundreds of notes on a non-existent auto-approval mechanism.
    """
    from library.lenie_markdown import md_remove_markdown, md_split_for_emb
    import library.embedding as embedding

    source = doc.text_md or doc.text or ""
    if not source:
        return 0
    if not doc.language:
        doc.language = "pl"

    created = 0
    for part in md_split_for_emb(source):
        cleaned = md_remove_markdown(part).strip()
        if not cleaned:
            continue
        result = embedding.get_embedding(model=model, text=cleaned)
        if result.status != "success" or not result.embedding:
            logger.warning("obsidian_reimport: embedding failed for document %s: %s", doc.id, result.status)
            continue
        repo.embedding_add(doc.id, result.embedding, doc.language, cleaned, cleaned, model)
        created += 1
    return created


def execute_obsidian_reimport(session: Session, job: Job) -> dict:
    """Job execution function for the ``obsidian_reimport`` job type.

    Returns a summary dict: scanned/created/skipped/failed file counts.
    """
    cfg = load_config()
    vault_path = Path(cfg.get("OBSIDIAN_VAULT_PATH", "/app/obsidian-vault"))
    model = cfg.require("EMBEDDING_MODEL")

    service = DocumentService(session)
    repo = DocumentRepository(session)

    scanned = created = skipped = failed = 0
    for subfolder in PILOT_SUBFOLDERS:
        folder = vault_path / subfolder
        if not folder.is_dir():
            logger.warning("obsidian_reimport: configured subfolder missing: %s", folder)
            continue

        for note_path in sorted(folder.rglob("*.md")):
            scanned += 1
            relative_path = note_path.relative_to(vault_path).as_posix()

            try:
                content = note_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("obsidian_reimport: cannot read %s: %s", note_path, exc)
                failed += 1
                continue

            if not content.strip():
                skipped += 1
                continue

            try:
                doc, outcome = service.import_document(
                    url=_note_url(relative_path),
                    document_type="obsidian_note",
                    skip_if_exists=True,
                    title=note_path.stem,
                    text=content,
                    text_md=content,
                    source="own",
                )
            except Exception:
                logger.exception("obsidian_reimport: import failed for %s", note_path)
                session.rollback()
                failed += 1
                continue

            if outcome == "skipped":
                skipped += 1
                continue

            try:
                _embed_note(repo, doc, model)
                session.commit()
                created += 1
            except Exception:
                logger.exception("obsidian_reimport: embedding failed for document %s", doc.id)
                session.rollback()
                failed += 1

            heartbeat(session, job.id, {"scanned": scanned, "created": created, "skipped": skipped, "failed": failed})

    return {"scanned": scanned, "created": created, "skipped": skipped, "failed": failed}
