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
previous run. An unchanged file with complete embeddings is skipped; a changed file updates
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

YAML front matter (``---\ntags: [...]\n---``) is stripped from the stored
``text``/``text_md`` and its ``tags`` field is merged into
``Document.tags`` (see ``_parse_frontmatter()``/``_merge_tags()``) —
previously the whole block was stored verbatim as document text, so it
polluted embeddings and Obsidian tags never reached Lenie's own tag system.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from sqlalchemy import select
from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.country_gazetteer import count_country_mentions, detect_countries
from library.content_group_suggestion_service import request_suggestions
from library.db.models import Document, DocumentEmbedding, Job
from library.document_repository import DocumentRepository
from library.document_service import DocumentService
from library.job_queue import heartbeat
from library.obsidian_sync_config import ObsidianSyncConfigError, SyncFolder, load_sync_folders
from library.text_functions import get_hash

logger = logging.getLogger(__name__)

OBSIDIAN_REIMPORT = "obsidian_reimport"

# Transitional default. The folders synchronized from the vault now come from
# the ``OBSIDIAN_SYNC_SUBFOLDERS`` config key (see obsidian_sync_config.py);
# this tuple is only used while that key is absent from the deployment's
# config, and doubles as the migration snapshot to copy into Vault.
#
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
# "Architektura i urbanistyka" was added deliberately (2026-10) so notes written
# by /lenie-obsidian-note from articles become searchable in Lenie too.
# The root journal folder is private and carries a personal-data warning.
PILOT_SUBFOLDERS: tuple[tuple[str, bool], ...] = (
    ("02-wiedza/Informatyka", False),
    ("02-wiedza/Geopolityka i polityka", False),
    ("02-wiedza/Architektura i urbanistyka", False),
    ("Journal", True),
)


# Obsidian requires front matter to open on the file's very first line --
# a note starting mid-paragraph with a literal "---" line is a Markdown
# thematic break, not front matter, so the pattern is anchored at ^.
_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?\r?\n)---[ \t]*\r?\n?", re.DOTALL)


def _normalize_obsidian_tag(raw: str) -> str:
    """Flatten one Obsidian tag into Lenie's flat, hyphenated tag format.

    Obsidian nested tags ("wiedza/informatyka") become "wiedza-informatyka" --
    Lenie's `document.tags` is a flat comma-separated list (see
    THEMATIC_TAGS/COUNTRY_TAG_TRIGGERS in article_tagging.py), it has no
    hierarchy concept. Commas are stripped rather than escaped since they
    are the tag list's own separator.
    """
    tag = raw.strip().lstrip("#").strip().lower().replace("/", "-").replace(",", "")
    return re.sub(r"\s+", "-", tag)


def _frontmatter_tags(data: dict) -> list[str]:
    """Normalize the `tags` front matter field, whatever shape Obsidian used.

    Accepts a YAML list (`tags:\\n  - a\\n  - b`), a single scalar
    (`tags: a`), or a comma-separated scalar (`tags: a, b`) -- all valid
    forms users type by hand. Anything else (missing key, wrong type) is
    treated as "no tags" rather than raised.
    """
    raw_tags = data.get("tags")
    if isinstance(raw_tags, list):
        candidates = [str(t) for t in raw_tags]
    elif isinstance(raw_tags, str):
        candidates = raw_tags.split(",")
    else:
        candidates = []
    normalized = [_normalize_obsidian_tag(t) for t in candidates]
    return [t for t in normalized if t]


