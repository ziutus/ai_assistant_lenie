"""Unit tests for POST /chunk/<id>/remove_span and its interaction with
execute_split/merge_with_next.

remove_span cuts one exact substring out of a chunk's original_text (e.g. an
ad spliced mid-sentence into a transcript segment) without touching
seg_start/seg_end, so the video-chapter divider (see
test_document_analysis_transcript_chapters.py) survives. execute_split and
merge_with_next must not resurrect an already-removed span when they rebuild
text from raw transcript segments / concatenate texts. All DB access is
mocked (MagicMock session) — no PostgreSQL required.
"""
import json
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as crr  # noqa: E402
from library.db.models import Document, DocumentChunk  # noqa: E402


def _make_chunk(**kw) -> DocumentChunk:
    defaults = dict(
        id=1, run_id=1, document_id=77, position=1, type="TEMAT", topic=None,
        original_text="treść", corrected_text=None, summary="s",
        seg_start=None, seg_end=None, rewrite_ratio=None, status="pending",
        split_at_seg=None, split_first_type=None, split_second_type=None,
        obsidian_note_paths=[], removed_text_spans=[],
    )
    defaults.update(kw)
    return DocumentChunk(**defaults)


@pytest.fixture
def app():
    application = flask.Flask(__name__)
    application.register_blueprint(crr.bp)
    return application


