"""Path-safety and versioned read/write for the mounted Obsidian vault (Epic 47).

Single entry point for every filesystem touch against the volume mounted at
OBSIDIAN_VAULT_PATH (Story 41.2) -- no other module may call open()/os.path
directly against vault files (architecture.md Sprint 15 enforcement rule #2).

This story (47.1) defines the module only; nothing calls write_note_with_version()
or read_note() yet -- POST /tools (Story 47.2) is the first real caller.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from library.config_loader import load_config
from library.db.models import ObsidianNoteVersion

DEFAULT_VAULT_PATH = "/app/obsidian-vault"


class VaultPathInvalidError(ValueError):
    """note_path resolves outside the configured Obsidian vault root."""


def _vault_root() -> str:
    cfg = load_config()
    return os.path.realpath(cfg.get("OBSIDIAN_VAULT_PATH", DEFAULT_VAULT_PATH))


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
    """
    resolved = ensure_within_vault(note_path)
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

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return version
