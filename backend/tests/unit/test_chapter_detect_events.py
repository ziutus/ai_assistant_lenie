"""POST /document/<id>/chapter/<position>/detect_events (event proposals for one /ner chapter).

The LLM extraction itself is covered in test_timeline_events.py; here the session and
refresh_document_events are mocked and only the route contract is checked.
"""

import datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as crr  # noqa: E402
from library import timeline_events  # noqa: E402
from library.db.models import Document, DocumentEvent  # noqa: E402


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


def _row(**kw) -> DocumentEvent:
    defaults = dict(
        id=1, document_id=5, chapter_position=2, event_date=datetime.date(1939, 9, 1), event_date_end=None,
        date_precision="day", date_text="1 września 1939", description="Atak na Polskę",
        anchor_quote="1 września 1939 roku", sort_year=1939,
    )
    defaults.update(kw)
    return DocumentEvent(**defaults)


def _session(doc):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: doc if model is Document else None
    return session


def test_detects_only_the_requested_chapter_and_returns_proposals(client, monkeypatch):
    doc = Document(id=5)
    session = _session(doc)
    monkeypatch.setattr(crr, "get_scoped_session", lambda: session)
    monkeypatch.setattr(crr, "_latest_run_for_document", lambda s, d: None)
    seen = {}

    def fake_refresh(sess, document, model=None, *, chapter_position=None):
        seen.update(model=model, chapter_position=chapter_position)
        return {
            "model": "m1", "rows": [_row()],
            "chapters": [{"rejected_without_quote": 1, "rejected_without_date": 2, "invalid_json": 0}],
        }

    monkeypatch.setattr(timeline_events, "refresh_document_events", fake_refresh)

    r = client.post("/document/5/chapter/2/detect_events", json={"model": "m1"})

    body = r.get_json()
    assert r.status_code == 200
    assert seen == {"model": "m1", "chapter_position": 2}
    assert body["events"][0]["date_text"] == "1 września 1939"
    assert body["events"][0]["event_date"] == "1939-09-01"
    assert body["rejected_without_quote"] == 1 and body["rejected_without_date"] == 2
    session.commit.assert_called_once()


def test_unknown_chapter_is_a_400_and_rolls_back(client, monkeypatch):
    session = _session(Document(id=5))
    monkeypatch.setattr(crr, "get_scoped_session", lambda: session)
    monkeypatch.setattr(crr, "_latest_run_for_document", lambda s, d: None)

    def boom(*args, **kwargs):
        raise ValueError("chapter 9 not found")

    monkeypatch.setattr(timeline_events, "refresh_document_events", boom)

    r = client.post("/document/5/chapter/9/detect_events", json={})

    assert r.status_code == 400
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_model_must_be_a_string(client, monkeypatch):
    monkeypatch.setattr(crr, "get_scoped_session", lambda: _session(Document(id=5)))

    r = client.post("/document/5/chapter/1/detect_events", json={"model": 3})

    assert r.status_code == 400
