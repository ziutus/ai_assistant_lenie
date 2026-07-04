"""Unit tests for DocumentAnalysisService.create_run in article mode.

LLM calls and DB access are mocked — verifies pipeline routing only:
article mode must skip speaker/filler processing, use the markdown splitter,
call analyze_article_chunk and persist mode/status on the run.
"""

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
        das.WebDocument, "get_by_id", staticmethod(lambda _s, _id: FakeDoc()),
    )

    calls = {"article": 0, "transcript": 0, "speakers": 0, "fillers": 0}

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
    return calls


class TestSzumType:
    def test_parse_szum_header(self):
        from library.chunk_llm_analysis import parse_rewritten_chunk
        t, topic, rest = parse_rewritten_chunk("### SZUM: nawigacja portalu WP\n")
        assert t == "SZUM"
        assert topic == "nawigacja portalu WP"
        assert rest == ""

    def test_article_chunk_szum_has_no_summary(self, monkeypatch):
        monkeypatch.setattr(
            llm, "call_model",
            lambda prompt, model, max_tokens: ("### SZUM: menu i stopka strony\ncokolwiek", 10),
        )
        result = llm.analyze_article_chunk("Wróć na POLSKA ŚWIAT...", "m")
        assert result["type"] == "SZUM"
        assert result["topic"] == "menu i stopka strony"
        assert result["summary"] is None
        assert result["corrected_text"] is None

    def test_article_chunk_temat_strips_streszczenie_prefix(self, monkeypatch):
        monkeypatch.setattr(
            llm, "call_model",
            lambda prompt, model, max_tokens: ("### TEMAT: konflikt USA-Iran\nStreszczenie: Analiza sytuacji.", 10),
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
        session.commit.assert_called_once()

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
