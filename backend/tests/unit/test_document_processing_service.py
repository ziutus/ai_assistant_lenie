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

    def fake_extract(doc, cache_dir, **kwargs):
        Path(cache_dir, "artifact.json").write_text("{}", encoding="utf-8")
        return "RAW MARKDOWN", "ARTICLE"

    with (
        patch("library.document_processing_service.extract_article", fake_extract),
        patch("library.document_processing_service.clean_article_text", return_value={"text": "CLEAN"}),
    ):
        result = DocumentProcessingService(Session(), storage, str(tmp_path)).execute(job)

    assert result["markdown_created"] is True
    assert result["llm_extracted"] is True
    assert result["artifacts_uploaded"] == 2  # materialized HTML + fake artifact
    assert document.text_extracted == "ARTICLE"
    assert document.text_md == "CLEAN"
    assert storage.objects["cache/markdown/12/12.html"] == b"<p>HTML</p>"
