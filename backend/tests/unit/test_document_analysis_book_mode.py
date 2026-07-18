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
from library.text_functions import detect_chapters  # noqa: E402


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
    tags = "geopolityka,kraj-polska,kraj-niemcy"
    document_type = "text"
    url = None
    quality = None
    date_from = None
    created_at = None


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
    monkeypatch.setattr("library.article_tagging.tag_article_with_llm", lambda text, title: [])
    monkeypatch.setattr("library.article_tagging.extract_countries_hybrid", lambda text, title: [])
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

    def test_reclean_applies_current_footer_rules_before_split(self, monkeypatch, session, book_env):
        class WpDoc(FakeBookDoc):
            text_md = None
            text = ("Treść właściwa artykułu i jego dłuższy akapit testowy. " * 4
                    + "\n\nWybrane dla Ciebie\n\nPolecany materiał")
            url = "https://tech.wp.pl/test"

        monkeypatch.setattr(
            das.WebDocument, "get_by_id", staticmethod(lambda _s, _id: WpDoc()),
        )
        monkeypatch.setattr("library.entity_service.refresh_document_entities", lambda *_a, **_kw: [])

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=77, model="m", mode="article", split_only=True, reclean=True)

        joined = "\n".join(
            item.original_text for item in session.added if isinstance(item, DocumentChunk)
        )
        assert "Treść właściwa" in joined
        assert "Wybrane dla Ciebie" not in joined
        assert "Polecany materiał" not in joined


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

    def first(self):
        return self._items[0] if self._items else None


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

    def route_scalars(stmt, *_a, **_kw):
        sql = str(stmt)
        if "document_analysis_runs" in sql:
            return _ScalarsResult([run])
        if "document_topic_sections" in sql:
            return _ScalarsResult(sections)
        return _ScalarsResult([101])  # websites_embeddings: embedded chunk ids

    fake_session.scalars.side_effect = route_scalars
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

    def test_reader_collapses_short_markdown_document(self, client):
        resp = client.get("/document/77/chapters?reader=1")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["reader_compact"] is True
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["title"] == "(całość)"
        assert data["chapters"][0]["length"] == data["text_length"]

    def test_returns_countries_from_kraj_tags(self, client):
        resp = client.get("/document/77/chapters")
        data = resp.get_json()

        assert data["countries"] == [
            {"slug": "polska", "name_pl": "Polska"},
            {"slug": "niemcy", "name_pl": "Niemcy"},
        ]

    def test_returns_thematic_tags_without_kraj_prefix(self, client):
        resp = client.get("/document/77/chapters")
        data = resp.get_json()

        assert data["thematic_tags"] == ["geopolityka"]

    def test_returns_synthesis_from_latest_run(self, client, run_with_sections):
        run, _ = run_with_sections
        run.synthesis = "Synteza całego dokumentu."

        resp = client.get("/document/77/chapters")
        data = resp.get_json()

        assert data["synthesis"] == "Synteza całego dokumentu."

    def test_countries_empty_when_no_tags(self, transcript_client):
        resp = transcript_client.get("/document/88/chapters")
        data = resp.get_json()

        assert data["countries"] == []
        assert data["thematic_tags"] == []
        assert data["synthesis"] is None


class TestCompactReaderChapters:
    def test_long_document_keeps_its_chapters(self):
        long_text = BOOK_TEXT + (" bardzo długi tekst" * 1_000)
        chapters = detect_chapters(long_text)

        result, compact = crr._compact_reader_chapters(long_text, chapters)

        assert compact is False
        assert result == chapters


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

    def test_short_document_is_returned_as_one_continuous_chapter(self, client):
        data = client.get("/document/77/chapter/1?reader=1").get_json()

        assert data["title"] == "(całość)"
        assert data["text"] == BOOK_TEXT.strip()
        assert data["chapter_total"] == 1
        assert data["prev"] is None
        assert data["next"] is None

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

    def test_reclean_requires_article_mode(self, client):
        resp = client.post("/document/77/analyze_chunks",
                           json={"mode": "transcript", "reclean": True})
        assert resp.status_code == 400


