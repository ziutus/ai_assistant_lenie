"""Persistence and HTTP contract of country detection audits."""

from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from library.country_detection_audit import list_detections, record_detection
from library.db.models import CountryDetectionRun, CountryTagDecision, Document


@pytest.fixture
def client():
    import server

    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as client:
            yield client


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    # The document model uses PostgreSQL-only types; keep real column names for ORM reads.
    with engine.begin() as conn:
        columns = ["id INTEGER PRIMARY KEY"] + [f'"{c.name}"' for c in Document.__table__.columns if c.name != "id"]
        conn.execute(text(f"CREATE TABLE documents ({', '.join(columns)})"))
        conn.execute(text("INSERT INTO documents (id, tags) VALUES (42, 'topic')"))
    CountryDetectionRun.__table__.create(engine)
    CountryTagDecision.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def audit():
    return dict(text_chars=500, threshold=5,
                llm=dict(model="model", prompt="full prompt\n", response="  Mars\n", usage_log_id=7,
                         error=None, called=True),
                decisions=[dict(slug="haiti", name_pl="Haiti", mention_count=5,
                                decision="auto_threshold", snippets=["Haiti."])])


def save(session, audit, **kwargs):
    return record_detection(session, 42, audit, trigger="detect_button", text_source="document", **kwargs)


def test_roundtrip_order_and_limit(session, audit):
    first = save(session, audit, tags_before="topic", tags_added=["haiti"], analysis_run_id=91)
    second = save(session, audit)
    rows = list_detections(session, 42)
    assert [r["id"] for r in rows] == [second, first]
    assert rows[1]["tags_added"] == ["haiti"]
    assert rows[1]["analysis_run_id"] == 91
    assert rows[0]["llm_prompt"] == audit["llm"]["prompt"]
    assert rows[0]["llm_response"] == audit["llm"]["response"]
    assert rows[0]["decisions"][0]["country_slug"] == "haiti"
    assert len(list_detections(session, 42, limit=1)) == 1
    assert list_detections(session, 999) == []


def test_failed_decision_rolls_back_run_but_preserves_tag_update(session, audit):
    # Start an outer write transaction, then trigger a real NOT NULL failure within the savepoint.
    session.execute(text("UPDATE documents SET tags='topic,kraj-haiti' WHERE id=42"))
    broken = deepcopy(audit)
    broken["decisions"][0]["decision"] = None
    assert save(session, broken) is None
    assert session.scalars(select(CountryDetectionRun)).all() == []
    session.commit()
    assert session.scalar(text("SELECT tags FROM documents WHERE id=42")) == "topic,kraj-haiti"
    assert save(session, audit) is not None


def test_record_does_not_commit(session, audit):
    session.execute(text("UPDATE documents SET tags='changed' WHERE id=42"))
    assert save(session, audit) is not None
    session.rollback()
    assert session.scalars(select(CountryDetectionRun)).all() == []
    assert session.scalar(text("SELECT tags FROM documents WHERE id=42")) == "topic"


def test_detect_document_persists_audit(session, monkeypatch):
    from library.document_countries import detect_document_countries

    doc = SimpleNamespace(id=42, title="", text_md=None, text="Haiti. " * 5, tags="topic")
    monkeypatch.setattr(Document, "get_by_id", lambda *a: doc)
    monkeypatch.setattr("library.entity_service.apply_channel_glossary_text", lambda s, i, t: t)
    result = detect_document_countries(session, 42)
    assert result["added"] == ["haiti"]
    row = list_detections(session, 42)[0]
    assert row["id"] == result["detection_id"]
    assert row["tags_before"] == "topic"
    assert row["tags_added"] == ["haiti"]
    assert row["trigger"] == "detect_button"


def test_apply_tags_audits_empty_results(session, monkeypatch):
    from library.document_analysis_service import _apply_tags

    doc = Document(id=42, title="", tags="topic")
    monkeypatch.setattr("sqlalchemy.orm.object_session", lambda d: session)
    monkeypatch.setattr("library.entity_service.apply_channel_glossary_text", lambda s, i, t: t)
    monkeypatch.setattr("library.article_tagging.tag_article_with_llm", lambda *a: [])
    monkeypatch.setattr("library.article_tagging._tagging_model", lambda: "model")
    monkeypatch.setattr("library.ai.ai_ask", lambda *a, **kw: SimpleNamespace(response_text=""))
    _apply_tags(doc, "Polska.")
    row = list_detections(session, 42)[0]
    assert row["trigger"] == "analysis_run"
    assert row["text_source"] == "synthesis"
    assert row["tags_added"] == []
    assert row["decisions"][0]["decision"] == "llm_rejected"
    assert doc.tags == "topic"


def test_endpoint_full_exchange_and_missing_document(client, session, audit, monkeypatch):
    save(session, audit)
    monkeypatch.setattr(session, "remove", lambda: None, raising=False)
    monkeypatch.setattr("server.get_scoped_session", lambda: session)
    monkeypatch.setattr(Document, "get_by_id", lambda s, i: SimpleNamespace(id=i) if i == 42 else None)
    headers = {"x-api-key": "test-api-key"}
    response = client.get("/document/42/country_detections?limit=1", headers=headers)
    assert response.status_code == 200
    row = response.get_json()["detections"][0]
    assert row["llm_prompt"] == audit["llm"]["prompt"]
    assert row["llm_response"] == audit["llm"]["response"]
    assert client.get("/document/99/country_detections", headers=headers).status_code == 404
    for limit in ("0", "-1", "abc"):
        assert client.get(f"/document/42/country_detections?limit={limit}", headers=headers).status_code == 400
