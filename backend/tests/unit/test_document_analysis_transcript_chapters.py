"""Unit tests for chapter-aware chunk splitting of YouTube transcripts.

youtube_processing.py inserts each video chapter's title as a standalone
line at the start of its block (text_transcript.py:_append_with_chapters).
document_analysis_service._chapter_chunks_from_text() reuses those
boundaries instead of blindly cutting every chunk_size characters — see
document_analysis_service.py step 7 (transcript mode).

LLM calls and DB access are mocked — verifies splitting/routing only.
"""

from unittest.mock import MagicMock

import pytest

import library.chunk_llm_analysis as llm
import library.document_analysis_service as das
from library.db.models import DocumentChunk
from library.document_analysis_service import DocumentAnalysisService, _chapter_chunks_from_text


CHAPTER_TITLES = ["Wstęp", "USA bombardują Iran", "Trump na szczycie NATO"]

TRANSCRIPT_TEXT = (
    "Wstęp\n" + "Zdanie wstępu. " * 20 + "\n\n"
    "USA bombardują Iran\n" + "Zdanie o Iranie. " * 20 + "\n\n"
    "Trump na szczycie NATO\n" + "Zdanie o NATO. " * 20
)

CHAPTER_LIST_TEXT = "00:00 Wstęp\n00:42 USA bombardują Iran\n13:17 Trump na szczycie NATO"


class TestChapterChunksFromText:
    def test_splits_at_chapter_boundaries(self):
        chunks = _chapter_chunks_from_text(TRANSCRIPT_TEXT, CHAPTER_TITLES, chunk_size=5000)
        assert chunks is not None
        assert len(chunks) == 3
        assert chunks[0].startswith("Wstęp")
        assert chunks[1].startswith("USA bombardują Iran")
        assert chunks[2].startswith("Trump na szczycie NATO")

    def test_returns_none_when_titles_absent(self):
        chunks = _chapter_chunks_from_text("Zwykły tekst bez rozdziałów. " * 30, CHAPTER_TITLES, chunk_size=5000)
        assert chunks is None

    def test_returns_none_below_half_threshold(self):
        # Only 1 of 3 known titles actually present in the text
        text = "Wstęp\n" + "Treść. " * 20
        chunks = _chapter_chunks_from_text(text, CHAPTER_TITLES, chunk_size=5000)
        assert chunks is None

    def test_empty_chapter_titles_returns_none(self):
        assert _chapter_chunks_from_text(TRANSCRIPT_TEXT, [], chunk_size=5000) is None

    def test_oversized_chapter_gets_subsplit(self):
        long_text = (
            "Wstęp\n" + "Zdanie wstępu. " * 20 + "\n\n"
            "USA bombardują Iran\n" + "Zdanie o Iranie. " * 500 + "\n\n"
            "Trump na szczycie NATO\n" + "Zdanie o NATO. " * 20
        )
        chunks = _chapter_chunks_from_text(long_text, CHAPTER_TITLES, chunk_size=2000)
        assert chunks is not None
        assert len(chunks) > 3
        assert chunks[0].startswith("Wstęp")
        assert any(c.startswith("USA bombardują Iran") for c in chunks)
        assert chunks[-1].startswith("Trump na szczycie NATO")


class FakeYoutubeDoc:
    id = 9216
    title = "Testowy film z rozdziałami"
    text = TRANSCRIPT_TEXT
    text_md = None
    text_raw = None
    chapter_list = CHAPTER_LIST_TEXT
    tags = None


@pytest.fixture
def session():
    s = MagicMock()
    s.added = []
    s.add.side_effect = s.added.append
    return s


@pytest.fixture
def transcript_env(monkeypatch, session):
    monkeypatch.setattr(das.WebDocument, "get_by_id", staticmethod(lambda _s, _id: FakeYoutubeDoc()))

    def fake_transcript(text, model, position=1, total=1, speakers=None, prev_context="", next_context=""):
        return {
            "type": "TEMAT", "topic": f"temat {position}",
            "corrected_text": None, "summary": f"streszczenie {position}",
            "rewrite_ratio": None,
        }

    monkeypatch.setattr(llm, "analyze_chunk", fake_transcript)
    monkeypatch.setattr(das, "_merge_topics", lambda sections, model, mode="transcript": [])
    monkeypatch.setattr(das, "_synthesize", lambda sections, title, model, mode="transcript": "")
    monkeypatch.setattr("library.article_tagging.tag_article_with_llm", lambda text, title: [])
    monkeypatch.setattr("library.article_tagging.extract_countries_hybrid", lambda text, title: [])
    return session


class TestCreateRunUsesChapterSplit:
    def test_chunk_count_matches_video_chapters(self, transcript_env):
        service = DocumentAnalysisService(transcript_env)
        run = service.create_run(doc_id=9216, model="test-model", mode="transcript")

        assert run.mode == "transcript"
        chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
        assert len(chunks) == 3
        assert chunks[0].original_text.startswith("Wstęp")
        assert chunks[1].original_text.startswith("USA bombardują Iran")
        assert chunks[2].original_text.startswith("Trump na szczycie NATO")

    def test_falls_back_to_sentence_split_without_chapter_list(self, transcript_env, monkeypatch):
        doc = FakeYoutubeDoc()
        doc.chapter_list = None
        monkeypatch.setattr(das.WebDocument, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(transcript_env)
        service.create_run(doc_id=9216, model="test-model", mode="transcript", chunk_size=300)

        chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
        # Blind char-count split ignores chapter boundaries — more/uneven pieces
        assert len(chunks) > 3