class TestGetRunChunksLazy:
    def test_default_full_response_unchanged(self, client):
        data = client.get("/analysis_run/1/chunks").get_json()

        assert data["lite"] is False
        assert data["chunk_total"] == 5
        assert len(data["chunks"]) == 5
        assert data["chunks"][0]["original_text"] is not None
        assert data["chunks"][0]["text_preview"] is None

    def test_document_includes_tags_and_countries(self, client):
        data = client.get("/analysis_run/1/chunks").get_json()

        assert data["document"]["thematic_tags"] == ["geopolityka"]
        assert data["document"]["countries"] == [
            {"slug": "polska", "name_pl": "Polska"},
            {"slug": "niemcy", "name_pl": "Niemcy"},
        ]

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


# ---------------------------------------------------------------------------
# Chapters fallback to TEMAT chunk topics (no markdown H1/H2 — e.g. YouTube
# transcripts, which are split into topic chunks instead of markdown text)
# ---------------------------------------------------------------------------


class FakeTranscriptDoc:
    id = 88
    title = "Testowy film YouTube"
    text = "Zwykła transkrypcja bez nagłówków markdown. " * 20
    text_md = None
    text_raw = None
    document_type = "youtube"
    tags = None
    url = None
    date_from = None
    created_at = None


@pytest.fixture
def transcript_run():
    run = MagicMock(spec=DocumentAnalysisRun)
    run.id = 5
    run.document_id = 88
    run.synthesis = None
    run.chunks = [
        _make_chunk(id=201, document_id=88, position=1, type="TEMAT", topic="Temat pierwszy",
                    corrected_text="Tekst poprawiony 1", original_text="Oryginał 1"),
        _make_chunk(id=202, document_id=88, position=2, type="REKLAMA", topic="Reklama"),
        _make_chunk(id=203, document_id=88, position=3, type="TEMAT", topic="Temat drugi",
                    corrected_text=None, original_text="Oryginał 2"),
    ]
    return run


@pytest.fixture
def transcript_client(monkeypatch, transcript_run):
    doc = FakeTranscriptDoc()
    fake_session = MagicMock()
    fake_session.get.side_effect = lambda model, pk: doc if model is WebDocument and pk == 88 else None
    # chapter-scoped synthesis lookup (GET /document/<id>/chapter/<pos>) — no
    # chapter-scoped run exists for this chunk-based-chapters document
    fake_session.scalars.side_effect = lambda *_a, **_kw: _ScalarsResult([])
    monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
    monkeypatch.setattr(crr, "_latest_run_for_document",
                        lambda _session, doc_id: transcript_run if doc_id == 88 else None)

    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


class TestChaptersFallbackToChunks:
    def test_chapters_list_uses_temat_chunk_topics(self, transcript_client):
        resp = transcript_client.get("/document/88/chapters")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["chapter_source"] == "chunks"
        titles = [c["title"] for c in data["chapters"]]
        assert titles == ["Temat pierwszy", "Temat drugi"]  # REKLAMA excluded

    def test_chapter_content_prefers_corrected_text(self, transcript_client):
        resp = transcript_client.get("/document/88/chapter/1")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["title"] == "Temat pierwszy"
        assert data["text"] == "Tekst poprawiony 1"
        assert data["chapter_total"] == 2
        assert data["prev"] is None
        assert data["next"] == 2

    def test_chapter_content_falls_back_to_original_text(self, transcript_client):
        resp = transcript_client.get("/document/88/chapter/2")
        data = resp.get_json()

        assert data["title"] == "Temat drugi"
        assert data["text"] == "Oryginał 2"
        assert data["prev"] == 1
        assert data["next"] is None

    def test_out_of_range_chunk_chapter_rejected(self, transcript_client):
        resp = transcript_client.get("/document/88/chapter/99")
        assert resp.status_code == 400

    def test_no_headers_and_no_run_returns_error(self, monkeypatch):
        doc = FakeTranscriptDoc()
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, pk: doc if model is WebDocument else None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
        monkeypatch.setattr(crr, "_latest_run_for_document", lambda _session, _doc_id: None)

        app = flask.Flask(__name__)
        app.register_blueprint(crr.bp)
        resp = app.test_client().get("/document/88/chapter/1")

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /analysis_run/<id>/extract_speakers
# ---------------------------------------------------------------------------


