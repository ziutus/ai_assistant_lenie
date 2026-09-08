"""Contract tests for the document-links blueprint (mocked sessions)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import flask
import pytest

pytest.importorskip("sqlalchemy")

import library.document_links_routes as routes
from library.db.models import DocumentLink


@pytest.fixture()
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(routes.bp)
    app.config["TESTING"] = True
    return app.test_client()


def _doc(doc_id):
    return SimpleNamespace(
        id=doc_id, title=f"Doc {doc_id}", url=f"https://x.test/{doc_id}",
        document_type="link", byline=None, published_on=None,
    )


def test_get_links_404_for_unknown_document(client):
    session = MagicMock()
    session.get.return_value = None
    with patch.object(routes, "get_scoped_session", return_value=session):
        response = client.get("/document/999/links")
    assert response.status_code == 404


def test_get_links_returns_vocabulary_and_links(client):
    session = MagicMock()
    session.get.return_value = _doc(10474)
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "list_document_links", return_value=[{"id": 1}]):
            response = client.get("/document/10474/links")
    body = response.get_json()
    assert response.status_code == 200
    assert body["links"] == [{"id": 1}]
    assert any(r["value"] == "discusses" for r in body["relations"])


def test_post_link_creates_edge(client):
    session = MagicMock()
    session.get.return_value = _doc(10477)
    fake_link = DocumentLink(
        id=7, from_document_id=10477, to_document_id=10474, relation="discusses",
        status="confirmed", detection_method="manual",
    )
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "create_link", return_value=fake_link) as create:
            response = client.post(
                "/document/10477/links",
                json={"to_document_id": 10474, "relation": "discusses", "note": "o tym repo"},
            )
    assert response.status_code == 201
    args, kwargs = create.call_args
    assert kwargs["from_document_id"] == 10477
    assert kwargs["to_document_id"] == 10474
    assert kwargs["relation"] == "discusses"


def test_post_link_incoming_direction_swaps_endpoints(client):
    session = MagicMock()
    session.get.return_value = _doc(10474)
    fake_link = DocumentLink(id=8, from_document_id=10477, to_document_id=10474, relation="discusses")
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "create_link", return_value=fake_link) as create:
            response = client.post(
                "/document/10474/links",
                json={"to_document_id": 10477, "relation": "discusses", "direction": "incoming"},
            )
    assert response.status_code == 201
    _, kwargs = create.call_args
    assert kwargs["from_document_id"] == 10477
    assert kwargs["to_document_id"] == 10474


def test_post_link_rejects_non_integer_target(client):
    session = MagicMock()
    session.get.return_value = _doc(1)
    with patch.object(routes, "get_scoped_session", return_value=session):
        response = client.post("/document/1/links", json={"to_document_id": "two", "relation": "related"})
    assert response.status_code == 400


def test_post_link_maps_domain_error_to_400(client):
    session = MagicMock()
    session.get.return_value = _doc(1)
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "create_link", side_effect=routes.DocumentLinkError("nope")):
            response = client.post("/document/1/links", json={"to_document_id": 2, "relation": "related"})
    assert response.status_code == 400
    assert response.get_json()["message"] == "nope"


def test_patch_link_sets_status(client):
    session = MagicMock()
    link = DocumentLink(id=3, from_document_id=1, to_document_id=2, relation="references", status="proposed")
    session.get.return_value = link
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "set_link_status") as setter:
            response = client.patch("/document_links/3", json={"status": "confirmed"})
    assert response.status_code == 200
    setter.assert_called_once()


def test_patch_link_404(client):
    session = MagicMock()
    session.get.return_value = None
    with patch.object(routes, "get_scoped_session", return_value=session):
        response = client.patch("/document_links/3", json={"status": "confirmed"})
    assert response.status_code == 404


def test_delete_link(client):
    session = MagicMock()
    session.get.return_value = DocumentLink(id=3, from_document_id=1, to_document_id=2, relation="related")
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "delete_link") as remover:
            response = client.delete("/document_links/3")
    assert response.status_code == 200
    remover.assert_called_once()


def test_detect_endpoint_returns_created(client):
    session = MagicMock()
    created = [DocumentLink(id=9, from_document_id=10477, to_document_id=10474, relation="references",
                            status="proposed", detection_method="url_mention")]
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "detect_url_mention_links", return_value=created):
            response = client.post("/document/10477/links/detect")
    body = response.get_json()
    assert response.status_code == 200
    assert body["created_count"] == 1
