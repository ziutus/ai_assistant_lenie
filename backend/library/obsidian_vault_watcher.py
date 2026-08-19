"""inotify-based watcher for the Obsidian vault pilot subfolders (Story 42.3).

Runs on its own ``watchdog`` Observer thread inside the coordinator
(``--scheduler``) ``lenie-worker`` process, alongside the existing
claim/execute polling loop. The vault is a plain local Docker volume (not
NFS/SMB — see ``infra/docker/compose.nas.yaml``), so kernel inotify events
are available and reliable.

On a create/modify/move event for a ``.md`` file under one of
``obsidian_reimport_service.PILOT_SUBFOLDERS``, debounces per relative path
(editors and Obsidian Sync commonly write a file more than once per logical
edit) and then enqueues a *targeted* ``obsidian_reimport`` job for that one
note — see ``obsidian_reimport_service.execute_obsidian_reimport()``'s
``relative_path`` branch. The full-vault scan (no ``relative_path``) stays as
the daily scheduled safety net for changes made while the watcher was down.

This replaces the every-5-minutes full-vault hash scan (Story 42.2) that
turned out to spam thousands of near-instant "nothing changed" job runs per
day — see the ``_schedule_obsidian_reimport`` docstring in ``worker.py`` —
with an event-driven trigger scoped to the one file that actually changed.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from library.db.models import Job
from library.job_queue import enqueue
from library.obsidian_reimport_service import PILOT_SUBFOLDERS

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 5.0
ACTIVE_STATUSES = ("queued", "running", "cancel_requested")


class DebouncedReimportHandler(FileSystemEventHandler):
    """Coalesces bursty filesystem events into one enqueue call per note.

    ``session_factory`` is called fresh for every enqueue -- the debounce
    timers fire on watchdog's own background thread, and a SQLAlchemy
    Session is not safe to share across threads with the main worker loop.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        vault_path: Path,
        debounce_seconds: float = DEBOUNCE_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._vault_path = vault_path
        self._debounce_seconds = debounce_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event.src_path, event.is_directory)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event.src_path, event.is_directory)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Editors / Obsidian Sync often write a temp file then rename it
        # into place -- the rename's destination is the one that matters.
        self._handle(event.dest_path, event.is_directory)

    def _handle(self, raw_path: str, is_directory: bool) -> None:
        if is_directory or not raw_path.endswith(".md"):
            return
        self._schedule(Path(raw_path))

    def _schedule(self, path: Path) -> None:
        try:
            relative_path = path.relative_to(self._vault_path).as_posix()
        except ValueError:
            return

        with self._lock:
            existing_timer = self._timers.get(relative_path)
            if existing_timer is not None:
                existing_timer.cancel()
            timer = threading.Timer(self._debounce_seconds, self._enqueue, args=(relative_path,))
            timer.daemon = True
            self._timers[relative_path] = timer
            timer.start()

    def _enqueue(self, relative_path: str) -> None:
        with self._lock:
            self._timers.pop(relative_path, None)

        session = self._session_factory()
        try:
            active = session.scalar(
                select(Job.id)
                .where(
                    Job.type == "obsidian_reimport",
                    Job.status.in_(ACTIVE_STATUSES),
                    Job.parameters["relative_path"].as_string() == relative_path,
                )
                .limit(1)
            )
            if active is not None:
                # Already-queued job reads the file fresh when it runs, so
                # it will pick up this latest write -- no need to duplicate.
                return
            enqueue(session, "obsidian_reimport", {"relative_path": relative_path})
        except Exception:
            logger.exception("obsidian_vault_watcher: failed to enqueue reimport for %s", relative_path)
            session.rollback()
        finally:
            session.close()


def start_watcher(session_factory: Callable[[], Session], vault_path: Path) -> Observer | None:
    """Start a background Observer watching the pilot subfolders for ``.md``
    changes. Returns the started Observer, or ``None`` if none of the pilot
    subfolders exist (nothing to watch)."""
    handler = DebouncedReimportHandler(session_factory, vault_path)
    observer = Observer()
    watched_any = False
    for subfolder in PILOT_SUBFOLDERS:
        folder = vault_path / subfolder
        if not folder.is_dir():
            logger.warning("obsidian_vault_watcher: configured subfolder missing: %s", folder)
            continue
        observer.schedule(handler, str(folder), recursive=True)
        watched_any = True

    if not watched_any:
        return None

    observer.daemon = True
    observer.start()
    logger.info("obsidian_vault_watcher: watching pilot subfolders under %s", vault_path)
    return observer
