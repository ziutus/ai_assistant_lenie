from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

import library.embedding as embedding_module  # noqa: E402
from library.models.embedding_results import EmbeddingResults  # noqa: E402


def _batch_response(texts, status_code=200, model="BAAI/bge-multilingual-gemma2"):
    response = EmbeddingResults(text=texts)
    response.status_code = status_code
    response.model_id = model
    if status_code == 200:
        response.embedding = [{"index": i, "embedding": [float(i)]} for i in range(len(texts))]
    else:
        response.error = "boom"
    return response


class TestGetEmbeddings:
    def test_sherlock_model_uses_one_batch_call(self, monkeypatch):
        calls = []

        def fake_batch(texts, model):
            calls.append(list(texts))
            return _batch_response(texts, model=model)

        monkeypatch.setattr(
            "library.api.cloudferro.sherlock.sherlock_embedding.sherlock_create_embeddings", fake_batch,
        )

        results = embedding_module.get_embeddings("BAAI/bge-multilingual-gemma2", ["a", "b", "c"])

        assert calls == [["a", "b", "c"]]
        assert [r.embedding for r in results] == [[0.0], [1.0], [2.0]]
        assert all(r.status == "success" for r in results)

    def test_batch_failure_marks_every_text_failed(self, monkeypatch):
        monkeypatch.setattr(
            "library.api.cloudferro.sherlock.sherlock_embedding.sherlock_create_embeddings",
            lambda texts, model: _batch_response(texts, status_code=500),
        )

        results = embedding_module.get_embeddings("BAAI/bge-multilingual-gemma2", ["a", "b"])

        assert len(results) == 2
        assert all(r.status == "error" and r.embedding is None for r in results)
        assert results[0].error_message == "boom"

    def test_out_of_order_batch_items_map_by_index(self, monkeypatch):
        def fake_batch(texts, model):
            response = _batch_response(texts, model=model)
            response.embedding = list(reversed(response.embedding))
            return response

        monkeypatch.setattr(
            "library.api.cloudferro.sherlock.sherlock_embedding.sherlock_create_embeddings", fake_batch,
        )

        results = embedding_module.get_embeddings("BAAI/bge-multilingual-gemma2", ["a", "b", "c"])

        assert [r.embedding for r in results] == [[0.0], [1.0], [2.0]]

    def test_non_batch_provider_falls_back_to_per_text_calls(self, monkeypatch):
        calls = []

        def fake_single(model, text):
            calls.append(text)
            return SimpleNamespace(text=text, status="success", embedding=[1.0])

        monkeypatch.setattr(embedding_module, "get_embedding", fake_single)

        results = embedding_module.get_embeddings("text-embedding-ada-002", ["a", "b"])

        assert calls == ["a", "b"]
        assert len(results) == 2

    def test_empty_input_returns_empty_list(self):
        assert embedding_module.get_embeddings("BAAI/bge-multilingual-gemma2", []) == []

    def test_unknown_model_raises(self):
        with pytest.raises(Exception, match="no model info"):
            embedding_module.get_embeddings("nieznany-model", ["a"])

    def test_english_only_model_is_not_available_for_generation(self):
        with pytest.raises(Exception, match="no model info"):
            embedding_module.get_embeddings("dunzhang/stella_en_1.5B_v5", ["polski tekst"])


class TestGenerateEmbeddingsBatching:
    def _run(self, monkeypatch, chunk_count=5, batch_size=2):
        from library import document_analysis_service as das
        from library.models.embedding_result import EmbeddingResult

        run = SimpleNamespace(id=21, document_id=9204)
        doc = SimpleNamespace(id=9204, language="pl", processing_status="DOCUMENT_INTO_DATABASE")
        chunks = [
            SimpleNamespace(
                id=100 + i, type="TEMAT", status="approved",
                corrected_text=None, original_text=f"Tekst rozdziału numer {i}.", position=i,
            )
            for i in range(1, chunk_count + 1)
        ]

        session = MagicMock()
        session.get.side_effect = lambda _cls, key: {21: run, 9204: doc}[key]
        session.scalars.return_value.all.return_value = chunks

        added = []

        class FakeRepo:
            def __init__(self, _session):
                pass

            def embedding_add(self, **kwargs):
                added.append(kwargs)

        monkeypatch.setattr("library.document_repository.DocumentRepository", FakeRepo)
        cfg = MagicMock()
        cfg.require.return_value = "BAAI/bge-multilingual-gemma2"
        monkeypatch.setattr("library.config_loader.load_config", lambda: cfg)

        batch_calls = []

        def fake_get_embeddings(model, texts):
            batch_calls.append(len(texts))
            return [EmbeddingResult(text=text, embedding=[0.1], status="success") for text in texts]

        monkeypatch.setattr("library.embedding.get_embeddings", fake_get_embeddings)
        monkeypatch.setattr(das, "EMBEDDING_BATCH_SIZE", batch_size)

        result = das.generate_embeddings_from_run(session, 21)
        return result, session, added, batch_calls, doc

    def test_batches_pieces_and_commits_per_batch(self, monkeypatch):
        result, session, added, batch_calls, doc = self._run(monkeypatch, chunk_count=5, batch_size=2)

        assert result["embeddings_created"] == 5
        assert result["embeddings_failed"] == 0
        assert len(added) == 5
        # 5 pieces in batches of 2 -> 3 API calls
        assert batch_calls == [2, 2, 1]
        # commits: 1 after the delete + 1 per batch (3) + 1 final
        assert session.commit.call_count == 5
        assert doc.processing_status == "EMBEDDING_EXIST"

    def test_failed_batch_items_are_counted_not_stored(self, monkeypatch):
        from library.models.embedding_result import EmbeddingResult

        def failing_get_embeddings(model, texts):
            return [EmbeddingResult(text=text, status="error", error_message="boom") for text in texts]

        monkeypatch.setattr("library.embedding.get_embeddings", failing_get_embeddings)
        # _run would override the patch, so patch again inside via a plain call path
        from library import document_analysis_service as das
        from unittest.mock import MagicMock as MM

        run = SimpleNamespace(id=21, document_id=9204)
        doc = SimpleNamespace(id=9204, language="pl", processing_status="DOCUMENT_INTO_DATABASE")
        chunks = [SimpleNamespace(id=101, type="TEMAT", status="approved",
                                  corrected_text=None, original_text="Tekst.", position=1)]
        session = MM()
        session.get.side_effect = lambda _cls, key: {21: run, 9204: doc}[key]
        session.scalars.return_value.all.return_value = chunks

        class FakeRepo:
            def __init__(self, _session):
                pass

            def embedding_add(self, **kwargs):
                raise AssertionError("failed embeddings must not be stored")

        monkeypatch.setattr("library.document_repository.DocumentRepository", FakeRepo)
        cfg = MM()
        cfg.require.return_value = "BAAI/bge-multilingual-gemma2"
        monkeypatch.setattr("library.config_loader.load_config", lambda: cfg)

        result = das.generate_embeddings_from_run(session, 21)

        assert result["embeddings_created"] == 0
        assert result["embeddings_failed"] == 1
        assert doc.processing_status == "DOCUMENT_INTO_DATABASE"
