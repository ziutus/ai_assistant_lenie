"""Unit tests for document_analysis_service.generate_embeddings_from_run.

DB session, embedding provider and the repository layer are mocked — verifies
selection logic (TEMAT + approved only), text preference (corrected_text over
original_text), chunk_id propagation, and idempotent re-run (old chunk-linked
embeddings deleted first).
"""

from unittest.mock import MagicMock

import pytest

import library.document_analysis_service as das
from library.db.models import DocumentAnalysisRun, DocumentChunk, Document
from library.document_analysis_service import generate_embeddings_from_run
from library.models.embedding_result import EmbeddingResult


def _chunk(id_, type_, status, corrected_text=None, original_text="tekst oryginalny"):
    c = MagicMock(spec=DocumentChunk)
    c.id = id_
    c.type = type_
    c.status = status
    c.corrected_text = corrected_text
    c.original_text = original_text
    c.position = id_
    return c


@pytest.fixture
def fake_run():
    run = MagicMock(spec=DocumentAnalysisRun)
    run.id = 5
    run.document_id = 42
    return run


@pytest.fixture
def fake_doc():
    doc = MagicMock(spec=Document)
    doc.id = 42
    doc.language = "pl"
    return doc


@pytest.fixture
def session(fake_run, fake_doc):
    s = MagicMock()

    def _get(model, id_):
        if model is DocumentAnalysisRun:
            return fake_run
        if model is Document:
            return fake_doc
        return None

    s.get.side_effect = _get
    return s


@pytest.fixture
def embedding_env(monkeypatch):
    """Patch config, embedding provider and the repository add() call."""
    monkeypatch.setattr(das, "logger", das.logger)  # no-op, keeps import explicit

    class FakeConfig:
        def require(self, key):
            assert key == "EMBEDDING_MODEL"
            return "test-embedding-model"

    monkeypatch.setattr("library.config_loader.load_config", lambda: FakeConfig())

    calls = {"embedding_add": []}

    class FakeWebsitesDB:
        def __init__(self, session):
            pass

        def embedding_add(self, **kwargs):
            calls["embedding_add"].append(kwargs)

    monkeypatch.setattr(
        "library.document_repository.DocumentRepository", FakeWebsitesDB,
    )
    monkeypatch.setattr(
        "library.embedding.get_embedding",
        lambda model, text: EmbeddingResult(text=text, embedding=[0.1, 0.2], status="success"),
    )
    return calls


class TestGenerateEmbeddingsFromRun:
    def test_run_not_found_raises(self, session):
        session.get.side_effect = lambda model, id_: None
        with pytest.raises(ValueError, match="Run 5 not found"):
            generate_embeddings_from_run(session, 5)

    def test_only_approved_temat_chunks_are_embedded(self, session, embedding_env):
        chunks = [
            _chunk(1, "TEMAT", "approved", original_text="Merytoryczna treść o gospodarce. " * 30),
            _chunk(2, "TEMAT", "pending", original_text="Nie powinno się embedować."),
            _chunk(3, "REKLAMA", "approved", original_text="Reklama, pomijana mimo approved."),
            _chunk(4, "SZUM", "approved", original_text="Szum, pomijany mimo approved."),
        ]
        session.scalars.return_value.all.return_value = chunks

        result = generate_embeddings_from_run(session, 5)

        assert result["chunks_considered"] == 1
        assert len(embedding_env["embedding_add"]) >= 1
        assert all(kw["chunk_id"] == 1 for kw in embedding_env["embedding_add"])

    def test_prefers_corrected_text_over_original(self, session, embedding_env):
        chunks = [_chunk(1, "TEMAT", "approved", corrected_text="Wersja poprawiona.", original_text="Wersja surowa.")]
        session.scalars.return_value.all.return_value = chunks

        generate_embeddings_from_run(session, 5)

        assert embedding_env["embedding_add"][0]["text"] == "Wersja poprawiona."

    def test_photo_captions_are_filtered_only_from_embedding_copy(self, session, embedding_env):
        source = "Treść przed zdjęciem.\nFot. Jan Kowalski / PAP\nTreść po zdjęciu."
        chunks = [_chunk(1, "TEMAT", "approved", original_text=source)]
        session.scalars.return_value.all.return_value = chunks

        generate_embeddings_from_run(session, 5)

        embedded = embedding_env["embedding_add"][0]["text"]
        assert "Fot. Jan Kowalski" not in embedded
        assert "Treść przed zdjęciem" in embedded
        assert "Treść po zdjęciu" in embedded
        assert chunks[0].original_text == source

    def test_empty_text_chunk_is_skipped(self, session, embedding_env):
        chunks = [_chunk(1, "TEMAT", "approved", original_text="   ")]
        session.scalars.return_value.all.return_value = chunks

        result = generate_embeddings_from_run(session, 5)

        assert result["chunks_skipped_empty"] == 1
        assert result["embeddings_created"] == 0

    def test_deletes_existing_chunk_linked_embeddings_before_recreating(self, session, embedding_env):
        chunks = [_chunk(1, "TEMAT", "approved", original_text="Treść.")]
        session.scalars.return_value.all.return_value = chunks

        generate_embeddings_from_run(session, 5)

        assert session.execute.called  # delete() statement issued before re-adding

    def test_marks_document_embedding_exist_when_embeddings_created(self, session, embedding_env, fake_doc):
        chunks = [_chunk(1, "TEMAT", "approved", original_text="Treść merytoryczna wystarczająco długa.")]
        session.scalars.return_value.all.return_value = chunks

        generate_embeddings_from_run(session, 5)

        assert fake_doc.document_state == "EMBEDDING_EXIST"

    def test_failed_embedding_provider_is_skipped_not_raised(self, session, embedding_env, monkeypatch):
        monkeypatch.setattr(
            "library.embedding.get_embedding",
            lambda model, text: EmbeddingResult(text=text, embedding=[], status="error"),
        )
        chunks = [_chunk(1, "TEMAT", "approved", original_text="Treść.")]
        session.scalars.return_value.all.return_value = chunks

        result = generate_embeddings_from_run(session, 5)

        assert result["embeddings_created"] == 0
        assert embedding_env["embedding_add"] == []
