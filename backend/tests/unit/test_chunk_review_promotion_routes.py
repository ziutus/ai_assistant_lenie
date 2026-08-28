"""Unit tests for the link->webpage promotion HTTP routes (mocked session)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as crr  # noqa: E402
from library.document_promotion import PromotionError  # noqa: E402
from library.document_service import PromotionResult  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(crr, "get_scoped_session", lambda: session)
    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    client = app.test_client()
    client.session = session
    return client


def test_promote_success(client):
    result = PromotionResult(document_id=42, document_type="webpage",
                             processing_job_id="job-1", already_webpage=False)
    with patch("library.document_service.DocumentService.promote_link_to_webpage", return_value=result) as promote:
        resp = client.post("/document/42/promote_to_webpage", json={"html": "<p>x</p>"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["document_type"] == "webpage"
    assert body["processing_job_id"] == "job-1"
    assert body["already_webpage"] is False
    promote.assert_called_once_with(42, html="<p>x</p>")


@pytest.mark.parametrize("reason", ["paywall", "requires_login", "not_a_link", "download_failed"])
def test_promote_guard_failure_returns_409(client, reason):
    with patch(
        "library.document_service.DocumentService.promote_link_to_webpage",
        side_effect=PromotionError(reason, "nie da sie"),
    ):
        resp = client.post("/document/42/promote_to_webpage", json={})

    assert resp.status_code == 409
    assert resp.get_json()["reason"] == reason
    client.session.rollback.assert_called_once()


def test_promote_missing_document_returns_404(client):
    with patch(
        "library.document_service.DocumentService.promote_link_to_webpage",
        side_effect=ValueError("Document does not exist"),
    ):
        resp = client.post("/document/999/promote_to_webpage", json={})
    assert resp.status_code == 404


def test_promote_rejects_non_string_html(client):
    resp = client.post("/document/42/promote_to_webpage", json={"html": 123})
    assert resp.status_code == 400


def _meta_doc(**overrides):
    doc = SimpleNamespace(
        url="https://example.test/a", text_raw=None, ingested_at=None,
        title="Zapisany tytul", summary="Moj wlasny opis", byline="Ja",
        byline_method="manual", published_on=date(2026, 1, 2), published_on_method="manual",
        language="pl",
    )
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


def test_page_metadata_suggestions_downloads_when_no_stored_html(client):
    client.session.get.return_value = _meta_doc()
    parsed = SimpleNamespace(title="Tytul ze strony", summary="Opis ze strony",
                             language="en", text="tresc")
    with (
        patch("library.website.website_download_context.download_raw_html", return_value=b"<html></html>"),
        patch("library.website.website_download_context.webpage_raw_parse", return_value=parsed),
        patch("library.article_metadata.extract_article_authors", return_value=["Jan Kowalski"]),
        patch("library.article_metadata.extract_article_publication_date", return_value="2026-05-01"),
    ):
        resp = client.get("/document/42/page_metadata_suggestions")

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["source"] == "downloaded"
    assert body["suggestions"]["title"] == {"value": "Tytul ze strony", "method": "html"}
    assert body["suggestions"]["byline"]["value"] == "Jan Kowalski"
    assert body["suggestions"]["published_on"]["value"] == "2026-05-01"
    assert body["stored"]["summary"] == "Moj wlasny opis"
    client.session.commit.assert_not_called()


def test_page_metadata_suggestions_uses_stored_html(client):
    client.session.get.return_value = _meta_doc(text_raw="<html><body>hi</body></html>")
    parsed = SimpleNamespace(title="T", summary="", language="", text="")
    with (
        patch("library.website.website_download_context.download_raw_html") as dl,
        patch("library.website.website_download_context.webpage_raw_parse", return_value=parsed),
        patch("library.article_metadata.extract_article_authors", return_value=[]),
        patch("library.article_metadata.extract_article_publication_date", return_value=None),
        patch("library.article_cleaner.resolve_relative_publication_date", return_value=None),
    ):
        resp = client.get("/document/42/page_metadata_suggestions")

    assert resp.get_json()["source"] == "raw_html_stored"
    dl.assert_not_called()


def test_page_metadata_suggestions_unavailable(client):
    client.session.get.return_value = _meta_doc(url="")
    resp = client.get("/document/42/page_metadata_suggestions")
    body = resp.get_json()
    assert body["source"] == "unavailable"
    assert body["suggestions"] == {}


def test_page_metadata_suggestions_missing_doc_404(client):
    client.session.get.return_value = None
    resp = client.get("/document/999/page_metadata_suggestions")
    assert resp.status_code == 404
