from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from library.document_processing_service import (
    DocumentProcessingService,
    document_prepare_idempotency_key,
)


class MemoryStorage:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = data

    def get_bytes(self, key):
        return self.objects[key]

    def exists(self, key):
        return key in self.objects


def test_idempotency_key_contains_document_uuid():
    assert document_prepare_idempotency_key(12, "abc") == "document_prepare:12:abc"


def test_execute_materializes_html_runs_pipeline_and_uploads_artifacts(tmp_path):
    document = SimpleNamespace(
        id=12,
        uuid="abc",
        document_type="webpage",
        text_md=None,
        text_extracted=None,
        url="https://example.test",
    )
    job = SimpleNamespace(
        id="job1",
        parameters={"document_id": 12, "document_uuid": "abc"},
        status="running",
    )
    storage = MemoryStorage({"abc.html": b"<p>HTML</p>"})

    class Session:
        def get(self, model, key):
            if getattr(model, "__name__", "") == "Job":
                return job
            return document

        def commit(self):
            pass

        def execute(self, statement):
            return None

    clean_text = "CLEAN " * 60  # a realistic-length article, well above the empty-page floor

    def fake_extract(doc, cache_dir, **kwargs):
        Path(cache_dir, "artifact.json").write_text("{}", encoding="utf-8")
        return "RAW MARKDOWN", "ARTICLE"

    images = [{"url": "https://example.test/photo.jpg", "alt": "Photo"}]
    session = Session()

    with (
        patch("library.document_processing_service.extract_article", fake_extract),
        patch("library.document_processing_service.clean_article_text", return_value={"text": clean_text, "images": images}),
        patch("library.document_images.replace_document_images") as replace_images,
    ):
        result = DocumentProcessingService(session, storage, str(tmp_path)).execute(job)

    replace_images.assert_called_once_with(session, 12, images)
    assert result["markdown_created"] is True
    assert result["llm_extracted"] is True
    assert result["artifacts_uploaded"] == 2  # materialized HTML + fake artifact
    assert document.text_extracted == "ARTICLE"
    assert document.text_md == clean_text
    assert storage.objects["cache/markdown/12/12.html"] == b"<p>HTML</p>"


def test_execute_flags_empty_extraction_as_error(tmp_path):
    document = SimpleNamespace(
        id=13,
        uuid="def",
        document_type="webpage",
        text_md=None,
        text_extracted=None,
        url="https://login-wall.test",
        processing_status="NEED_CLEAN_MD",
        processing_error_code=None,
    )
    document.set_processing_status = lambda value: setattr(document, "processing_status", value)
    document.set_processing_error_code = lambda value: setattr(document, "processing_error_code", value)
    job = SimpleNamespace(id="job2", parameters={"document_id": 13, "document_uuid": "def"}, status="running")
    storage = MemoryStorage({"def.html": b"<html><body>Zaloguj sie</body></html>"})

    class Session:
        def get(self, model, key):
            return job if getattr(model, "__name__", "") == "Job" else document

        def commit(self):
            pass

        def execute(self, statement):
            return None

    with (
        patch("library.document_processing_service.extract_article", lambda *a, **k: ("RAW", "tiny")),
        patch("library.document_processing_service.clean_article_text", return_value={"text": "za krotko"}),
    ):
        result = DocumentProcessingService(Session(), storage, str(tmp_path)).execute(job)

    assert result["content_empty"] is True
    assert result["markdown_created"] is False
    assert document.processing_status == "ERROR"
    assert document.processing_error_code == "ERROR_DOWNLOAD"
    assert document.text_md is None


def _run_success(tmp_path, processing_status, processing_error_code):
    document = SimpleNamespace(
        id=14,
        uuid="ghi",
        document_type="webpage",
        text_md=None,
        text_extracted=None,
        url="https://recovered.test",
        processing_status=processing_status,
        processing_error_code=processing_error_code,
    )
    document.set_processing_status = lambda value: setattr(document, "processing_status", value)
    document.set_processing_error_code = lambda value: setattr(document, "processing_error_code", value)
    job = SimpleNamespace(id="job3", parameters={"document_id": 14, "document_uuid": "ghi"}, status="running")
    storage = MemoryStorage({"ghi.html": b"<p>HTML</p>"})

    class Session:
        def get(self, model, key):
            return job if getattr(model, "__name__", "") == "Job" else document

        def commit(self):
            pass

        def execute(self, statement):
            return None

    with (
        patch("library.document_processing_service.extract_article", lambda *a, **k: ("RAW", "ARTICLE")),
        patch(
            "library.document_processing_service.clean_article_text",
            return_value={"text": "CLEAN " * 60, "images": []},
        ),
        patch("library.document_images.replace_document_images"),
    ):
        result = DocumentProcessingService(Session(), storage, str(tmp_path)).execute(job)
    return document, result


def test_execute_success_clears_stale_download_error(tmp_path):
    document, result = _run_success(tmp_path, "ERROR", "ERROR_DOWNLOAD")

    assert result["markdown_created"] is True
    assert document.processing_status == "NEED_MANUAL_REVIEW"
    assert document.processing_error_code == "NONE"


def test_execute_success_keeps_other_status_and_error_code(tmp_path):
    for status, code in [
        ("URL_ADDED", "NONE"),
        ("NEED_MANUAL_REVIEW", "NONE"),
        ("ERROR", "TEMPORARY_ERROR"),
        ("NEED_CLEAN_MD", "ERROR_DOWNLOAD"),
    ]:
        document, _ = _run_success(tmp_path, status, code)
        assert (document.processing_status, document.processing_error_code) == (status, code)
