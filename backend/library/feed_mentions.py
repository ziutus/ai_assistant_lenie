"""How often a radar entry's name shows up in the feed items - a cheap popularity signal.

A SQL regex join of every radar name against every feed item took ~95 s on the NAS, so
the feed texts are tokenised once into a prefix index (first three letters of every
word) kept in process for ``CACHE_TTL_SECONDS``. A name only has to be verified against
the feed items that contain a word with the same prefix; the verification uses the same
whole-word, Polish-inflection-tolerant pattern as ``tool_relations_service``.
"""

import re
import threading
import time

from sqlalchemy import select

from library.db.models import FeedItem
from library.tool_relations_service import name_pattern

CACHE_TTL_SECONDS = 600
PREFIX_LENGTH = 3
SAMPLES_PER_NAME = 5
_WORD = re.compile(r"\w+")

_lock = threading.Lock()
_cache: dict = {"built_at": 0.0, "texts": [], "index": {}}


def _build_index(session) -> dict:
    rows = session.execute(select(FeedItem.id, FeedItem.title, FeedItem.summary, FeedItem.url)).all()
    texts, index = [], {}
    for position, (item_id, title, summary, url) in enumerate(rows):
        text = f"{title or ''} {summary or ''}"
        texts.append({"id": item_id, "title": title, "url": url, "text": text})
        for word in {w[:PREFIX_LENGTH] for w in _WORD.findall(text.lower())}:
            index.setdefault(word, []).append(position)
    return {"built_at": time.monotonic(), "texts": texts, "index": index}


def _index(session) -> dict:
    with _lock:
        if time.monotonic() - _cache["built_at"] > CACHE_TTL_SECONDS or not _cache["texts"]:
            _cache.update(_build_index(session))
        return _cache


def mentions_for(session, names: dict[int, str]) -> dict[int, dict]:
    """``{radar id: {"count": n, "samples": [{"id", "title", "url"}]}}`` for the names that occur at least once."""
    snapshot = _index(session)
    result: dict[int, dict] = {}
    for entry_id, name in names.items():
        pattern = name_pattern(name)
        words = _WORD.findall(name.lower())
        if pattern is None or not words:
            continue
        key = max(words, key=len)[:PREFIX_LENGTH]
        hits = [snapshot["texts"][p] for p in snapshot["index"].get(key, ()) if pattern.search(snapshot["texts"][p]["text"])]
        if hits:
            result[entry_id] = {
                "count": len(hits),
                "samples": [{"id": h["id"], "title": h["title"], "url": h["url"]} for h in hits[:SAMPLES_PER_NAME]],
            }
    return result


def reset_cache() -> None:
    with _lock:
        _cache.update({"built_at": 0.0, "texts": [], "index": {}})
