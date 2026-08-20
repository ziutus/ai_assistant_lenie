"""Contract tests for GET /document/<id>/relationship_graph."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    import server

    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as test_client:
            yield test_client


def test_relationship_graph_returns_only_stored_links(client):
    organization = SimpleNamespace(id=31, canonical_name="The Telegraph",)
    source = SimpleNamespace(
        id=12, canonical_name="The Telegraph", organization_id=31,
        organization=organization,
    )
    provenance = SimpleNamespace(id=51, role="original_reporting", source=source, source_url=None)
    cited = SimpleNamespace(id=8, title="Badanie", doi="10.1/example", pmid=None, pmcid=None,
                            canonical_url="https://example.test/paper")
    citation = SimpleNamespace(id=61)
    document_organization = SimpleNamespace(id=71)
    publisher = SimpleNamespace(id=4, canonical_name="gazeta.pl")
    document = SimpleNamespace(id=9377, title="Artykuł", publisher=publisher)
    session = MagicMock()
    session.get.return_value = document
    # Source-chain relations are queried before direct provenance links.
    session.scalars.side_effect = [
        MagicMock(all=lambda: []),
        MagicMock(all=lambda: [provenance]),
    ]
    session.execute.side_effect = [
        MagicMock(all=lambda: [(citation, cited)]),
        MagicMock(all=lambda: [(document_organization, organization)]),
    ]

    with patch("server.get_scoped_session", return_value=session):
        response = client.get("/document/9377/relationship_graph", headers=API_HEADERS)

    assert response.status_code == 200
    graph = response.get_json()
    assert graph["status"] == "success"
    assert {node["id"] for node in graph["nodes"]} == {
        "publisher:4", "organization:31", "cited_publication:8",
    }
    assert {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]} == {
        ("publisher:4", "organization:31", "original_reporting"),
        ("publisher:4", "cited_publication:8", "cited_publication"),
    }


def test_relationship_graph_returns_404_for_unknown_document(client):
    session = MagicMock()
    session.get.return_value = None
    with patch("server.get_scoped_session", return_value=session):
        response = client.get("/document/999999/relationship_graph", headers=API_HEADERS)

    assert response.status_code == 404
    assert response.get_json()["message"] == "Document not found"
