"""Unit tests for POST /document/<id>/promote_to_webpage (mocked session)."""

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
