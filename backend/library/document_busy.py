"""Per-document exclusion between long text-touching operations.

Splitting a transcript into paragraphs rewrites ``Document.text`` at the end of a
long model run (up to 15 minutes), while NER, country and geopolitics detection read
that text for just as long.  Letting them overlap means detection works on text that
is replaced under it, or two splits overwrite each other.  Each of these operations
claims the document here first and the route answers 409 when somebody holds it.

The registry lives in process memory: it protects concurrent requests served by one
backend process (threads), which is how the NAS runs it.  It is not a distributed lock.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

_lock = threading.Lock()
_active: dict[int, str] = {}


class DocumentBusy(Exception):
    """Another long operation holds the document; ``holder`` names it."""

    def __init__(self, holder: str):
        super().__init__(holder)
        self.holder = holder


@contextmanager
def claim_document(doc_id: int, operation: str) -> Iterator[None]:
    """Hold ``doc_id`` exclusively for ``operation``; raise DocumentBusy if it is taken."""
    with _lock:
        holder = _active.get(doc_id)
        if holder is not None:
            raise DocumentBusy(holder)
        _active[doc_id] = operation
    try:
        yield
    finally:
        with _lock:
            _active.pop(doc_id, None)


def busy_response(exc: DocumentBusy) -> tuple[dict, int]:
    """409 body shared by the routes that claim a document."""
    return {
        "status": "error",
        "message": f"Dokument jest zajęty inną operacją ({exc.holder}). Poczekaj, aż się skończy.",
        "busy_with": exc.holder,
    }, 409
