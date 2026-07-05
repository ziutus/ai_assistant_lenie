"""Unit tests for Etap 4 (books): chapter-scoped runs and lazy chunk loading.

Covers _slice_chapter + create_run(scope_chapter=N) in the analysis service and
the chunk_review_routes additions (GET /document/<id>/chapters, split_preview
scope_chapter, GET /analysis_run/<id>/chunks lite/section_id/offset/limit,
PATCH /topic_section/<id>). LLM calls and DB access are mocked.
"""

import datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

import library.chunk_llm_analysis as llm  # noqa: E402
import library.document_analysis_service as das  # noqa: E402
from library import chunk_review_routes as crr  # noqa: E402
from library.db.models import (  # noqa: E402
    DocumentAnalysisRun, DocumentChunk, DocumentTopicSection, WebDocument,
)
from library.document_analysis_service import DocumentAnalysisService, _slice_chapter  # noqa: E402


BOOK_TEXT = (
    "Strona tytułowa książki testowej. " + "w" * 80 + "\n\n"
    "# Rozdział 1: Geneza\n\n" + "Zdanie z rozdziału pierwszego. " * 10 + "\n\n"
    "# Rozdział 2: Rozwój\n\n" + "Zdanie z rozdziału drugiego. " * 10
)


class FakeBookDoc:
    id = 77
    title = "Testowa książka"
    text = None
    text_md = BOOK_TEXT
    text_raw = None


# ---------------------------------------------------------------------------
# _slice_chapter
# ---------------------------------------------------------------------------


class TestSliceChapter:
    def test_returns_chapter_text_and_title(self):
        text, title = _slice_chapter(BOOK_TEXT, 2)
        assert title == "Rozdział 1: Geneza"
        assert text.startswith("# Rozdział 1: Geneza")
        assert "rozdziału drugiego" not in text

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            _slice_chapter(BOOK_TEXT, 99)

    def test_no_chapters_raises(self):
        with pytest.raises(ValueError, match="no detectable chapters"):
            _slice_chapter("Tekst bez nagłówków.", 1)


# ---------------------------------------------------------------------------
# create_run(scope_chapter=N)
# ---------------------------------------------------------------------------


@pytest.fixture
def session():
    s = MagicMock()
    s.added = []
    s.add.side_effect = s.added.append
    return s


@pytest.fixture
def book_env(monkeypatch, session):
    monkeypatch.setattr(
        das.WebDocument, "get_by_id", staticmethod(lambda _s, _id: FakeBookDoc()),
    )
    analyzed: list[str] = []

    def fake_article(text, model, position=1, total=1):
        analyzed.append(text)
        return {
            "type": "TEMAT", "topic": f"temat {position}",
            "corrected_text": None, "summary": f"streszczenie {position}",
            "rewrite_ratio": None,
        }

    monkeypatch.setattr(llm, "analyze_article_chunk", fake_article)
    monkeypatch.setattr(das, "_merge_topics", lambda sections, model, mode="transcript": [])
    monkeypatch.setattr(
        das, "_synthesize", lambda sections, title, model, mode="transcript": "",
    )
    return analyzed


class TestScopeChapterRun:
    def test_scope_chapter_analyzes_only_that_chapter(self, session, book_env):
        service = DocumentAnalysisService(session)
        run = service.create_run(doc_id=77, model="m", mode="article", scope_chapter=3)

        assert run.scope == "Rozdział 2: Rozwój"
        joined = "\n".join(book_env)
        assert "rozdziału drugiego" in joined
        assert "rozdziału pierwszego" not in joined
        assert "Strona tytułowa" not in joined

    def test_no_scope_chapter_leaves_scope_null(self, session, book_env):
        service = DocumentAnalysisService(session)
        run = service.create_run(doc_id=77, model="m", mode="article")
        assert run.scope is None

    def test_scope_chapter_in_transcript_mode_raises(self, session, book_env):
        service = DocumentAnalysisService(session)
        with pytest.raises(ValueError, match="requires article mode"):
            service.create_run(doc_id=77, model="m", mode="transcript", scope_chapter=1)

    def test_scope_chapter_out_of_range_raises(self, session, book_env):
        service = DocumentAnalysisService(session)
        with pytest.raises(ValueError, match="out of range"):
            service.create_run(doc_id=77, model="m", mode="article", scope_chapter=42)