def _parse_frontmatter(content: str) -> tuple[str, list[str]]:
    """Split a note into (body without front matter, normalized tags list).

    Malformed YAML or a non-mapping front matter block degrades to "no
    front matter" (the raw content is kept as-is, no tags) rather than
    failing the import -- an unattended bulk/watch import must never break
    on one user's hand-edited YAML typo.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return content, []

    yaml = YAML(typ="safe")
    try:
        data = yaml.load(match.group(1))
    except YAMLError:
        logger.warning("obsidian_reimport: malformed front matter, keeping raw content")
        return content, []

    body = content[match.end():].lstrip("\n")
    if not isinstance(data, dict):
        return body, []
    return body, _frontmatter_tags(data)


def _merge_tags(existing_csv: str | None, new_tags: list[str]) -> str | None:
    """Union existing document tags with front-matter tags, order-preserving.

    Never removes a tag -- an obsidian_note bypasses the LLM tagging
    pipeline entirely, so front matter is the only automatic source, but a
    tag added manually in the reader/editor (or a tag since removed from
    the note in Obsidian) must survive a reimport untouched.
    """
    if not new_tags:
        return existing_csv
    existing = [t.strip() for t in (existing_csv or "").split(",") if t.strip()]
    merged = list(dict.fromkeys(existing + new_tags))
    return ",".join(merged)


# A note about one country names it in the title; broader notes (regional
# overviews) mention several. Body countries count only when mentioned often
# enough, capped, so a passing "Rosja" in a note about Sudan adds no tag.
_BODY_COUNTRY_MIN_MENTIONS = 4
_BODY_COUNTRY_MAX_TAGS = 3


def detect_country_tags(title: str, body: str) -> list[str]:
    """``kraj-<slug>`` tags for an Obsidian note, from the gazetteer only (no LLM).

    Title countries are always tagged (a note titled "Sudan" is about Sudan,
    even when its body names the country rarely); body countries need
    ``_BODY_COUNTRY_MIN_MENTIONS`` mentions, at most ``_BODY_COUNTRY_MAX_TAGS``.
    Feeds the reader's country map, which renders only for ``kraj-*`` tags.
    """
    tags = [f"kraj-{entry.slug}" for entry in detect_countries(title)]
    frequent = [
        entry for entry, count in count_country_mentions(body)
        if count >= _BODY_COUNTRY_MIN_MENTIONS
    ][:_BODY_COUNTRY_MAX_TAGS]
    tags += [f"kraj-{entry.slug}" for entry in frequent]
    return list(dict.fromkeys(tags))


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
    import library.embedding as embedding

    source = doc.text_md or doc.text or ""
    if not source:
        return 0
    if not doc.language:
        doc.language = "pl"

    created = 0
    for cleaned in _embedding_parts(source):
        result = embedding.get_embedding(model=model, text=cleaned)
        if result.status != "success" or not result.embedding:
            raise RuntimeError(f"Embedding failed for document {doc.id}: {result.status}")
        repo.embedding_add(doc.id, result.embedding, doc.language, cleaned, cleaned, model)
        created += 1
    return created


def _embedding_parts(source: str) -> list[str]:
    from library.lenie_markdown import md_remove_markdown, md_split_for_emb

    return [cleaned for part in md_split_for_emb(source) if (cleaned := md_remove_markdown(part).strip())]


def _has_complete_embeddings(session: Session, doc_id: int, model: str, parts: list[str]) -> bool:
    # Compare the actual fragments, including duplicates, rather than accepting
    # one surviving vector from a legacy partially successful import.
    stored = session.scalars(select(DocumentEmbedding.text).where(
        DocumentEmbedding.document_id == doc_id,
        DocumentEmbedding.model == model,
        DocumentEmbedding.embedding.is_not(None),
    )).all()
    return Counter(stored) == Counter(parts)


def _reimport_one_note(
    session: Session, service: DocumentService, repo: DocumentRepository, model: str, vault_path: Path, note_path: Path,
    is_private: bool,
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

    # Hashed on the raw file (front matter included) so a tags-only edit in
    # Obsidian still counts as "changed" and re-syncs document.tags below.
    content_hash = get_hash(content)
    existing = Document.get_by_url(session, url)

    # existing.obsidian_source_hash is None for notes imported before
    # this column existed (Story 42.1) -- never equals a real hash,
    # so they fall through to the "changed" branch on the first run
    # after deploy (a one-time backfill re-embed, not a bug).
    body, fm_tags = _parse_frontmatter(content)

    try:
        if existing is not None and existing.obsidian_source_hash == content_hash:
            parts = _embedding_parts(body)
            if _has_complete_embeddings(session, existing.id, model, parts):
                # Repairs legacy URL_ADDED rows without paying to embed them
                # again. Empty/frontmatter-only notes have nothing to index.
                status = "EMBEDDING_EXIST" if parts else "DOCUMENT_INTO_DATABASE"
                if (existing.processing_status != status or existing.processing_error_code is not None
                        or existing.is_private != is_private):
                    existing.is_private = is_private
                    existing.processing_status = status
                    existing.processing_error_code = None
                    session.commit()
                return "skipped"

        if existing is None:
            doc, _outcome = service.import_document(
                url=url,
                document_type="obsidian_note",
                processing_status="READY_FOR_EMBEDDING",
                skip_if_exists=True,
                title=note_path.stem,
                text=body,
                text_md=body,
                source="own",
                is_private=is_private,
                tags=_merge_tags(None, fm_tags + detect_country_tags(note_path.stem, body)),
            )
        else:
            doc = existing
            doc.text = body
            doc.text_md = body
            doc.title = note_path.stem
            doc.tags = _merge_tags(doc.tags, fm_tags + detect_country_tags(note_path.stem, body))
            # Discard stale fragments before re-embedding -- otherwise
            # search would return both the old and new versions.
            repo.embedding_delete(doc.id, model)

        doc.is_private = is_private
        doc.processing_status = "READY_FOR_EMBEDDING"
        created = _embed_note(repo, doc, model)
        doc.processing_status = "EMBEDDING_EXIST" if created else "DOCUMENT_INTO_DATABASE"
        doc.processing_error_code = None
        # Only a complete attempt can mark this source version as processed.
        # Rollback also restores old vectors deleted above if any part fails.
        doc.obsidian_source_hash = content_hash
        session.commit()
    except Exception:
        logger.exception("obsidian_reimport: import/update failed for %s", note_path)
        session.rollback()
        return "failed"

    # Best-effort: a classification failure must never fail the note import
    # itself (same defensive pattern as record_llm_usage() in ai.py). Runs
    # asynchronously via the content_group_suggest job -- see
    # content_group_suggestion_service.execute_suggestion_job() for the
    # auto-apply logic that classifies obsidian_note documents unattended.
    try:
        request_suggestions(session, "document", doc.id, user_id=None)
    except Exception:
        logger.exception("obsidian_reimport: failed to enqueue content group suggestion for document %s", doc.id)

    return "created" if existing is None else "updated"


def _is_safe_note(vault_path: Path, note_path: Path, allowed_root: Path) -> bool:
    """A note is readable only if neither it nor any directory between the
    vault root and it is a symlink and it really resolves inside ``allowed_root``
    (a symlink in a synced vault could otherwise point at a file outside the
    configured folders)."""
    try:
        relative = note_path.relative_to(vault_path)
    except ValueError:
        return False
    current = vault_path
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    resolved = note_path.resolve()
    return resolved == allowed_root or allowed_root in resolved.parents


def _resolve_note_path(
    vault_path: Path, relative_path: str, folders: Sequence[SyncFolder]
) -> tuple[Path, bool] | None:
    """Resolve a watcher-supplied relative path, refusing anything outside
    the configured sync folders (defence in depth against a path-traversal
    payload reaching this far -- the watcher only ever emits paths it
    observed under those folders itself) and anything reached via a symlink."""
    vault_resolved = vault_path.resolve()
    lexical = vault_path / relative_path
    for folder in folders:
        allowed_root = (vault_resolved / folder.path).resolve()
        if _is_safe_note(vault_path, lexical, allowed_root):
            return lexical.resolve(), folder.is_private
    logger.warning("obsidian_reimport: relative_path outside sync folders: %s", relative_path)
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
    try:
        folders = load_sync_folders(cfg, fallback=PILOT_SUBFOLDERS)
    except ObsidianSyncConfigError:
        logger.exception("obsidian_reimport: invalid OBSIDIAN_SYNC_SUBFOLDERS, nothing imported")
        raise

    service = DocumentService(session)
    repo = DocumentRepository(session)

    counts = {"scanned": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

    relative_path = job.parameters.get("relative_path") if job.parameters else None
    if relative_path:
        resolved = _resolve_note_path(vault_path, relative_path, folders)
        if resolved is None or not resolved[0].is_file():
            counts["failed"] = 1
            return counts
        note_path, is_private = resolved
        counts["scanned"] = 1
        counts[_reimport_one_note(session, service, repo, model, vault_path, note_path, is_private)] += 1
        return counts

    # Pace full scans, including unchanged notes; zero disables the pause.
    scan_throttle_seconds = float(cfg.get("OBSIDIAN_SCAN_THROTTLE_SECONDS", "0.2"))

    vault_resolved = vault_path.resolve()
    for sync_folder in folders:
        folder = vault_path / sync_folder.path
        if not folder.is_dir():
            logger.warning("obsidian_reimport: configured subfolder missing: %s", folder)
            continue
        allowed_root = (vault_resolved / sync_folder.path).resolve()

        for note_path in sorted(folder.rglob("*.md")):
            if not _is_safe_note(vault_path, note_path, allowed_root):
                logger.warning("obsidian_reimport: skipping note outside sync folder or behind a symlink: %s", note_path)
                continue
            counts["scanned"] += 1
            counts[
                _reimport_one_note(session, service, repo, model, vault_path, note_path, sync_folder.is_private)
            ] += 1
            heartbeat(session, job.id, dict(counts))
            if scan_throttle_seconds > 0:
                time.sleep(scan_throttle_seconds)

    return counts
