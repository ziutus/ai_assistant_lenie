"""Shared helpers for per-chapter LLM analyses that must read a WHOLE chapter (tone, historical period).

A chapter longer than one model call used to be cut to its first ``MAX_FRAGMENT_CHARS`` characters, so the tone or
period of a long chapter described only its opening. These helpers split a chapter at paragraph boundaries (the
splitter of the event timeline), and merge the per-fragment reports; the analysis modules merge their own results.
"""

from __future__ import annotations

from collections.abc import Iterable

from library.llm_usage.report import combine_usage_reports

# Cost cap per chapter: 12 fragments of 8 000 characters is ~96 000 characters, longer than almost any chapter.
# What is beyond the cap is reported (``fragments_skipped``) instead of being dropped silently.
MAX_FRAGMENTS_PER_CHAPTER = 12


def resolve_chapter_scope(doc, position: int | None) -> int | None:
    """The chapter position to store results under: ``position`` for a document with ``##`` chapters, else ``None``.

    An article without H1/H2 headings has no chapters; its tone, periods and passages are stored as one
    whole-document row (``chapter_position`` NULL), and the reader still numbers it as chapter 1. A call that names a
    chapter of such a document therefore means the whole document.
    """
    from library.text_functions import detect_chapters

    return position if detect_chapters((doc.text_md or doc.text or "")) else None


def chapter_fragments(
    text: str | None, max_chars: int, max_fragments: int = MAX_FRAGMENTS_PER_CHAPTER,
) -> tuple[list[str], int]:
    """Split ``text`` at paragraph boundaries into fragments of at most ``max_chars`` characters.

    Returns the fragments to analyse (at most ``max_fragments``) and how many were left out because of the cap.
    Empty text gives no fragments, so no model call is made for it.
    """
    from library.timeline_events import split_timeline_fragments

    fragments = split_timeline_fragments(text or "", max_chars)
    return fragments[:max_fragments], max(0, len(fragments) - max_fragments)


def merge_fragment_reports(
    reports: Iterable[dict], *, counters: tuple[str, ...], fragments: int, skipped: int,
) -> dict:
    """One report for a chapter from the reports of its fragments.

    ``counters`` are summed. Usage (calls, tokens, cost) is combined only from reports that carry it, so a report
    built without a usage record (a stubbed model call) does not break the total.
    """
    reports = list(reports)
    merged: dict = {name: sum(int(report.get(name) or 0) for report in reports) for name in counters}
    usage = [report for report in reports if "llm_calls" in report]
    if usage:
        merged.update(combine_usage_reports(usage))
    merged["fragments"] = fragments
    merged["fragments_skipped"] = skipped
    return merged
