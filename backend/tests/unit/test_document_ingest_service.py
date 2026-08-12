from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.document_ingest_service import (
    DocumentIngestService,
    IngestRequest,
)
from library.document_service import ExistingDocumentError


def _service(document=None):
    session = MagicMock()
    document = document or SimpleNamespace(id=42, text_raw="<html>")
    with patch("library.document_ingest_service.DocumentService") as service_cls:
        service_cls.return_value.create_document.return_value = document
        result = DocumentIngestService(session, storage=MagicMock()).ingest(
            IngestRequest(url="https://example.test", document_type="webpage", html="<p>x</p>", text="x")
        )
    return service_cls.return_value, result


def test_create_delegates_to_document_service_and_returns_added():
    service, result = _service()

    assert result.document_id == 42
    assert result.status == "added"
    service.create_document.assert_called_once()
    assert service.create_document.call_args.kwargs["html"] == "<p>x</p>"


def test_create_without_html_does_not_report_duplicate_missing_html():
    service, result = _service(document=SimpleNamespace(id=43, text_raw=None))

    assert result.status == "added"
    assert result.missing_raw_html is False
    assert service.create_document.call_args.kwargs["url_type"] == "webpage"


def test_duplicate_is_returned_without_rethrowing():
    session = MagicMock()
    existing = SimpleNamespace(id=7, text_raw=None)
    with patch("library.document_ingest_service.DocumentService") as service_cls:
        service_cls.return_value.create_document.side_effect = ExistingDocumentError(existing)
        result = DocumentIngestService(session, storage=MagicMock()).ingest(
            IngestRequest(url="https://example.test", document_type="webpage")
        )

    assert result == result.__class__(7, "already_exists", None, True)


def test_duplicate_email_updates_captured_images():
    session = MagicMock()
    existing = SimpleNamespace(id=7, text_raw=None, document_type="email")
    with patch("library.document_ingest_service.DocumentService") as service_cls:
        service_cls.return_value.create_document.side_effect = ExistingDocumentError(existing)
        result = DocumentIngestService(session, storage=MagicMock()).ingest(
            IngestRequest(
                url="gmail://message-1", document_type="email",
                images=[{"position": 0, "url": "https://cdn.example.test/chart.png"}],
            )
        )

    assert result.status == "already_exists"
    service_cls.return_value.normalize_email_tracking_links.assert_called_once_with(existing)
    service_cls.return_value.replace_email_images.assert_called_once_with(
        7, [{"position": 0, "url": "https://cdn.example.test/chart.png"}],
    )


def test_fill_missing_passes_external_uuid_and_returns_refreshed():
    session = MagicMock()
    doc = SimpleNamespace(id=8)
    with patch("library.document_ingest_service.DocumentService") as service_cls:
        service_cls.return_value.fill_missing_source_html.return_value = doc
        result = DocumentIngestService(session, storage=MagicMock()).ingest(
            IngestRequest(
                url="https://example.test",
                document_type="webpage",
                html="<p>x</p>",
                operation="fill_missing_html",
                external_uuid="aws-uuid",
            )
        )

    assert result.status == "refreshed"
    assert service_cls.return_value.fill_missing_source_html.call_args.kwargs["external_uuid"] == "aws-uuid"


def test_invalid_operation_is_rejected_before_service_call():
    with pytest.raises(ValueError, match="Invalid operation"):
        DocumentIngestService(MagicMock(), storage=MagicMock()).ingest(
            IngestRequest(url="https://example.test", document_type="webpage", operation="bad")
        )
