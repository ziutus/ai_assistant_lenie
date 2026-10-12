"""Decision browsing validates input and executes filtering against real SQL."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from library.db.models import NerContextClassification
from library.ner_decisions import list_decisions

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture
def client():
    import server

    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"), server.app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize("query", [
    "limit=0", "limit=201", "limit=no", "offset=-1", "offset=1.5", "document_id=0",
    "document_id=no", "entity_type=orgName", "predicted_class=bad", "confidence=bad",
    "dropped=1", "latest_only=yes",
])
def test_invalid_filters(client, query):
    with patch("server.get_scoped_session") as session:
        response = client.get(f"/ner_context_decisions?{query}", headers=API_HEADERS)
    assert response.status_code == 400
    assert "Nieprawidłowy parametr" in response.json["message"]
    session.return_value.execute.assert_not_called()


@pytest.fixture
def decisions_session():
    engine = create_engine("sqlite://")
    # Only the columns used by the read-only join are needed here.
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT, document_type TEXT)")
        connection.exec_driver_sql("INSERT INTO documents VALUES (1, 'Document', 'webpage')")
    NerContextClassification.__table__.create(engine)
    with Session(engine) as session:
        for id_, doc, name, verdict, dropped in [
            (1, 1, "Alpha", "not_place", True), (2, 1, "Alpha", "place", False),
            (3, 1, "Beta", "not_place", True), (4, None, "ALPHA%", "uncertain", False),
        ]:
            session.add(NerContextClassification(id=id_, document_id=doc, entity_type="placeName",
                        entity_text=name, predicted_class=verdict, confidence="high", dropped=dropped,
                        model="test", created_at=datetime(2026, 1, 1), rationale="Reason"))
        session.commit()
        yield session
    engine.dispose()


def test_pagination_summary_and_left_join(decisions_session):
    data = list_decisions(decisions_session, limit=2, offset=1)
    assert [row["id"] for row in data["items"]] == [3, 2]
    assert data["items"][0]["document_title"] == "Document"
    assert data["summary"] == {"total": 4, "dropped": 2,
                               "by_class": {"not_place": 2, "place": 1, "uncertain": 1}}
    assert list_decisions(decisions_session)["items"][0]["document_title"] is None
    assert list_decisions(decisions_session, offset=100)["total"] == 4


def test_latest_precedes_filters(decisions_session):
    assert list_decisions(decisions_session, latest_only=True)["total"] == 3
    data = list_decisions(decisions_session, latest_only=True, predicted_class="not_place", dropped=True)
    assert [row["id"] for row in data["items"]] == [3]
    assert data["summary"] == {"total": 1, "dropped": 1, "by_class": {"not_place": 1}}


def test_filters_and_literal_search(decisions_session):
    data = list_decisions(decisions_session, document_id=1, entity_type="placeName", confidence="high",
                          dropped=False, q="aLpH")
    assert [row["id"] for row in data["items"]] == [2]
    assert list_decisions(decisions_session, q="%")["total"] == 1
    assert list_decisions(decisions_session, entity_type="persName")["summary"]["total"] == 0


def test_endpoint(client, decisions_session):
    scoped = SimpleNamespace(execute=decisions_session.execute, remove=lambda: None)
    with patch("server.get_scoped_session", return_value=scoped):
        response = client.get("/ner_context_decisions?latest_only=true&document_id=1&limit=1&offset=1",
                              headers=API_HEADERS)
    assert response.status_code == 200
    assert response.json["status"] == "success"
    assert response.json["total"] == 2
    assert response.json["items"][0]["id"] == 2
