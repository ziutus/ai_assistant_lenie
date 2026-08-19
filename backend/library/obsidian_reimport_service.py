"""Read-only import of existing Obsidian notes as Document rows (Epic 42).

Walks the pilot vault subfolders for ``.md`` files and, through the existing
``DocumentService.import_document()`` pipeline, creates a new read-only
``Document`` (``document_type="obsidian_note"``) for each file not already
imported — no new text-extraction mechanism. Embeddings are generated via the
same whole-document split+embed fallback ``documents_pipeline.py`` already
uses for documents without an approved chunk-analysis run (no LLM chunk
classification, no human review gate — required for an unattended bulk
import of hundreds of notes).

Story 42.2 adds change detection: each file's content is hashed (SHA-256,
not mtime — Obsidian Sync does not guarantee mtime survives cross-device
sync) and compared against ``Document.obsidian_source_hash`` from the
previous run. An unchanged file is skipped entirely; a changed file updates
the existing ``Document`` in place (never a duplicate) and re-embeds only
that note, discarding its stale embeddings first.

Story 42.3 adds ``library/obsidian_vault_watcher.py``, an inotify-based
watcher (via ``watchdog``) that enqueues a targeted single-note job
(``job.parameters["relative_path"]`` set) the moment a file changes, instead
of waiting for the next scheduled full scan. ``execute_obsidian_reimport()``
below handles both shapes: with ``relative_path`` it reimports exactly that
one note; without it, it falls back to the original full-vault walk, which
the schedule now runs once a day as a safety net (catches changes made while
the worker/watcher was down, and file-system events the watcher may have
missed) rather than every 5 minutes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import Document, Job
from library.document_repository import DocumentRepository
from library.document_service import DocumentService
from library.job_queue import heartbeat
from library.text_functions import get_hash

logger = logging.getLogger(__name__)

OBSIDIAN_REIMPORT = "obsidian_reimport"

# Pilot scope per PRD (913 notes) -- Informatyka + Geopolityka only, not all
# of 02-wiedza. Broadening this is a deliberate future decision, out of scope
# for this story.
#
# The Geopolityka folder's real vault name is "Geopolityka i polityka" (see
# also imports/control_questions.py, imports/import_control_questions.py,
# which already reference it correctly) -- Story 42.1 introduced this
# constant with the wrong, shortened name, so the folder was silently
# skipped (a "configured subfolder missing" warning) from day one. Fixed in
# Story 42.2 after NAS verification surfaced it.
PILOT_SUBFOLDERS = ("02-wiedza/Informatyka", "02-wiedza/Geopolityka i polityka")


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


def _reimport_one_note(
    session: Session, service: DocumentService, repo: DocumentRepository, model: str, vault_path: Path, note_path: Path
) -> str:
    """Read, hash-compare and, if needed, (re)import a single note.

    Returns one of ``"created"``, ``"updated"``, ``"skipped"``, ``"failed"``.
    Commits/rolls back its own transaction so callers (full-vault walk or a
    single-note watcher job) can process notes independently.
    """
    relative_path = note_path.relative_to(vault_path).as_posix()
    url = _note_url(relative_path)

    try:
        content = note_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("obsidian_reimport: cannot read %s: %s", note_path, exc)
        return "failed"

    if not content.strip():
        return "skipped"

    content_hash = get_hash(content)
    existing = Document.get_by_url(session, url)

    # existing.obsidian_source_hash is None for notes imported before
    # this column existed (Story 42.1) -- never equals a real hash,
    # so they fall through to the "changed" branch on the first run
    # after deploy (a one-time backfill re-embed, not a bug).
    if existing is not None and existing.obsidian_source_hash == content_hash:
        return "skipped"

    try:
        if existing is None:
            doc, _outcome = service.import_document(
                url=url,
                document_type="obsidian_note",
                skip_if_exists=True,
                title=note_path.stem,
                text=content,
                text_md=content,
                source="own",
            )
        else:
            doc = existing
            doc.text = content
            doc.text_md = content
            doc.title = note_path.stem
            # Discard stale fragments before re-embedding -- otherwise
            # search would return both the old and new versions.
            repo.embedding_delete(doc.id, model)

        doc.obsidian_source_hash = content_hash
        _embed_note(repo, doc, model)
        session.commit()
    except Exception:
        logger.exception("obsidian_reimport: import/update failed for %s", note_path)
        session.rollback()
        return "failed"

    return "created" if existing is None else "updated"


def _resolve_note_path(vault_path: Path, relative_path: str) -> Path | None:
    """Resolve a watcher-supplied relative path, refusing anything outside
    the configured pilot subfolders (defence in depth against a path-
    traversal payload reaching this far -- the watcher only ever emits
    paths it observed under those subfolders itself)."""
    candidate = (vault_path / relative_path).resolve()
    vault_resolved = vault_path.resolve()
    for subfolder in PILOT_SUBFOLDERS:
        allowed_root = (vault_resolved / subfolder).resolve()
        if candidate == allowed_root or allowed_root in candidate.parents:
            return candidate
    logger.warning("obsidian_reimport: relative_path outside pilot subfolders: %s", relative_path)
    return None


def execute_obsidian_reimport(session: Session, job: Job) -> dict:
    """Job execution function for the ``obsidian_reimport`` job type.

    With ``job.parameters["relative_path"]`` set (dispatched by
    ``obsidian_vault_watcher.py`` on a file-change event), reimports exactly
    that one note. Otherwise walks every pilot subfolder -- the daily
    safety-net run.

    Returns a summary dict: scanned/created/updated/skipped/failed file
    counts (single-note calls report scanned=1).
    """
    cfg = load_config()
    vault_path = Path(cfg.get("OBSIDIAN_VAULT_PATH", "/app/obsidian-vault"))
    model = cfg.require("EMBEDDING_MODEL")

    service = DocumentService(session)
    repo = DocumentRepository(session)

    counts = {"scanned": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

    relative_path = job.parameters.get("relative_path") if job.parameters else None
    if relative_path:
        note_path = _resolve_note_path(vault_path, relative_path)
        if note_path is None or not note_path.is_file():
            counts["failed"] = 1
            return counts
        counts["scanned"] = 1
        counts[_reimport_one_note(session, service, repo, model, vault_path, note_path)] += 1
        return counts

    for subfolder in PILOT_SUBFOLDERS:
        folder = vault_path / subfolder
        if not folder.is_dir():
            logger.warning("obsidian_reimport: configured subfolder missing: %s", folder)
            continue

        for note_path in sorted(folder.rglob("*.md")):
            counts["scanned"] += 1
            counts[_reimport_one_note(session, service, repo, model, vault_path, note_path)] += 1
            heartbeat(session, job.id, dict(counts))

    return counts
