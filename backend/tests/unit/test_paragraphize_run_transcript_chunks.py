"""Unit tests for document_analysis_service.paragraphize_run_transcript_chunks.

DB session and the LLM boundary-picker are mocked — verifies the scope gate
(YouTube + transcript mode + no source chapters), the idempotency skip (a
chunk whose corrected_text already has a blank line), and that a changed
chunk's corrected_text is persisted via commit.
"""

from unittest.mock import MagicMock

import pytest

from library.db.models import Document, DocumentAnalysisRun, DocumentChunk
from library.document_analysis_service import paragraphize_run_transcript_chunks
from library.transcript_paragraphs import ParagraphizeResult


def _chunk(id_, type_="TEMAT", corrected_text="tekst bez akapitów"):
    c = MagicMock(spec=DocumentChunk)
    c.id = id_
    c.type = type_
    c.corrected_text = corrected_text
    c.position = id_
    return c


def _run(mode="transcript", model="Bielik-11B-v3.0-Instruct"):
    run = MagicMock(spec=DocumentAnalysisRun)
    run.id = 163
    run.document_id = 9353
    run.mode = mode
    run.model = model
    return run


def _doc(document_type="youtube", text=None, text_md=None):
    doc = MagicMock(spec=Document)
    doc.id = 9353
    doc.document_type = document_type
    doc.text = text
    doc.text_md = text_md
    doc.text_raw = None
    return doc


def _session(run, doc, chunks):
    s = MagicMock()

    def _get(model, id_):
        if model is DocumentAnalysisRun:
            return run
        if model is Document:
            return doc
        return None

    s.get.side_effect = _get
    s.scalars.return_value.all.return_value = chunks
    return s


class TestParagraphizeRunTranscriptChunks:
    def test_run_not_found_raises(self):
        s = MagicMock()
        s.get.side_effect = lambda model, id_: None
        with pytest.raises(ValueError, match="Run 163 not found"):
            paragraphize_run_transcript_chunks(s, 163)

    def test_skips_article_mode_runs(self):
        run = _run(mode="article")
        doc = _doc()
        session = _session(run, doc, [_chunk(1)])

        result = paragraphize_run_transcript_chunks(session, 163)

        assert result == {
            "run_id": 163, "document_id": 9353,
            "chunks_processed": 0, "chunks_changed": 0, "paragraphs_added": 0, "model_calls": 0,
        }
        session.scalars.assert_not_called()

    def test_skips_non_youtube_documents(self):
        run = _run()
        doc = _doc(document_type="movie")
        session = _session(run, doc, [_chunk(1)])

        result = paragraphize_run_transcript_chunks(session, 163)

        assert result["chunks_processed"] == 0
        session.scalars.assert_not_called()

    def test_skips_documents_with_source_chapters(self, monkeypatch):
        run = _run()
        doc = _doc(text_md="## Rozdział pierwszy\n\ntreść " * 30)
        session = _session(run, doc, [_chunk(1)])
        monkeypatch.setattr(
            "library.text_functions.detect_chapters",
            lambda text: [{"title": "Rozdział pierwszy", "char_start": 0, "char_end": len(text)}],
        )

        result = paragraphize_run_transcript_chunks(session, 163)

        assert result["chunks_processed"] == 0
        session.scalars.assert_not_called()

    def test_skips_chunk_already_paragraphized(self, monkeypatch):
        run = _run()
        doc = _doc(text="Ściana tekstu bez rozdziałów źródłowych. " * 5)
        already_done = _chunk(1, corrected_text="Pierwszy akapit.\n\nDrugi akapit.")
        session = _session(run, doc, [already_done])
        monkeypatch.setattr("library.text_functions.detect_chapters", lambda text: [])
        monkeypatch.setattr(
            "library.transcript_paragraphs.paragraphize_chunk_text",
            lambda *a, **k: pytest.fail("should not call the LLM boundary-picker"),
        )

        result = paragraphize_run_transcript_chunks(session, 163)

        assert result["chunks_processed"] == 0
        assert already_done.corrected_text == "Pierwszy akapit.\n\nDrugi akapit."

    def test_paragraphizes_qualifying_chunk_and_persists(self, monkeypatch):
        run = _run()
        doc = _doc(text="Ściana tekstu bez rozdziałów źródłowych. " * 5)
        chunk = _chunk(1, corrected_text="Jedno pierwsze zdanie. Drugie zdanie bez podziału.")
        session = _session(run, doc, [chunk])
        monkeypatch.setattr("library.text_functions.detect_chapters", lambda text: [])
        monkeypatch.setattr(
            "library.transcript_paragraphs.paragraphize_chunk_text",
            lambda text, *, document_id, model, analysis_run_id: ParagraphizeResult(
                text="Jedno pierwsze zdanie.\n\nDrugie zdanie bez podziału.",
                chapter_count=1, paragraph_count=2, model_calls=1,
            ),
        )

        result = paragraphize_run_transcript_chunks(session, 163)

        assert result["chunks_processed"] == 1
        assert result["chunks_changed"] == 1
        assert result["paragraphs_added"] == 2
        assert result["model_calls"] == 1
        assert chunk.corrected_text == "Jedno pierwsze zdanie.\n\nDrugie zdanie bez podziału."
        assert session.commit.called
