"""How often a radar entry's name shows up in the feed items - a cheap popularity signal.

A SQL regex join of every radar name against every feed item took ~95 s on the NAS, so
the feed texts are tokenised once into a sorted vocabulary (word -> feed positions) kept
in process for ``CACHE_TTL_SECONDS``. A name is looked up by its longest word as a prefix
(a Polish case ending adds at most ``MAX_SUFFIX_LENGTH`` letters), and only those few
candidates are verified with the same whole-word pattern ``tool_relations_service`` uses.
"""

import bisect
import re
import threading
import time

from sqlalchemy import select

from library.db.models import FeedItem
from library.tool_relations_service import name_pattern

CACHE_TTL_SECONDS = 600
MAX_SUFFIX_LENGTH = 3
SAMPLES_PER_NAME = 5
_WORD = re.compile(r"\w+")

_lock = threading.Lock()
_cache: dict = {"built_at": 0.0, "texts": [], "vocabulary": [], "positions": {}, "results": {}}


def _build_index(session) -> dict:
    rows = session.execute(select(FeedItem.id, FeedItem.title, FeedItem.summary, FeedItem.url)).all()
    texts, positions = [], {}
    for position, (item_id, title, summary, url) in enumerate(rows):
        text = f"{title or ''} {summary or ''}"
        texts.append({"id": item_id, "title": title, "url": url, "text": text})
        for word in set(_WORD.findall(text.lower())):
            positions.setdefault(word, []).append(position)
    return {"built_at": time.monotonic(), "texts": texts, "vocabulary": sorted(positions), "positions": positions, "results": {}}


def _index(session) -> dict:
    with _lock:
        if time.monotonic() - _cache["built_at"] > CACHE_TTL_SECONDS or not _cache["texts"]:
            _cache.update(_build_index(session))
        return _cache


def _candidates(snapshot: dict, word: str) -> set[int]:
    vocabulary, found = snapshot["vocabulary"], set()
    index = bisect.bisect_left(vocabulary, word)
    while index < len(vocabulary) and vocabulary[index].startswith(word):
        if len(vocabulary[index]) <= len(word) + MAX_SUFFIX_LENGTH:
            found.update(snapshot["positions"][vocabulary[index]])
        index += 1
    return found


def mentions_for(session, names: dict[int, str]) -> dict[int, dict]:
    """``{radar id: {"count": n, "samples": [{"id", "title", "url"}]}}`` for the names that occur at least once."""
    snapshot = _index(session)
    by_name: dict[str, dict | None] = snapshot["results"]  # per-name results live as long as the index
    result: dict[int, dict] = {}
    for entry_id, name in names.items():
        if name not in by_name:
            pattern = name_pattern(name)
            words = _WORD.findall(name.lower())
            hits = []
            if pattern is not None and words:
                positions = sorted(_candidates(snapshot, max(words, key=len)))
                hits = [snapshot["texts"][p] for p in positions if pattern.search(snapshot["texts"][p]["text"])]
            by_name[name] = {
                "count": len(hits),
                "samples": [{"id": h["id"], "title": h["title"], "url": h["url"]} for h in hits[:SAMPLES_PER_NAME]],
            } if hits else None
        if by_name[name] is not None:
            result[entry_id] = by_name[name]
    return result


def reset_cache() -> None:
    with _lock:
        _cache.update({"built_at": 0.0, "texts": [], "vocabulary": [], "positions": {}, "results": {}})
