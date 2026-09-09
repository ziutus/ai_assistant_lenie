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
    _merge_tags,
    _normalize_obsidian_tag,
    _note_url,
    _parse_frontmatter,
    _reimport_one_note,
    _has_complete_embeddings,
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


def _make_doc(doc_id=101, obsidian_source_hash=None, tags=None):
    doc = MagicMock()
    doc.id = doc_id
    doc.text = "Treść notatki"
    doc.text_md = "Treść notatki"
    doc.language = None
    doc.obsidian_source_hash = obsidian_source_hash
    doc.tags = tags
    doc.processing_status = "EMBEDDING_EXIST"
    doc.processing_error_code = None
    return doc


class TestNoteUrl:
    def test_builds_synthetic_obsidian_scheme(self):
        assert _note_url("02-wiedza/Informatyka/k8s.md") == "obsidian://02-wiedza/Informatyka/k8s.md"


class TestNormalizeObsidianTag:
    def test_flattens_nested_tag(self):
        assert _normalize_obsidian_tag("wiedza/informatyka") == "wiedza-informatyka"

    def test_strips_leading_hash_and_lowercases(self):
        assert _normalize_obsidian_tag("#Linux") == "linux"

    def test_collapses_internal_whitespace(self):
        assert _normalize_obsidian_tag("  sluzby specjalne  ") == "sluzby-specjalne"

    def test_strips_commas_the_csv_separator_would_otherwise_break_on(self):
        assert _normalize_obsidian_tag("a,b") == "ab"


class TestParseFrontmatter:
    def test_no_frontmatter_returns_content_unchanged(self):
        body, tags = _parse_frontmatter("# Linux\n\nTreść notatki.")
        assert body == "# Linux\n\nTreść notatki."
        assert tags == []

    def test_yaml_list_tags_are_extracted_and_stripped_from_body(self):
        content = "---\ntags:\n  - wiedza/informatyka\n  - Linux\n---\n[[Linux]]\n"
        body, tags = _parse_frontmatter(content)
        assert body == "[[Linux]]\n"
        assert tags == ["wiedza-informatyka", "linux"]

    def test_inline_list_tags(self):
        content = "---\ntags: [a, B]\n---\ntreść\n"
        _, tags = _parse_frontmatter(content)
        assert tags == ["a", "b"]

    def test_comma_separated_scalar_tags(self):
        content = "---\ntags: a, b\n---\ntreść\n"
        _, tags = _parse_frontmatter(content)
        assert tags == ["a", "b"]

    def test_no_tags_key_returns_empty_list(self):
        content = "---\ntitle: Coś\n---\ntreść\n"
        body, tags = _parse_frontmatter(content)
        assert body == "treść\n"
        assert tags == []

    def test_malformed_yaml_degrades_to_raw_content(self):
        content = "---\ntags: [unclosed\n---\ntreść\n"
        body, tags = _parse_frontmatter(content)
        assert body == content
        assert tags == []

    def test_mid_document_triple_dash_is_not_treated_as_frontmatter(self):
        content = "Akapit.\n\n---\n\nDrugi akapit."
        body, tags = _parse_frontmatter(content)
        assert body == content
        assert tags == []


class TestMergeTags:
    def test_no_new_tags_keeps_existing_untouched(self):
        assert _merge_tags("a,b", []) == "a,b"

    def test_new_tags_added_to_empty_existing(self):
        assert _merge_tags(None, ["a", "b"]) == "a,b"

    def test_union_deduplicates_and_preserves_first_occurrence_order(self):
        assert _merge_tags("a,b", ["b", "c"]) == "a,b,c"

    def test_manually_added_tag_survives_when_frontmatter_has_no_tags(self):
        assert _merge_tags("manual-tag", []) == "manual-tag"


