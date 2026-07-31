"""Unit tests for document_analysis_service._map_chunks_to_segments().

chunk_texts is split (at sentence boundaries) from transcript text that has
already had speech fillers stripped and, for multi-speaker transcripts,
speaker labels inserted — it has diverged character-for-character from the
untouched raw `segments`. The old implementation guessed each chunk's
seg_start/seg_end purely by character-count proportion, which drifts badly
when segments have uneven lengths (a single unusually long/short segment
skews the whole downstream proportion) and can land a chunk boundary
mid-sentence in the raw-segment view (chunk_review_routes.py's SegmentsView
renders directly from segments[seg_start:seg_end]).

The current implementation anchors each boundary to the chunk's own trailing
words, searched for in the raw segment word stream near the proportional
estimate, falling back to the estimate only when no match is found nearby.
"""
import pytest

pytest.importorskip("sqlalchemy")

from library.document_analysis_service import _map_chunks_to_segments  # noqa: E402


class TestMapChunksToSegments:
    def test_empty_inputs_return_none_pairs(self):
        assert _map_chunks_to_segments([], []) == []
        assert _map_chunks_to_segments(["a"], []) == [(None, None)]
        assert _map_chunks_to_segments([], [{"text": "a"}]) == []

    def test_single_chunk_spans_all_segments(self):
        segments = [{"text": "Ala"}, {"text": "ma"}, {"text": "kota"}]
        assert _map_chunks_to_segments(["Ala ma kota"], segments) == [(0, 3)]

    def test_anchors_boundary_past_a_disproportionately_long_segment(self):
        # seg1 dominates the character count (character-proportion would
        # guess the boundary lands inside or after seg1's own segment index,
        # short-changing chunk 1 of content that's genuinely still part of
        # it) — the real sentence boundary is between seg1 and seg2.
        segments = [
            {"text": "Krotko."},
            {"text": "To jest bardzo dlugi segment z wieloma slowami "
                     "wypelniajacymi przestrzen tekstowa bez konca prawie."},
            {"text": "Nowe zdanie zaczyna sie tutaj."},
            {"text": "I konczy sie ono w tym miejscu."},
        ]
        chunk_texts = [
            "Krotko. To jest bardzo dlugi segment z wieloma slowami "
            "wypelniajacymi przestrzen tekstowa bez konca prawie.",
            "Nowe zdanie zaczyna sie tutaj. I konczy sie ono w tym miejscu.",
        ]

        result = _map_chunks_to_segments(chunk_texts, segments)

        assert result == [(0, 2), (2, 4)]

    def test_tolerates_a_filler_word_stripped_from_chunk_text(self):
        # "yyy" is a filler present in the raw segment but already removed
        # from chunk_texts by remove_speech_fillers() before splitting.
        segments = [
            {"text": "Pierwsze zdanie tutaj jest."},
            {"text": "Drugie yyy zdanie konczy fragment."},
            {"text": "Trzecie zdanie zaczyna kolejny fragment."},
        ]
        chunk_texts = [
            "Pierwsze zdanie tutaj jest. Drugie zdanie konczy fragment.",
            "Trzecie zdanie zaczyna kolejny fragment.",
        ]

        result = _map_chunks_to_segments(chunk_texts, segments)

        assert result == [(0, 2), (2, 3)]

    def test_falls_back_to_proportion_when_no_match_found(self):
        # chunk_texts wording bears no relation to segments (degenerate
        # input) — must still return a usable range instead of raising.
        segments = [{"text": "foo bar"}, {"text": "baz qux"}]
        chunk_texts = ["completely unrelated text here", "more unrelated text"]

        result = _map_chunks_to_segments(chunk_texts, segments)

        assert len(result) == 2
        assert result[0][0] == 0
        assert result[-1][1] == 2
        assert result[0][1] <= result[1][1]
