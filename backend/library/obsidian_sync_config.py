"""Which Obsidian vault subfolders are synchronized into Lenie.

The list lives in configuration (Vault KV), not in code, so adding a folder is
a config change plus a worker restart instead of a PR and a deploy. The key
``OBSIDIAN_SYNC_SUBFOLDERS`` holds a JSON text::

    [
      {"path": "02-wiedza/Informatyka", "is_private": false},
      {"path": "Journal", "is_private": true}
    ]

Rules (a mistake here can leak private notes into shared search, so the loader
is strict and never guesses):

- ``is_private`` is optional and defaults to ``true`` -- a folder has to be
  made public explicitly. Only real JSON booleans are accepted.
- ``Journal`` and anything below it can never be public.
- Paths are vault-relative, POSIX style; absolute paths, ``..``, ``.`` and
  backslashes are rejected, and entries must not be duplicated or nested in
  one another (the same note would otherwise get two different privacy flags).
- ``[]`` disables synchronization. Empty text, invalid JSON, unknown fields or
  bad entries raise :class:`ObsidianSyncConfigError` -- there is deliberately
  no fallback on error.
- Only an *absent* key may fall back (to ``fallback``, with a warning); that is
  the transitional path for deployments that have not set the key yet.

The configuration is read once per process (worker start / job execution), so
changing the list takes effect after the worker is restarted.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

logger = logging.getLogger(__name__)

CONFIG_KEY = "OBSIDIAN_SYNC_SUBFOLDERS"
PRIVATE_ROOTS = ("Journal",)

_ALLOWED_ENTRY_KEYS = {"path", "is_private"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class ObsidianSyncConfigError(ValueError):
    """The ``OBSIDIAN_SYNC_SUBFOLDERS`` value is missing structure or unsafe."""


@dataclass(frozen=True)
class SyncFolder:
    path: str
    is_private: bool


def _normalize_path(raw: Any, index: int) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ObsidianSyncConfigError(f"entry {index}: 'path' must be a non-empty string")
    path = raw.strip()
    if "\\" in path or "\x00" in path:
        raise ObsidianSyncConfigError(f"entry {index}: path must use '/' separators: {path!r}")
    if path.startswith("/") or _DRIVE_RE.match(path):
        raise ObsidianSyncConfigError(f"entry {index}: path must be relative to the vault: {path!r}")
    parts = PurePosixPath(path).parts
    if not parts or any(part in (".", "..") for part in parts):
        raise ObsidianSyncConfigError(f"entry {index}: path must not contain '.' or '..' segments: {path!r}")
    return "/".join(parts)


def _is_private_root(path: str) -> bool:
    return any(path == root or path.startswith(root + "/") for root in PRIVATE_ROOTS)


def parse_sync_folders(raw: Any) -> tuple[SyncFolder, ...]:
    """Parse and validate the JSON text of ``OBSIDIAN_SYNC_SUBFOLDERS``."""
    if not isinstance(raw, str) or not raw.strip():
        raise ObsidianSyncConfigError(f"{CONFIG_KEY} is set but empty; use [] to disable synchronization")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ObsidianSyncConfigError(f"{CONFIG_KEY} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ObsidianSyncConfigError(f"{CONFIG_KEY} must be a JSON list")

    folders: list[SyncFolder] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ObsidianSyncConfigError(f"entry {index}: must be an object")
        unknown = set(entry) - _ALLOWED_ENTRY_KEYS
        if unknown:
            raise ObsidianSyncConfigError(f"entry {index}: unknown fields {sorted(unknown)}")
        if "path" not in entry:
            raise ObsidianSyncConfigError(f"entry {index}: missing 'path'")
        path = _normalize_path(entry["path"], index)
        is_private = entry.get("is_private", True)
        if not isinstance(is_private, bool):
            raise ObsidianSyncConfigError(f"entry {index}: 'is_private' must be true or false")
        if not is_private and _is_private_root(path):
            raise ObsidianSyncConfigError(f"entry {index}: {path!r} is under a private root and cannot be public")
        folders.append(SyncFolder(path=path, is_private=is_private))

    _reject_overlaps(folders)
    return tuple(folders)


def _reject_overlaps(folders: list[SyncFolder]) -> None:
    for i, first in enumerate(folders):
        for second in folders[i + 1 :]:
            a, b = first.path, second.path
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                raise ObsidianSyncConfigError(f"overlapping folders: {a!r} and {b!r}")


def load_sync_folders(cfg: Any, fallback: Iterable[tuple[str, bool]] = ()) -> tuple[SyncFolder, ...]:
    """Read the configured folders. An absent key uses ``fallback`` (warning);
    any present-but-bad value raises :class:`ObsidianSyncConfigError`."""
    raw = cfg.get(CONFIG_KEY)
    if raw is None:
        folders = tuple(SyncFolder(path, is_private) for path, is_private in fallback)
        logger.warning(
            "%s is not set; using the built-in transitional list (%d folders). Set the key in Vault.",
            CONFIG_KEY,
            len(folders),
        )
        _reject_overlaps(list(folders))
        return folders
    return parse_sync_folders(raw)
