"""Unit tests for DocumentAnalysisService.create_run in article mode.

LLM calls and DB access are mocked — verifies pipeline routing only:
article mode must skip speaker/filler processing, use the markdown splitter,
call analyze_article_chunk and persist mode/status on the run.
"""

import datetime
from unittest.mock import MagicMock

import pytest

import library.chunk_llm_analysis as llm
import library.document_analysis_service as das
from library.db.models import DocumentChunk
from library.document_analysis_service import ANALYSIS_MODES, DocumentAnalysisService


ARTICLE_TEXT = (
    "# Rozdział pierwszy\n\n" + "Zdanie merytoryczne. " * 20
    + "\n\n# Rozdział drugi\n\n" + "Kolejne zdanie. " * 20
)


class FakeDoc:
    id = 42
    title = "Testowy artykuł"
    text = ARTICLE_TEXT
    text_md = None
    text_raw = None
    tags = None


@pytest.fixture
def session():
    s = MagicMock()
    s.added = []
    s.add.side_effect = s.added.append
    return s


@pytest.fixture
def article_env(monkeypatch, session):
    """Patch document lookup, LLM primitives and topic grouping/synthesis."""
    monkeypatch.setattr(
        das.Document, "get_by_id", staticmethod(lambda _s, _id: FakeDoc()),
    )

    calls = {"article": 0, "transcript": 0, "speakers": 0, "fillers": 0, "tagging": 0}

    def fake_article(text, model, position=1, total=1):
        calls["article"] += 1
        return {
            "type": "TEMAT",
            "topic": f"temat {position}",
            "corrected_text": None,
            "summary": f"streszczenie {position}",
            "rewrite_ratio": None,
        }

    def fail_transcript(*_a, **_kw):
        calls["transcript"] += 1
        raise AssertionError("transcript-mode LLM primitive called in article mode")

    def fail_speakers(*_a, **_kw):
        calls["speakers"] += 1
        raise AssertionError("speaker extraction called in article mode")

    def fail_fillers(text):
        calls["fillers"] += 1
        raise AssertionError("remove_speech_fillers called in article mode")

    monkeypatch.setattr(llm, "analyze_article_chunk", fake_article)
    monkeypatch.setattr(llm, "analyze_chunk", fail_transcript)
    monkeypatch.setattr(llm, "extract_speaker_info", fail_speakers)
    monkeypatch.setattr(llm, "remove_speech_fillers", fail_fillers)
    monkeypatch.setattr(das, "_merge_topics", lambda sections, model, mode="transcript": [])
    monkeypatch.setattr(
        das, "_synthesize", lambda sections, title, model, mode="transcript": "synteza",
    )

    def fake_tag_article(text, title):
        calls["tagging"] += 1
        return []

    monkeypatch.setattr("library.article_tagging.tag_article_with_llm", fake_tag_article)
    monkeypatch.setattr("library.article_tagging.extract_countries_hybrid", lambda text, title: [])
    return calls


class TestSzumType:
    def test_parse_zrodla_header(self):
        from library.chunk_llm_analysis import parse_rewritten_chunk
        chunk_type, topic, rest = parse_rewritten_chunk("### ZRODLA: publikacje naukowe\n")
        assert chunk_type == "ZRODLA"
        assert topic == "publikacje naukowe"
        assert rest == ""

    def test_parse_szum_header(self):
        from library.chunk_llm_analysis import parse_rewritten_chunk
        t, topic, rest = parse_rewritten_chunk("### SZUM: nawigacja portalu WP\n")
        assert t == "SZUM"
        assert topic == "nawigacja portalu WP"
        assert rest == ""

    def test_article_chunk_szum_has_no_summary(self, monkeypatch):
        monkeypatch.setattr(
            llm, "call_model",
            lambda prompt, model, max_tokens, **kwargs: ("### SZUM: menu i stopka strony\ncokolwiek", 10),
        )
        result = llm.analyze_article_chunk("Wróć na POLSKA ŚWIAT...", "m")
        assert result["type"] == "SZUM"
        assert result["topic"] == "menu i stopka strony"
        assert result["summary"] is None
        assert result["corrected_text"] is None

    def test_article_chunk_temat_strips_streszczenie_prefix(self, monkeypatch):
        monkeypatch.setattr(
            llm, "call_model",
            lambda prompt, model, max_tokens, **kwargs: ("### TEMAT: konflikt USA-Iran\nStreszczenie: Analiza sytuacji.", 10),
        )
        result = llm.analyze_article_chunk("Treść merytoryczna.", "m")
        assert result["type"] == "TEMAT"
        assert result["summary"] == "Analiza sytuacji."