class TestExtractSpeakers:
    def _make_client(self, monkeypatch, run, chunks_for_query):
        fake_session = MagicMock()
        fake_session.get.side_effect = (
            lambda model, pk: run if model is DocumentAnalysisRun and pk == run.id else None
        )
        fake_session.scalars.return_value = _ScalarsResult(chunks_for_query)
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)

        app = flask.Flask(__name__)
        app.register_blueprint(crr.bp)
        return app.test_client()

    def test_default_uses_first_three_chunks_by_position(self, monkeypatch):
        run = MagicMock(spec=DocumentAnalysisRun)
        run.id, run.model, run.speakers = 10, "m", []
        chunks = [
            _make_chunk(id=1, position=1, original_text="Cześć, jestem Jan."),
            _make_chunk(id=2, position=2, original_text="A ja Anna."),
            _make_chunk(id=3, position=3, original_text="Zaczynajmy odcinek."),
        ]
        captured = {}
        monkeypatch.setattr(llm, "extract_speaker_info", lambda text, model: (
            captured.__setitem__("text", text) or [{"name": "Jan", "role": "prowadzący", "description": ""}]
        ))
        client = self._make_client(monkeypatch, run, chunks)

        resp = client.post(f"/analysis_run/{run.id}/extract_speakers")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["speakers"] == [{"name": "Jan", "role": "prowadzący", "description": ""}]
        assert run.speakers == data["speakers"]
        assert "Cześć, jestem Jan." in captured["text"]
        assert "Zaczynajmy odcinek." in captured["text"]

    def test_chunk_ids_uses_only_the_specified_chunk(self, monkeypatch):
        run = MagicMock(spec=DocumentAnalysisRun)
        run.id, run.model, run.speakers = 11, "m", []
        target = _make_chunk(id=42, position=5, original_text="Nazywam się Ola, jestem gościem.")
        captured = {}
        monkeypatch.setattr(llm, "extract_speaker_info", lambda text, model: (
            captured.__setitem__("text", text) or [{"name": "Ola", "role": "gość", "description": ""}]
        ))
        client = self._make_client(monkeypatch, run, [target])

        resp = client.post(f"/analysis_run/{run.id}/extract_speakers", json={"chunk_ids": [42]})
        data = resp.get_json()

        assert resp.status_code == 200
        assert captured["text"] == "Nazywam się Ola, jestem gościem."
        assert data["speakers"] == [{"name": "Ola", "role": "gość", "description": ""}]

    def test_chunk_ids_not_found_in_run_returns_400(self, monkeypatch):
        run = MagicMock(spec=DocumentAnalysisRun)
        run.id, run.model, run.speakers = 12, "m", []
        client = self._make_client(monkeypatch, run, [])  # query matched nothing

        resp = client.post(f"/analysis_run/{run.id}/extract_speakers", json={"chunk_ids": [999]})

        assert resp.status_code == 400

    def test_chunk_ids_wrong_type_returns_400(self, monkeypatch):
        run = MagicMock(spec=DocumentAnalysisRun)
        run.id, run.model, run.speakers = 13, "m", []
        client = self._make_client(monkeypatch, run, [])

        resp = client.post(f"/analysis_run/{run.id}/extract_speakers", json={"chunk_ids": "not-a-list"})

        assert resp.status_code == 400

    def test_run_not_found_returns_404(self, monkeypatch):
        fake_session = MagicMock()
        fake_session.get.return_value = None
        monkeypatch.setattr(crr, "get_scoped_session", lambda: fake_session)
        app = flask.Flask(__name__)
        app.register_blueprint(crr.bp)

        resp = app.test_client().post("/analysis_run/999/extract_speakers")

        assert resp.status_code == 404