# ---------------------------------------------------------------------------
# Flask routes (mocked session)
# ---------------------------------------------------------------------------


def _make_chunk(**kw) -> DocumentChunk:
    defaults = dict(
        run_id=1, document_id=77, type="TEMAT", topic=None,
        original_text="treść " * 60, corrected_text=None, summary="s",
        seg_start=None, seg_end=None, rewrite_ratio=None, status="pending",
        split_at_seg=None, split_first_type=None, split_second_type=None,
        obsidian_note_paths=[],
    )
    defaults.update(kw)
    return DocumentChunk(**defaults)


@pytest.fixture
def run_with_sections():
    run = MagicMock(spec=DocumentAnalysisRun)
    run.id = 1
    run.document_id = 77
    run.model = "m"
    run.chunk_size = 5000
    run.mode = "article"
    run.status = "created"
    run.scope = None
    run.synthesis = None
    run.speakers = []
    run.created_at = datetime.datetime(2026, 7, 5, 12, 0)
    run.chunks = [
        _make_chunk(id=101, position=1, status="approved", obsidian_note_paths=["N.md"]),
        _make_chunk(id=102, position=2),
        _make_chunk(id=103, position=3, type="SZUM", status="approved"),
        _make_chunk(id=104, position=4, status="approved"),
        _make_chunk(id=105, position=5),
    ]
    s1 = MagicMock(spec=DocumentTopicSection)
    s1.id, s1.position, s1.type, s1.title, s1.summary = 11, 1, "TEMAT", "Sekcja A", None
    s1.chunk_positions = [1, 2]
    s2 = MagicMock(spec=DocumentTopicSection)
    s2.id, s2.position, s2.type, s2.title, s2.summary = 12, 2, "TEMAT", "Sekcja B", None
    s2.chunk_positions = [3, 4, 5]
    return run, [s1, s2]


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


@pytest.fixture
def client(monkeypatch, run_with_sections):
    run, sections = run_with_sections
    doc = FakeBookDoc()
    doc.original_id = ""
    doc.document_type = "text"

    fake_session = MagicMock()

    def fake_get(model, pk):
        if model is DocumentAnalysisRun:
            return run if pk == run.id else None
        if model is WebDocument:
            return doc
        if model is DocumentTopicSection:
            return next((s for s in sections if s.id == pk), None)
        return None

    fake_session.get.side_effect = fake_get
    # get_run_chunks issues two scalars() queries: topic sections, embedded chunk ids
    fake_session.scalars.side_effect = lambda *_a, **_kw: (
        _ScalarsResult(sections) if fake_session.scalars.call_count % 2 == 1
        else _ScalarsResult([101])
    )
    monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


class TestChaptersEndpoint:
    def test_returns_detected_chapters(self, client):
        resp = client.get("/document/77/chapters")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["source_field"] == "text_md"
        titles = [c["title"] for c in data["chapters"]]
        assert titles == ["(wstęp)", "Rozdział 1: Geneza", "Rozdział 2: Rozwój"]


class TestChapterContentEndpoint:
    def test_returns_chapter_text_with_nav(self, client):
        resp = client.get("/document/77/chapter/2")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["title"] == "Rozdział 1: Geneza"
        assert data["text"].startswith("# Rozdział 1: Geneza")
        assert data["chapter_total"] == 3
        assert data["prev"] == 1
        assert data["next"] == 3

    def test_first_and_last_chapter_nav_boundaries(self, client):
        first = client.get("/document/77/chapter/1").get_json()
        last = client.get("/document/77/chapter/3").get_json()

        assert first["prev"] is None and first["next"] == 2
        assert last["prev"] == 2 and last["next"] is None

    def test_out_of_range_rejected(self, client):
        resp = client.get("/document/77/chapter/42")
        assert resp.status_code == 400


