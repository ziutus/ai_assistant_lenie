"""The reviewer's decisions about words the spellcheck panel flagged, reused so later runs spend no model call.

* ``accepted`` — the word is a speech-to-text slip and the reviewer approved a spelling for it. The same word in a
  later transcript of the SAME channel is offered with that spelling straight from here (no model call); once two
  different documents confirmed the pair it is *trusted* and the panel pre-ticks it.
* ``rejected`` — the word is not a slip (a term, a name the dictionary lacks). It is skipped without a model call.

The newest decision wins: accepting a word drops its earlier rejection and rejecting it drops its approved
spellings. Documents without a channel (``byline``) share one bucket. Nothing here edits a transcript.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select

from library.db.models import TranscriptSpellcheckMemory as Memory
from library.transcript_corrections import normalize_author

logger = logging.getLogger(__name__)

TRUSTED_DOCUMENTS = 2  # distinct documents of a channel that confirmed a pair before it is pre-ticked
MAX_DOCUMENT_IDS = 100
MAX_DECISIONS = 200
MAX_WORD_LENGTH = 200
MAX_REPLACEMENT_LENGTH = 500
DECISIONS = ("accepted", "rejected")


class MemoryValidationError(ValueError):
    """A decision the panel sent is not storable."""


@dataclass(frozen=True)
class Remembered:
    id: int
    original: str
    replacement: str | None
    decision: str
    documents: int
    times: int

    @property
    def trusted(self) -> bool:
        return self.decision == "accepted" and self.documents >= TRUSTED_DOCUMENTS


def author_key(author) -> str:
    return normalize_author(author if isinstance(author, str) else None) or ""


def word_key(word: str) -> str:
    return " ".join(word.split()).casefold()


def lookup(session, author, words) -> dict[str, Remembered]:
    """Remembered decision per word key (``word_key``) for this channel; the shared bucket fills the gaps.

    Of several approved spellings of one word the one confirmed by most documents wins.
    """
    keys = {word_key(word) for word in words if isinstance(word, str) and word.strip()}
    if not keys:
        return {}
    channel = author_key(author)
    rows = session.scalars(select(Memory).where(
        Memory.original_key.in_(keys), Memory.author_key.in_({channel, ""}),
    ))
    best: dict[str, tuple[tuple, Remembered]] = {}
    for row in rows:
        documents = len(row.document_ids or [])
        found = Remembered(row.id, row.original, row.replacement, row.decision, documents, row.times or 1)
        rank = (row.author_key == channel and bool(channel), documents, row.times or 1, row.id)
        if row.original_key not in best or rank > best[row.original_key][0]:
            best[row.original_key] = (rank, found)
    return {key: item for key, (_, item) in best.items()}


def _clean(decision) -> tuple[str, str, str | None]:
    if not isinstance(decision, dict):
        raise MemoryValidationError("Decyzja musi być obiektem.")
    original, kind = decision.get("original"), decision.get("decision")
    if not isinstance(original, str) or not original.strip() or len(original) > MAX_WORD_LENGTH:
        raise MemoryValidationError("original musi być niepustym tekstem.")
    if kind not in DECISIONS:
        raise MemoryValidationError("decision musi być accepted albo rejected.")
    original = " ".join(original.split())
    if kind == "rejected":
        return original, kind, None
    replacement = decision.get("replacement")
    if not isinstance(replacement, str) or not replacement.strip() or len(replacement) > MAX_REPLACEMENT_LENGTH:
        raise MemoryValidationError("Zaakceptowana poprawka wymaga niepustego replacement.")
    replacement = " ".join(replacement.split())
    if replacement.casefold() == original.casefold():
        raise MemoryValidationError("replacement musi się różnić od original.")
    return original, kind, replacement


def record_decisions(session, *, document_id: int, author, decisions) -> dict[str, int]:
    """Store the decisions of one panel session (flushes, the caller commits). Returns counts per decision."""
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= MAX_DECISIONS:
        raise MemoryValidationError(f"decisions musi być listą od 1 do {MAX_DECISIONS} wpisów.")
    cleaned = [_clean(item) for item in decisions]
    channel = author_key(author)
    counts = {"accepted": 0, "rejected": 0}
    for original, kind, replacement in cleaned:
        key = word_key(original)
        opposite = "rejected" if kind == "accepted" else "accepted"
        session.execute(delete(Memory).where(
            Memory.author_key == channel, Memory.original_key == key, Memory.decision == opposite,
        ))
        replacement_key = word_key(replacement) if replacement else ""
        row = session.scalars(select(Memory).where(
            Memory.author_key == channel, Memory.original_key == key, Memory.decision == kind,
            Memory.replacement_key == replacement_key,
        )).first()
        if row is None:
            session.add(Memory(author_key=channel, original_key=key, original=original, replacement=replacement,
                               replacement_key=replacement_key, decision=kind, document_ids=[document_id], times=1))
        else:
            documents = list(row.document_ids or [])
            if document_id not in documents:
                documents.append(document_id)
            row.document_ids = documents[-MAX_DOCUMENT_IDS:]
            row.times = (row.times or 0) + 1
            row.replacement = replacement
        counts[kind] += 1
    session.flush()
    return counts


def forget(session, memory_id: int) -> bool:
    """Drop one remembered decision (flushes, the caller commits)."""
    row = session.get(Memory, memory_id)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True