class TestExecuteObsidianReimport:
    def test_new_note_creates_document_and_embeddings(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/kubernetes-podstawy.md"
        note.write_text("# Kubernetes\n\nPodstawy orkiestracji.", encoding="utf-8")

        doc = _make_doc()
        session = MagicMock()
        job = MagicMock(id="job-1", parameters={})

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
        assert call_kwargs["processing_status"] == "READY_FOR_EMBEDDING"
        assert call_kwargs["skip_if_exists"] is True
        assert call_kwargs["title"] == "kubernetes-podstawy"

        mock_repo_cls.return_value.embedding_add.assert_called()
        mock_repo_cls.return_value.embedding_delete.assert_not_called()
        assert doc.obsidian_source_hash == get_hash("# Kubernetes\n\nPodstawy orkiestracji.")
        assert doc.processing_status == "EMBEDDING_EXIST"
        assert doc.processing_error_code is None
        assert summary == {"scanned": 1, "created": 1, "updated": 0, "skipped": 0, "failed": 0}

    def test_new_note_frontmatter_tags_stripped_from_text_and_passed_as_tags(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/linux.md"
        note.write_text(
            "---\ntags:\n  - wiedza/informatyka\n  - Linux\n---\n[[Linux]]\n", encoding="utf-8",
        )

        doc = _make_doc()
        session = MagicMock()
        job = MagicMock(id="job-1b", parameters={})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository"), \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = None
            mock_service_cls.return_value.import_document.return_value = (doc, "added")
            mock_get_embedding.return_value = EmbeddingResult(
                text="piece", embedding=[0.1, 0.2], status="success",
            )

            execute_obsidian_reimport(session, job)

        call_kwargs = mock_service_cls.return_value.import_document.call_args.kwargs
        assert call_kwargs["text"] == "[[Linux]]\n"
        assert call_kwargs["text_md"] == "[[Linux]]\n"
        assert call_kwargs["tags"] == "wiedza-informatyka,linux"

    def test_existing_note_unchanged_is_skipped_without_embedding_call(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Geopolityka i polityka/nato.md"
        content = "Treść o NATO."
        note.write_text(content, encoding="utf-8")

        existing_doc = _make_doc(obsidian_source_hash=get_hash(content))
        session = MagicMock()
        session.scalars.return_value.all.return_value = [content]
        job = MagicMock(id="job-2", parameters={})

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
        note = vault / "02-wiedza/Geopolityka i polityka/nato.md"
        new_content = "Treść o NATO -- zaktualizowana."
        note.write_text(new_content, encoding="utf-8")

        existing_doc = _make_doc(doc_id=202, obsidian_source_hash="stary-hash-nie-pasuje")
        session = MagicMock()
        job = MagicMock(id="job-3", parameters={})
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

    def test_existing_note_frontmatter_tags_merge_with_manually_added_tags(self, tmp_path):
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/linux.md"
        new_content = "---\ntags:\n  - wiedza/informatyka\n  - Linux\n---\n[[Linux]]\n"
        note.write_text(new_content, encoding="utf-8")

        existing_doc = _make_doc(doc_id=303, obsidian_source_hash="stary-hash", tags="manual-tag")
        session = MagicMock()
        job = MagicMock(id="job-3b", parameters={})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService"), \
             patch("library.obsidian_reimport_service.DocumentRepository"), \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = existing_doc
            mock_get_embedding.return_value = EmbeddingResult(
                text="piece", embedding=[0.1, 0.2], status="success",
            )

            execute_obsidian_reimport(session, job)

        assert existing_doc.text == "[[Linux]]\n"
        assert existing_doc.text_md == "[[Linux]]\n"
        assert existing_doc.tags == "manual-tag,wiedza-informatyka,linux"

    def test_existing_note_with_null_hash_is_treated_as_changed(self, tmp_path):
        """Notes imported by Story 42.1 predate this column -- NULL must never match."""
        vault = _make_vault(tmp_path)
        note = vault / "02-wiedza/Informatyka/legacy.md"
        note.write_text("Treść zaimportowana przed dodaniem hasha.", encoding="utf-8")

        existing_doc = _make_doc(doc_id=303, obsidian_source_hash=None)
        session = MagicMock()
        job = MagicMock(id="job-4", parameters={})

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
        job = MagicMock(id="job-5", parameters={})

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
        job = MagicMock(id="job-6", parameters={})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository"):
            summary = execute_obsidian_reimport(session, job)

        mock_document_cls.get_by_url.assert_not_called()
        mock_service_cls.return_value.import_document.assert_not_called()
        assert summary == {"scanned": 1, "created": 0, "updated": 0, "skipped": 1, "failed": 0}


class TestSingleNoteReimport:
    """Story 42.3: obsidian_vault_watcher.py enqueues a targeted job with
    parameters={"relative_path": ...} instead of waiting for the daily
    full-vault scan."""

    def test_relative_path_reimports_only_that_note(self, tmp_path):
        vault = _make_vault(tmp_path)
        target = vault / "02-wiedza/Informatyka/kubernetes-podstawy.md"
        target.write_text("# Kubernetes\n\nPodstawy orkiestracji.", encoding="utf-8")
        # A second, untouched note in the same subfolder must NOT be scanned.
        (vault / "02-wiedza/Informatyka/inna-notatka.md").write_text("Coś innego.", encoding="utf-8")

        doc = _make_doc()
        session = MagicMock()
        job = MagicMock(id="job-7", parameters={"relative_path": "02-wiedza/Informatyka/kubernetes-podstawy.md"})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository"), \
             patch("library.embedding.get_embedding") as mock_get_embedding:
            mock_document_cls.get_by_url.return_value = None
            mock_service_cls.return_value.import_document.return_value = (doc, "added")
            mock_get_embedding.return_value = EmbeddingResult(text="piece", embedding=[0.1, 0.2], status="success")

            summary = execute_obsidian_reimport(session, job)

        mock_service_cls.return_value.import_document.assert_called_once()
        call_kwargs = mock_service_cls.return_value.import_document.call_args.kwargs
        assert call_kwargs["url"] == "obsidian://02-wiedza/Informatyka/kubernetes-podstawy.md"
        assert summary == {"scanned": 1, "created": 1, "updated": 0, "skipped": 0, "failed": 0}

    def test_relative_path_missing_file_is_reported_failed(self, tmp_path):
        vault = _make_vault(tmp_path)
        session = MagicMock()
        job = MagicMock(id="job-8", parameters={"relative_path": "02-wiedza/Informatyka/nie-istnieje.md"})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService"), \
             patch("library.obsidian_reimport_service.DocumentRepository"):
            summary = execute_obsidian_reimport(session, job)

        mock_document_cls.get_by_url.assert_not_called()
        assert summary == {"scanned": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 1}

    def test_relative_path_outside_pilot_subfolders_is_refused(self, tmp_path):
        vault = _make_vault(tmp_path)
        outside = vault / "03-personal" / "sekret.md"
        outside.parent.mkdir(parents=True)
        outside.write_text("nie powinno zostać zaimportowane", encoding="utf-8")

        session = MagicMock()
        job = MagicMock(id="job-9", parameters={"relative_path": "03-personal/sekret.md"})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService") as mock_service_cls, \
             patch("library.obsidian_reimport_service.DocumentRepository"):
            summary = execute_obsidian_reimport(session, job)

        mock_document_cls.get_by_url.assert_not_called()
        mock_service_cls.return_value.import_document.assert_not_called()
        assert summary == {"scanned": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 1}

    def test_relative_path_traversal_is_refused(self, tmp_path):
        vault = _make_vault(tmp_path)
        session = MagicMock()
        job = MagicMock(id="job-10", parameters={"relative_path": "../../etc/passwd"})

        with patch("library.obsidian_reimport_service.load_config", return_value=_make_config(vault)), \
             patch("library.obsidian_reimport_service.Document") as mock_document_cls, \
             patch("library.obsidian_reimport_service.DocumentService"), \
             patch("library.obsidian_reimport_service.DocumentRepository"):
            summary = execute_obsidian_reimport(session, job)

        mock_document_cls.get_by_url.assert_not_called()
        assert summary == {"scanned": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 1}


class TestJobTypeRegistration:
    def test_obsidian_reimport_is_a_registered_job_type(self):
        from library.job_queue import JOB_TYPES

        assert "obsidian_reimport" in JOB_TYPES


class TestEmbeddingRecovery:
    def test_completeness_requires_matching_model_document_and_all_duplicate_fragments(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from library.db.models import DocumentEmbedding

        engine = create_engine("sqlite://")
        DocumentEmbedding.__table__.create(engine)
        with Session(engine) as session:
            session.add_all([
                DocumentEmbedding(document_id=1, model="active", text="same", embedding=[0.1]),
                DocumentEmbedding(document_id=1, model="old", text="same", embedding=[0.1]),
                DocumentEmbedding(document_id=2, model="active", text="same", embedding=[0.1]),
                DocumentEmbedding(document_id=1, model="active", text="same", embedding=None),
            ])
            session.commit()
            assert not _has_complete_embeddings(session, 1, "active", ["same", "same"])
            session.add(DocumentEmbedding(document_id=1, model="active", text="same", embedding=[0.2]))
            session.commit()
            assert _has_complete_embeddings(session, 1, "active", ["same", "same"])
        engine.dispose()

    def test_failed_replacement_preserves_previous_vectors_in_database(self, tmp_path):
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from library.db.models import DocumentEmbedding
        from library.document_repository import DocumentRepository

        engine = create_engine("sqlite://")
        DocumentEmbedding.__table__.create(engine)
        note = tmp_path / "note.md"
        note.write_text("new content", encoding="utf-8")
        doc = _make_doc(obsidian_source_hash="old-hash")
        with Session(engine) as session:
            session.add(DocumentEmbedding(document_id=doc.id, model="model", text="old content", embedding=[0.1]))
            session.commit()
            with patch("library.obsidian_reimport_service.Document.get_by_url", return_value=doc), \
                 patch("library.obsidian_reimport_service._embedding_parts", return_value=["first", "second"]), \
                 patch("library.embedding.get_embedding", side_effect=[
                     EmbeddingResult(text="first", embedding=[0.2], status="success"),
                     RuntimeError("provider unavailable"),
                 ]):
                assert _reimport_one_note(session, MagicMock(), DocumentRepository(session), "model", tmp_path, note) == "failed"
            assert session.scalars(select(DocumentEmbedding.text)).all() == ["old content"]
        engine.dispose()

    @pytest.mark.parametrize("stored", [["first", "second"], ["first"], [], ["wrong", "second"]])
    def test_legacy_status_repaired_only_after_all_fragments_verified(self, tmp_path, stored):
        note = tmp_path / "note.md"
        content = "first\nsecond"
        note.write_text(content, encoding="utf-8")
        doc = _make_doc(obsidian_source_hash=get_hash(content))
        doc.processing_status = "URL_ADDED"
        session, service, repo = MagicMock(), MagicMock(), MagicMock()
        session.scalars.return_value.all.return_value = stored
        with patch("library.obsidian_reimport_service.Document.get_by_url", return_value=doc), \
             patch("library.obsidian_reimport_service._embedding_parts", return_value=["first", "second"]), \
             patch("library.embedding.get_embedding", return_value=EmbeddingResult(
                 text="piece", embedding=[0.1, 0.2], status="success",
             )) as embed, \
             patch("library.obsidian_reimport_service.request_suggestions"):
            outcome = _reimport_one_note(session, service, repo, "model", tmp_path, note)

        assert doc.processing_status == "EMBEDDING_EXIST"
        assert doc.processing_error_code is None
        session.commit.assert_called_once()
        if stored == ["first", "second"]:
            assert outcome == "skipped"
            embed.assert_not_called()
            repo.embedding_delete.assert_not_called()
        else:
            assert outcome == "updated"
            assert embed.call_count == 2
            repo.embedding_delete.assert_called_once_with(doc.id, "model")

    @pytest.mark.parametrize("failure", [
        EmbeddingResult(text="second", embedding=[], status="error"),
        EmbeddingResult(text="second", embedding=[], status="success"),
        RuntimeError("provider unavailable"),
    ])
    @pytest.mark.parametrize("new_note", [False, True])
    def test_partial_failure_rolls_back_and_unchanged_file_is_retried(self, tmp_path, failure, new_note):
        note = tmp_path / "note.md"
        note.write_text("new content", encoding="utf-8")
        doc = _make_doc(obsidian_source_hash=None if new_note else "old-hash")
        original_hash = doc.obsidian_source_hash
        session, service, repo = MagicMock(), MagicMock(), MagicMock()
        service.import_document.return_value = (doc, "added")
        success = EmbeddingResult(text="piece", embedding=[0.1, 0.2], status="success")
        with patch("library.obsidian_reimport_service.Document.get_by_url", return_value=None if new_note else doc) as get_doc, \
             patch("library.obsidian_reimport_service._embedding_parts", return_value=["first", "second"]), \
             patch("library.embedding.get_embedding", side_effect=[success, failure, success, success]) as embed, \
             patch("library.obsidian_reimport_service.request_suggestions") as suggestions:
            assert _reimport_one_note(session, service, repo, "model", tmp_path, note) == "failed"
            session.rollback.assert_called_once()
            session.commit.assert_not_called()
            suggestions.assert_not_called()
            assert doc.obsidian_source_hash == original_hash

            # import_document commits new rows before embedding; the next run
            # must retry that existing row even though the file hasn't changed.
            get_doc.return_value = doc
            assert _reimport_one_note(session, service, repo, "model", tmp_path, note) == "updated"

        assert embed.call_count == 4
        assert doc.obsidian_source_hash == get_hash("new content")
        assert doc.processing_status == "EMBEDDING_EXIST"
        session.commit.assert_called_once()

    def test_frontmatter_only_note_is_imported_without_claiming_embeddings_exist(self, tmp_path):
        note = tmp_path / "note.md"
        content = "---\ntags: [linux]\n---\n"
        note.write_text(content, encoding="utf-8")
        doc = _make_doc(obsidian_source_hash="old-hash")
        session, service, repo = MagicMock(), MagicMock(), MagicMock()
        session.scalars.return_value.all.return_value = []
        with patch("library.obsidian_reimport_service.Document.get_by_url", return_value=doc), \
             patch("library.embedding.get_embedding") as embed, \
             patch("library.obsidian_reimport_service.request_suggestions"):
            assert _reimport_one_note(session, service, repo, "model", tmp_path, note) == "updated"
            assert _reimport_one_note(session, service, repo, "model", tmp_path, note) == "skipped"
        assert doc.processing_status == "DOCUMENT_INTO_DATABASE"
        assert doc.obsidian_source_hash == get_hash(content)
        embed.assert_not_called()