class TestArticleMode:
    def test_invalid_mode_raises(self, session):
        service = DocumentAnalysisService(session)
        with pytest.raises(ValueError, match="Invalid mode"):
            service.create_run(doc_id=42, model="m", mode="ksiazka")

    def test_modes_constant(self):
        assert ANALYSIS_MODES == ("transcript", "article")

    def test_article_run_persists_mode_and_status(self, session, article_env):
        service = DocumentAnalysisService(session)
        run = service.create_run(doc_id=42, model="test-model", mode="article")

        assert run.mode == "article"
        assert run.status == "created"
        assert run.speakers == []
        # 2 commits: entity_service's own isolated commit of ner_unavailable_at
        # (NER unreachable in this test env — no real ner_service) + the run persist.
        assert session.commit.call_count == 2

    def test_article_chunks_have_no_corrected_text(self, session, article_env):
        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        chunks = [o for o in session.added if isinstance(o, DocumentChunk)]
        assert len(chunks) >= 2
        assert all(c.corrected_text is None for c in chunks)
        assert all(c.rewrite_ratio is None for c in chunks)
        assert all(c.seg_start is None and c.seg_end is None for c in chunks)
        assert [c.position for c in chunks] == list(range(1, len(chunks) + 1))

    def test_article_mode_skips_transcript_pipeline(self, session, article_env):
        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        assert article_env["article"] >= 2
        assert article_env["transcript"] == 0
        assert article_env["speakers"] == 0
        assert article_env["fillers"] == 0

    def test_split_only_makes_no_llm_calls(self, session, article_env):
        service = DocumentAnalysisService(session)
        run = service.create_run(
            doc_id=42, model="test-model", mode="article", chunk_size=300, split_only=True,
        )

        assert article_env["article"] == 0
        assert article_env["transcript"] == 0
        assert run.synthesis is None
        chunks = [o for o in session.added if isinstance(o, DocumentChunk)]
        assert len(chunks) >= 2
        assert all(c.type == "TEMAT" and c.status == "pending" for c in chunks)
        assert all(c.topic is None and c.summary is None and c.corrected_text is None for c in chunks)
        from library.db.models import DocumentTopicSection
        sections = [o for o in session.added if isinstance(o, DocumentTopicSection)]
        assert sections == []

    def test_tags_document_using_synthesis_text(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
        captured = {}

        def fake_tag_article(text, title):
            captured["text"] = text
            return ["geopolityka"]

        monkeypatch.setattr("library.article_tagging.tag_article_with_llm", fake_tag_article)
        monkeypatch.setattr(
            "library.article_tagging.extract_countries_hybrid", lambda text, title: ["kraj-polska"],
        )

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        assert captured["text"] == "synteza"
        assert doc.tags == "geopolityka,kraj-polska"

    def test_tagging_skipped_for_split_only(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300, split_only=True)

        assert article_env["tagging"] == 0
        assert doc.tags is None

    def test_tagging_merges_with_existing_tags(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        doc.tags = "kraj-niemcy"
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
        monkeypatch.setattr("library.article_tagging.tag_article_with_llm", lambda text, title: ["wojsko"])
        monkeypatch.setattr(
            "library.article_tagging.extract_countries_hybrid", lambda text, title: ["kraj-niemcy", "kraj-polska"],
        )

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        assert doc.tags == "kraj-niemcy,wojsko,kraj-polska"

    def test_single_chunk_run_skips_merge_topics_and_still_tags(self, session, monkeypatch):
        """Regression: a single-chunk run used to end up with empty topic_sections
        AND empty synthesis, starving 11b's tagging_text and silently leaving
        doc.tags unset (found via a live /obsidian-note run on a real one-topic
        article — 42 documents affected on the NAS DB at time of fix)."""
        doc = FakeDoc()
        doc.text = "Krótki akapit merytoryczny o jednym temacie. " * 5
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        def fake_article(text, model, position=1, total=1):
            return {
                "type": "TEMAT", "topic": "jedyny temat",
                "corrected_text": None, "summary": "streszczenie jedynego chunka",
                "rewrite_ratio": None,
            }

        def fail_merge_topics(*_a, **_kw):
            raise AssertionError("_merge_topics should be skipped for a single-chunk run")

        monkeypatch.setattr(llm, "analyze_article_chunk", fake_article)
        monkeypatch.setattr(das, "_merge_topics", fail_merge_topics)
        monkeypatch.setattr(das, "_synthesize", lambda sections, title, model, mode="transcript": "")

        captured = {}

        def fake_tag_article(text, title):
            captured["text"] = text
            return ["geopolityka"]

        monkeypatch.setattr("library.article_tagging.tag_article_with_llm", fake_tag_article)
        monkeypatch.setattr("library.article_tagging.extract_countries_hybrid", lambda text, title: [])

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=5000)

        chunks = [o for o in session.added if isinstance(o, DocumentChunk)]
        assert len(chunks) == 1
        assert captured["text"] == "streszczenie jedynego chunka"
        assert doc.tags == "geopolityka"

    def test_default_mode_is_transcript(self, session, article_env, monkeypatch):
        """Without mode argument the transcript pipeline runs (fillers get called)."""
        # Un-fail the transcript primitives — record calls instead
        monkeypatch.setattr(llm, "remove_speech_fillers", lambda t: t)
        monkeypatch.setattr(
            llm, "analyze_chunk",
            lambda *a, **kw: {
                "type": "TEMAT", "topic": "t", "corrected_text": "x",
                "summary": "s", "rewrite_ratio": 100,
            },
        )
        service = DocumentAnalysisService(session)
        run = service.create_run(doc_id=42, model="test-model")

        assert run.mode == "transcript"
        assert article_env["article"] == 0


class TestPublishedOnBackfill:
    """create_run() step 2b: backfill published_on from a relative-date
    artifact (e.g. interia.pl's "Wczoraj, HH:MM") resolved against
    ingested_at — dok. 8865, zob. resolve_relative_publication_date."""

    INGESTED_AT = datetime.datetime(2026, 4, 13, 7, 10, 45)

    def test_backfills_from_relative_date_artifact(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        doc.text_md = "Wczoraj, 12:58\n\n" + ARTICLE_TEXT
        doc.ingested_at = self.INGESTED_AT
        doc.published_on = None
        doc.published_on_method = None
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        assert doc.published_on == datetime.date(2026, 4, 12)
        assert doc.published_on_method == "relative"

    def test_does_not_overwrite_existing_published_on(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        doc.text_md = "Wczoraj, 12:58\n\n" + ARTICLE_TEXT
        doc.ingested_at = self.INGESTED_AT
        doc.published_on = datetime.date(2026, 1, 1)
        doc.published_on_method = "manual"
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        assert doc.published_on == datetime.date(2026, 1, 1)
        assert doc.published_on_method == "manual"

    def test_no_artifact_leaves_published_on_none(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        doc.ingested_at = self.INGESTED_AT
        doc.published_on = None
        doc.published_on_method = None
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(session)
        service.create_run(doc_id=42, model="test-model", mode="article", chunk_size=300)

        assert doc.published_on is None
        assert doc.published_on_method is None


class TestAuthorBiographyIsolationOnLateDetection:
    """create_run() step 11b2: when the byline is only discovered by the LLM
    fallback (i.e. AFTER this run's text was already split — see the
    article-mode branch earlier in create_run(), which only isolates the
    trailing "o autorze" widget when the byline is known ahead of time),
    extract_trailing_author_biography() gets a second chance to strip it
    from doc.text_md so the NEXT run/reclean doesn't re-surface it as its
    own chunk. See [[project_article_author_detection]]/doc 9270 (money.pl/
    o2.pl bio widget)."""

    BIO_TEXT = (
        "Jan Kowalski Dziennikarz o2.pl\n\n"
        "Zajmował się dziennikarstwem od 2010 roku, pracował w kilku redakcjach lokalnych."
    )

    def test_bio_isolated_and_persisted_when_author_discovered_late(
        self, session, article_env, monkeypatch,
    ):
        doc = FakeDoc()
        doc.byline = None
        doc.text_md = ARTICLE_TEXT.rstrip() + "\n\n" + self.BIO_TEXT
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
        monkeypatch.setattr(llm, "extract_author_info", lambda text, model: ["Jan Kowalski"])

        def fake_set_authors(_session, doc, names, method):
            doc.byline = ", ".join(names)
            return {"linked": [], "skipped": []}

        monkeypatch.setattr("library.author_service.set_document_authors", fake_set_authors)

        bio_calls = []
        monkeypatch.setattr(
            "library.author_biography.process_author_biography",
            lambda _session, _doc, bio, _model: bio_calls.append(bio) or {
                "person_id": 1, "status": "auto_applied",
            },
        )

        DocumentAnalysisService(session).create_run(
            doc_id=42, model="test-model", mode="article", chunk_size=300,
        )

        assert doc.byline == "Jan Kowalski"
        assert bio_calls == [self.BIO_TEXT]
        assert "Zajmował się dziennikarstwem" not in doc.text_md

    def test_no_bio_found_leaves_text_md_untouched(self, session, article_env, monkeypatch):
        doc = FakeDoc()
        doc.byline = None
        doc.text_md = ARTICLE_TEXT
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
        monkeypatch.setattr(llm, "extract_author_info", lambda text, model: ["Jan Kowalski"])

        monkeypatch.setattr(
            "library.author_service.set_document_authors",
            lambda _session, doc, names, method: setattr(doc, "byline", ", ".join(names))
            or {"linked": [], "skipped": []},
        )
        bio_calls = []
        monkeypatch.setattr(
            "library.author_biography.process_author_biography",
            lambda *a, **kw: bio_calls.append(a) or {"person_id": 1, "status": "auto_applied"},
        )

        DocumentAnalysisService(session).create_run(
            doc_id=42, model="test-model", mode="article", chunk_size=300,
        )

        assert doc.byline == "Jan Kowalski"
        assert bio_calls == []
        assert doc.text_md == ARTICLE_TEXT