class TestSplitPreviewScopeChapter:
    def test_preview_scoped_to_chapter(self, client):
        resp = client.get("/document/77/split_preview?mode=article&scope_chapter=2")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["scope_chapter"] == 2
        assert data["scope_title"] == "Rozdział 1: Geneza"
        assert data["text_length"] < len(BOOK_TEXT)

    def test_scope_chapter_transcript_mode_rejected(self, client):
        resp = client.get("/document/77/split_preview?mode=transcript&scope_chapter=1")
        assert resp.status_code == 400

    def test_scope_chapter_out_of_range_rejected(self, client):
        resp = client.get("/document/77/split_preview?mode=article&scope_chapter=42")
        assert resp.status_code == 400


class TestAnalyzeChunksScopeValidation:
    def test_scope_chapter_requires_article_mode(self, client):
        resp = client.post("/document/77/analyze_chunks",
                           json={"mode": "transcript", "scope_chapter": 2})
        assert resp.status_code == 400

    def test_scope_chapter_must_be_int(self, client):
        resp = client.post("/document/77/analyze_chunks",
                           json={"mode": "article", "scope_chapter": "abc"})
        assert resp.status_code == 400


class TestGetRunChunksLazy:
    def test_default_full_response_unchanged(self, client):
        data = client.get("/analysis_run/1/chunks").get_json()

        assert data["lite"] is False
        assert data["chunk_total"] == 5
        assert len(data["chunks"]) == 5
        assert data["chunks"][0]["original_text"] is not None
        assert data["chunks"][0]["text_preview"] is None

    def test_lite_strips_texts_and_adds_preview(self, client):
        data = client.get("/analysis_run/1/chunks?lite=1").get_json()

        for c in data["chunks"]:
            assert c["original_text"] is None
            assert c["corrected_text"] is None
            assert 0 < len(c["text_preview"]) <= crr.TEXT_PREVIEW_CHARS
            assert c["text_length"] > 0

    def test_section_filter(self, client):
        data = client.get("/analysis_run/1/chunks?section_id=12").get_json()

        assert data["chunk_total"] == 3
        assert [c["position"] for c in data["chunks"]] == [3, 4, 5]
        assert data["chunks"][0]["original_text"] is not None

    def test_unknown_section_404(self, client):
        resp = client.get("/analysis_run/1/chunks?section_id=999")
        assert resp.status_code == 404

    def test_offset_limit(self, client):
        data = client.get("/analysis_run/1/chunks?offset=1&limit=2").get_json()

        assert data["chunk_total"] == 5
        assert [c["position"] for c in data["chunks"]] == [2, 3]
        assert data["offset"] == 1

    def test_section_stats(self, client):
        data = client.get("/analysis_run/1/chunks?lite=1").get_json()
        s1, s2 = data["topic_sections"]

        # Sekcja A: chunks 1-2 (both TEMAT, one approved, one with a note)
        assert (s1["chunk_count"], s1["temat_count"], s1["approved_count"], s1["notes_count"]) \
            == (2, 2, 1, 1)
        # Sekcja B: chunks 3-5 (SZUM + 2 TEMAT, one TEMAT approved)
        assert (s2["chunk_count"], s2["temat_count"], s2["approved_count"], s2["notes_count"]) \
            == (3, 2, 1, 0)

    def test_embeddings_flag_survives_lite(self, client):
        data = client.get("/analysis_run/1/chunks?lite=1").get_json()
        by_pos = {c["position"]: c for c in data["chunks"]}
        assert by_pos[1]["has_embeddings"] is True
        assert by_pos[2]["has_embeddings"] is False


class TestPatchTopicSection:
    def test_updates_title(self, client, run_with_sections):
        _, sections = run_with_sections
        resp = client.patch("/topic_section/11", json={"title": "Nowy tytuł rozdziału"})
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["topic_section"]["title"] == "Nowy tytuł rozdziału"
        assert sections[0].title == "Nowy tytuł rozdziału"

    def test_empty_title_rejected(self, client):
        resp = client.patch("/topic_section/11", json={"title": "   "})
        assert resp.status_code == 400

    def test_unknown_section_404(self, client):
        resp = client.patch("/topic_section/999", json={"title": "x"})
        assert resp.status_code == 404
