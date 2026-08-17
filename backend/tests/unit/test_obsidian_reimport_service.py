"""Unit tests for obsidian_reimport_service (Story 42.1, extended in 42.2).

All tests use a real temporary directory as the vault (filesystem walk is
part of what's under test) but mock DocumentService/DocumentRepository/
Document/embedding -- no database or LLM/embedding provider required.
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.obsidian_reimport_service import (
    PILOT_SUBFOLDERS,
    _note_url,
    execute_obsidian_reimport,
)
from library.models.embedding_result import EmbeddingResult
from library.text_functions import get_hash


def _make_vault(tmp_path):
    for subfolder in PILOT_SUBFOLDERS:
        (tmp_path / subfolder).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_config(vault_path):
    cfg = MagicMock()
    cfg.get.return_value = str(vault_path)
    cfg.require.return_value = "BAAI/bge-multilingual-gemma2"
    return cfg


def _make_doc(doc_id=101, obsidian_source_hash=None):
    doc = MagicMock()
    doc.id = doc_id
    doc.text = "Treść notatki"
    doc.text_md = "Treść notatki"
    doc.language = None
    doc.obsidian_source_hash = obsidian_source_hash
    return doc


class TestNoteUrl:
    def test_builds_synthetic_obsidian_scheme(self):
        assert _note_url("02-wiedza/Informatyka/k8s.md") == "obsidian://02-wiedza/Informatyka/k8s.md"


class TestExecuteObsidianReimport:
    def test_new_note_creates_document_and_embeddings(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/kubernetes-podstawy.md"
        note.write_text("# Kubernetes\n\nPodstawy orkiestracji.", encoding="utf-8")

        doc = _make_doc()
        session = MagicMock()
        job = MagicMock(id="job-1")

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository") as mock_repo_cls, \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = None
            mock_service_cls.return_value.import_document.return_value = (doc, "added")
            mock_get_embedding.return_value = EmbeddingResult(
                text="piece", embedding=[0.1, 0.2], status="success",
            )

            summary = execute_obsidian_reimport(session, job)

        mock_service_cls.return_value.import_document.assert_called_once()
        call_kwargs = mock_service_cls.return_value.import_document.call_args.kwargs
        assert call_kwargs["url"] == "obsidian://02-wiedza/Informatyka/kubernetes-podstawy.md"
        assert call_kwargs["document_type"] == "obsidian_note"
        assert call_kwargs["skip_if_exists"] is True
        assert call_kwargs["title"] == "kubernetes-podstawy"

        mock_repo_cls.return_value.embedding_add.assert_called()
        mock_repo_cls.return_value.embedding_delete.assert_not_called()
        assert doc.obsidian_source_hash == get_hash("# Kubernetes\n\nPodstawy orkiestracji.")
        assert summary == {"scanned": 1, "created": 1, "updated": 0, "skipped": 0, "failed": 0}

    def test_existing_note_unchanged_is_skipped_without_embedding_call(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Geopolityka/nato.md"
        content = "Treść o NATO."
        note.write_text(content, encoding="utf-8")

        existing_doc = _make_doc(obsidian_source_hash=get_hash(content))
        session = MagicMock()
        job = MagicMock(id="job-2")

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository") as mock_repo_cls, \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = existing_doc

            summary = execute_obsidian_reimport(session, job)

        mock_service_cls.return_value.import_document.assert_not_called()
        mock_get_embedding.assert_not_called()
        mock_repo_cls.return_value.embedding_add.assert_not_called()
        mock_repo_cls.return_value.embedding_delete.assert_not_called()
        assert summary == {"scanned": 1, "created": 0, "updated": 0, "skipped": 1, "failed": 0}

    def test_existing_note_changed_updates_document_and_reembeds(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Geopolityka/nato.md"
        new_content = "Treść o NATO -- zaktualizowana."
        note.write_text(new_content, encoding="utf-8")

        existing_doc = _make_doc(doc_id=202, obsidian_source_hash="stary-hash-nie-pasuje")
        session = MagicMock()
        job = MagicMock(id="job-3")
        call_order = []

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository") as mock_repo_cls, \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = existing_doc
            mock_repo_cls.return_value.embedding_delete.side_effect = lambda *a, **k: call_order.append("delete")
            mock_repo_cls.return_value.embedding_add.side_effect = lambda *a, **k: call_order.append("add")
            mock_get_embedding.return_value = EmbeddingResult(
                text="piece", embedding=[0.1, 0.2], status="success",
            )

            summary = execute_obsidian_reimport(session, job)

        mock_service_cls.return_value.import_document.assert_not_called()
        mock_repo_cls.return_value.embedding_delete.assert_called_once_with(202, "BAAI/bge-multilingual-gemma2")
        mock_repo_cls.return_value.embedding_add.assert_called()
        assert call_order[0] == "delete"
        assert existing_doc.text == new_content
        assert existing_doc.text_md == new_content
        assert existing_doc.title == "nato"
        assert existing_doc.obsidian_source_hash == get_hash(new_content)
        assert summary == {"scanned": 1, "created": 0, "updated": 1, "skipped": 0, "failed": 0}

    def test_existing_note_with_null_hash_is_treated_as_changed(self, tmp_path):
        """Notes imported by Story 42.1 predate this column -- NULL must never match."""
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/legacy.md"
        note.write_text("Treść zaimportowana przed dodaniem hasha.", encoding="utf-8")

        existing_doc = _make_doc(doc_id=303, obsidian_source_hash=None)
        session = MagicMock()
        job = MagicMock(id="job-4")

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository") as mock_repo_cls, \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = existing_doc
            mock_get_embedding.return_value = EmbeddingResult(
                text="piece", embedding=[0.1, 0.2], status="success",
            )

            summary = execute_obsidian_reimport(session, job)

        mock_service_cls.return_value.import_document.assert_not_called()
        mock_repo_cls.return_value.embedding_delete.assert_called_once_with(303, "BAAI/bge-multilingual-gemma2")
        assert existing_doc.obsidian_source_hash is not None
        assert summary == {"scanned": 1, "created": 0, "updated": 1, "skipped": 0, "failed": 0}

    def test_missing_configured_subfolder_is_not_fatal(self, tmp_path):
        # Only create Informatyka, not Geopolityka -- both are configured.
        (tmp_path / "02-wiedza/Informatyka").mkdir(parents=True)
        session = MagicMock()
        job = MagicMock(id="job-5")

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(tmp_path)), \
             patch("library.obsidian_reimport_service.Document"), \
             patch("library.obsidian_reimport_service.DocumentService"), \
             patch("library.obsidian_reimport_service.DocumentRepository"):
            summary = execute_obsidian_reimport(session, job)

        assert summary == {"scanned": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

    def test_empty_file_is_skipped(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/pusta.md"
        note.write_text("   \n", encoding="utf-8")

        session = MagicMock()
        job = MagicMock(id="job-6")

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository"):
            summary = execute_obsidian_reimport(session, job)

        mock_document_cls.get_by_url.assert_not_called()
        mock_service_cls.return_value.import_document.assert_not_called()
        assert summary == {"scanned": 1, "created": 0, "updated": 0, "skipped": 1, "failed": 0}


class TestJobTypeRegistration:
    def test_obsidian_reimport_is_a_registered_job_type(self):
        from library.job_queue import JOB_TYPES

        assert "obsidian_reimport" in JOB_TYPES
