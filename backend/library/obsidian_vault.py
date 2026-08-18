"""Path-safety and versioned read/write for the mounted Obsidian vault (Epic 47).

Single entry point for every filesystem touch against the volume mounted at
OBSIDIAN_VAULT_PATH (Story 41.2) -- no other module may call open()/os.path
directly against vault files (architecture.md Sprint 15 enforcement rule #2).

This story (47.1) defines the module only; nothing calls write_note_with_version()
or read_note() yet -- POST /tools (Story 47.2) is the first real caller.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import ObsidianNoteVersion

DEFAULT_VAULT_PATH = "/app/obsidian-vault"


class VaultPathInvalidError(ValueError):
    """note_path resolves outside the configured Obsidian vault root."""


def _vault_root() -> str:
    cfg = load_config()
    return os.path.realpath(cfg.get("OBSIDIAN_VAULT_PATH", DEFAULT_VAULT_PATH))


def is_vault_mount_available() -> bool:
    """Check whether the vault root is currently a reachable, mounted path.

    Called ONLY from POST /tools' error handling, after write_note_with_version()
    has already raised -- never proactively / on every request. Distinguishes
    sync_container_unavailable from a generic obsidian_write_failed (Story 47.3).

    This does NOT probe obsidian-headless-sync's health in any way (no HTTP
    call, no docker inspect) -- it only checks whether the volume backing
    OBSIDIAN_VAULT_PATH is still mounted as seen from inside this container,
    per architecture.md Decision 8 ("detect it from the mount/write failure
    itself", not by polling a health endpoint on the sync container).
    """
    root = _vault_root()
    try:
        return os.path.ismount(root)
    except OSError:
        return False


def ensure_within_vault(note_path: str) -> Path:
    """Resolve note_path against the vault root, rejecting any escape.

    Symlinks are followed and `..`/absolute-path tricks are normalized by
    os.path.realpath() before the containment check, so the guard cannot be
    bypassed by an on-disk symlink pointing outside the vault, nor by an
    absolute note_path (os.path.join discards the vault root entirely when
    the second argument is absolute -- realpath() still resolves to the
    literal absolute target, which then fails the startswith check below).
    """
    root = _vault_root()
    candidate = os.path.realpath(os.path.join(root, note_path))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise VaultPathInvalidError(f"note_path escapes vault root: {note_path!r}")
    return Path(candidate)


def read_note(note_path: str) -> str | None:
    """Return a note's content, or None if it doesn't exist yet (new note)."""
    resolved = ensure_within_vault(note_path)
    if not resolved.is_file():
        return None
    return resolved.read_text(encoding="utf-8")


def _write_file_atomically(resolved: Path, content: str) -> None:
    """Write content via a same-directory temp file + atomic rename.

    os.replace() never follows a symlink at the destination -- on POSIX,
    rename() replaces the directory entry itself (the symlink), it does not
    write through to whatever the symlink points at. That defeats the
    "something swaps the destination for a symlink pointing outside the
    vault between ensure_within_vault()'s check and this write" race
    (code-review finding on Story 47.1's PR): even if that swap happens in
    the narrow window right before this call, the rename still lands on the
    vault-local path, not the symlink's external target. This also makes
    the write atomic (no truncated/corrupt file on a crash or full disk
    mid-write).
    """
    resolved.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=resolved.parent, prefix=f".{resolved.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, resolved)
    except BaseException:
        os.unlink(tmp_path)
        raise


def write_note_with_version(
    session: Session,
    note_path: str,
    content: str,
    tool_id: int | None = None,
    user_prompt: str | None = None,
) -> ObsidianNoteVersion:
    """Insert a version row, commit it, then write the file to disk.

    Caller contract (see Story 47.1 Dev Notes / architecture.md's dual-write
    sequence): if this call is part of a larger transaction (e.g. Story
    47.2's POST /tools, which flushes a new Tool row first), do so on the
    SAME session and do not commit before calling this function -- the
    commit() below lands the caller's flushed rows atomically together with
    the new ObsidianNoteVersion row. If the filesystem write below raises,
    the DB commit has already happened and is deliberately NOT rolled back
    (FR20) -- mapping that exception to obsidian_write_failed /
    sync_container_unavailable is Story 47.3's responsibility, not this
    function's.

    Concurrent writers targeting the SAME note_path are serialized by a
    PostgreSQL session-level advisory lock keyed on note_path (acquired via
    pg_advisory_lock, not the transaction-scoped pg_advisory_xact_lock --
    the lock must outlive the commit() above and still be held during the
    filesystem write below, so a second writer's content_before read can
    never observe content that a first writer's file write hasn't landed
    yet). The lock is always released in `finally`, including when the
    filesystem write raises, so a failed write never leaves the note_path
    permanently locked for the rest of this DB session/connection
    (code-review finding on Story 47.1's PR).
    """
    resolved = ensure_within_vault(note_path)

    session.execute(sa_text("SELECT pg_advisory_lock(hashtext(:note_path))"), {"note_path": note_path})
    try:
        content_before = read_note(note_path)

        version = ObsidianNoteVersion(
            note_path=note_path,
            content_before=content_before,
            content_after=content,
            user_prompt=user_prompt,
            tool_id=tool_id,
        )
        session.add(version)
        session.commit()

        _write_file_atomically(resolved, content)
    finally:
        session.execute(sa_text("SELECT pg_advisory_unlock(hashtext(:note_path))"), {"note_path": note_path})

    return version


def retry_write_note(session: Session, note_path: str, content: str) -> None:
    """Re-attempt ONLY the filesystem write for an already-versioned note (Story 47.4).

    Caller contract: the ObsidianNoteVersion row and its content_after already
    exist from the original (failed) write -- this function inserts nothing
    and commits nothing (no session.add(), no session.commit() anywhere in
    its body). It is step 7 of the dual-write sequence run in isolation from
    steps 3-6, called only from POST /tools/<id>/retry_obsidian_write once a
    prior write has genuinely failed (Tool.obsidian_note_path IS NULL). "No
    new row is ever inserted" is the structural reason a retry can never
    duplicate the entity (FR21) -- not a check that could be bypassed by a
    programming error.
    """
    resolved = ensure_within_vault(note_path)

    session.execute(sa_text("SELECT pg_advisory_lock(hashtext(:note_path))"), {"note_path": note_path})
    try:
        _write_file_atomically(resolved, content)
    finally:
        session.execute(sa_text("SELECT pg_advisory_unlock(hashtext(:note_path))"), {"note_path": note_path})