class TestRemoveSpanEndpoint:
    def test_removes_exact_substring_and_records_it(self, monkeypatch, app):
        chunk = _make_chunk(
            original_text="Dzień dobry. WEJDŹ NA MBANK.PL i zacznij oszczędzać. Witam widzów.",
        )
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk if model is DocumentChunk and pk == chunk.id else None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post(
            "/chunk/1/remove_span", json={"text": "WEJDŹ NA MBANK.PL i zacznij oszczędzać. "},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["chunk"]["original_text"] == "Dzień dobry. Witam widzów."
        assert data["chunk"]["removed_text_spans"] == ["WEJDŹ NA MBANK.PL i zacznij oszczędzać."]
        assert data["chunk"]["status"] == "needs_reanalysis"
        fake_session.commit.assert_called_once()

    def test_matches_whitespace_tolerantly_against_hard_wrapped_text(self, monkeypatch, app):
        # original_text can be hard-wrapped mid-sentence (embedded \n) even
        # though a selection made in the live transcript view (SegmentsView,
        # single-space reconstruction from raw segments) is single-spaced —
        # this is the exact mismatch caught live on doc 8790's chunk #1.
        chunk = _make_chunk(
            original_text="Amerykanie by fabryki półprzewodników zostałyby zburzone,\nżeby nie wpadły w ręce.",
        )
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post(
            "/chunk/1/remove_span",
            json={"text": "Amerykanie by fabryki półprzewodników zostałyby zburzone, żeby nie wpadły"},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["chunk"]["original_text"] == "w ręce."
        assert data["chunk"]["removed_text_spans"] == [
            "Amerykanie by fabryki półprzewodników zostałyby zburzone, żeby nie wpadły",
        ]

    def test_rejects_a_cut_that_bisects_a_word(self, monkeypatch, app):
        # Caught live on doc 8790: an imprecise selection matched "ykanie by
        # ... nie wp" inside "Amerykanie by ... nie wpadły", splicing the
        # leftover "Amer" + "adły" into the garbled word "Ameradły".
        chunk = _make_chunk(original_text="to Amerykanie by fabryki nie wpadły w ręce.")
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post(
            "/chunk/1/remove_span", json={"text": "ykanie by fabryki nie wp"},
        )

        assert resp.status_code == 400
        assert chunk.original_text == "to Amerykanie by fabryki nie wpadły w ręce."
        fake_session.commit.assert_not_called()

    def test_allows_a_cut_ending_exactly_at_a_word_boundary(self, monkeypatch, app):
        chunk = _make_chunk(original_text="to Amerykanie by fabryki nie wpadły w ręce.")
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post(
            "/chunk/1/remove_span", json={"text": "Amerykanie by fabryki nie wpadły"},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["chunk"]["original_text"] == "to w ręce."

    def test_text_not_found_returns_400(self, monkeypatch, app):
        chunk = _make_chunk(original_text="Dzień dobry.")
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post("/chunk/1/remove_span", json={"text": "nie ma mnie tutaj"})

        assert resp.status_code == 400
        assert chunk.original_text == "Dzień dobry."
        fake_session.commit.assert_not_called()

    def test_blank_text_returns_400(self, monkeypatch, app):
        chunk = _make_chunk()
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post("/chunk/1/remove_span", json={"text": "   "})

        assert resp.status_code == 400

    def test_non_temat_chunk_keeps_its_status(self, monkeypatch, app):
        chunk = _make_chunk(type="SZUM", status="approved", original_text="reklama a potem tekst")
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post("/chunk/1/remove_span", json={"text": "reklama a potem "})
        data = resp.get_json()

        assert data["chunk"]["status"] == "approved"


class TestRemoveSpanSurvivesSplit:
    def test_split_does_not_resurrect_a_removed_span(self, monkeypatch, app):
        # Raw transcript: [ad-laced segment][real content segment]
        segments = [
            {"start": 0.0, "text": "Nie jutraj myślenia o emeryturze. Wejdź na mbank.pl. Dzień dobry."},
            {"start": 12.0, "text": "Zapraszam na program."},
        ]
        doc = MagicMock(spec=Document)
        doc.id = 77
        doc.text_raw = json.dumps(segments)

        chunk = _make_chunk(
            id=5, seg_start=0, seg_end=2,
            original_text="Dzień dobry. Zapraszam na program.",
            removed_text_spans=["Nie jutraj myślenia o emeryturze. Wejdź na mbank.pl. "],
        )
        fake_session = MagicMock()

        def fake_get(model, pk):
            if model is DocumentChunk:
                return chunk
            if model is Document:
                return doc
            return None

        fake_session.get.side_effect = fake_get
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
        monkeypatch.setattr(
            "library.cited_publications.refresh_document_cited_publications",
            lambda *a, **kw: None,
        )

        resp = app.test_client().post(
            "/chunk/5/execute_split",
            json={"split_at_seg": 1, "split_first_type": "TEMAT", "split_second_type": "TEMAT"},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert "mbank" not in data["chunk_a"]["original_text"].lower()
        assert data["chunk_a"]["original_text"] == "Dzień dobry."
        assert data["chunk_b"]["original_text"] == "Zapraszam na program."
        assert data["chunk_a"]["removed_text_spans"] == chunk.removed_text_spans
        assert data["chunk_b"]["removed_text_spans"] == chunk.removed_text_spans


class TestRemoveSpanSurvivesMerge:
    def test_merge_unions_removed_text_spans(self, monkeypatch, app):
        chunk = _make_chunk(id=10, position=1, removed_text_spans=["reklama A"])
        next_chunk = _make_chunk(
            id=11, position=2, original_text="dalszy tekst", removed_text_spans=["reklama B"],
        )
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk if pk == chunk.id else None
        fake_session.scalar.side_effect = lambda *_a, **_kw: next_chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
        monkeypatch.setattr(
            "library.cited_publications.refresh_document_cited_publications",
            lambda *a, **kw: None,
        )

        resp = app.test_client().post("/chunk/10/merge_with_next")
        data = resp.get_json()

        assert resp.status_code == 200
        assert sorted(data["chunk"]["removed_text_spans"]) == ["reklama A", "reklama B"]


class TestSplitAtText:
    """split_at_text: cut a chunk in two at a whitespace-tolerant text match,
    for a split point too fine-grained for split_at_seg/split_at_line —
    e.g. a multi-sentence transcript segment. Freezes both halves as plain
    text (seg_start/seg_end null), like split_at_line."""

    def test_splits_at_matched_text_and_freezes_seg_info(self, monkeypatch, app):
        chunk = _make_chunk(
            id=20, seg_start=0, seg_end=5,
            original_text="Reklama mBank tutaj.\nDzień dobry, zapraszam na program.",
        )
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk if model is DocumentChunk else None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
        monkeypatch.setattr(
            "library.cited_publications.refresh_document_cited_publications",
            lambda *a, **kw: None,
        )

        resp = app.test_client().post(
            "/chunk/20/execute_split",
            json={
                "split_at_text": "Dzień dobry, zapraszam na program.",
                "split_first_type": "REKLAMA", "split_second_type": "TEMAT",
            },
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["chunk_a"]["original_text"] == "Reklama mBank tutaj."
        assert data["chunk_a"]["type"] == "REKLAMA"
        assert data["chunk_a"]["seg_start"] is None
        assert data["chunk_a"]["seg_end"] is None
        assert data["chunk_b"]["original_text"] == "Dzień dobry, zapraszam na program."
        assert data["chunk_b"]["type"] == "TEMAT"
        assert data["chunk_b"]["status"] == "needs_reanalysis"
        assert data["chunk_b"]["seg_start"] is None

    def test_rejects_a_split_point_in_the_middle_of_a_word(self, monkeypatch, app):
        chunk = _make_chunk(id=20, original_text="to Amerykanie by fabryki nie wpadły w ręce.")
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post(
            "/chunk/20/execute_split",
            json={"split_at_text": "ykanie by fabryki", "split_first_type": "TEMAT", "split_second_type": "TEMAT"},
        )

        assert resp.status_code == 400
        assert chunk.original_text == "to Amerykanie by fabryki nie wpadły w ręce."

    def test_text_not_found_returns_400(self, monkeypatch, app):
        chunk = _make_chunk(id=20, original_text="Dzień dobry.")
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        resp = app.test_client().post(
            "/chunk/20/execute_split",
            json={"split_at_text": "nie ma mnie tutaj", "split_first_type": "TEMAT", "split_second_type": "TEMAT"},
        )

        assert resp.status_code == 400

    def test_carries_forward_removed_text_spans_to_both_halves(self, monkeypatch, app):
        chunk = _make_chunk(
            id=20, original_text="Dzień dobry. Zapraszam na program.",
            removed_text_spans=["Reklama wcześniej usunięta."],
        )
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: chunk
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
        monkeypatch.setattr(
            "library.cited_publications.refresh_document_cited_publications",
            lambda *a, **kw: None,
        )

        resp = app.test_client().post(
            "/chunk/20/execute_split",
            json={
                "split_at_text": "Zapraszam na program.",
                "split_first_type": "TEMAT", "split_second_type": "TEMAT",
            },
        )
        data = resp.get_json()

        assert data["chunk_a"]["removed_text_spans"] == ["Reklama wcześniej usunięta."]
        assert data["chunk_b"]["removed_text_spans"] == ["Reklama wcześniej usunięta."]
