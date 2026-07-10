import types
from unittest.mock import MagicMock

import pytest

from src import main


@pytest.fixture
def client(monkeypatch):
    fake_ent = types.SimpleNamespace(
        text="Donald Tusk", label_="persName", lemma_="Donald Tusk", start_char=0, end_char=11,
    )
    fake_doc = types.SimpleNamespace(ents=[fake_ent])
    monkeypatch.setattr(main, "get_nlp", lambda: MagicMock(return_value=fake_doc))
    main.app.testing = True
    return main.app.test_client()


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_ner_returns_entities(client):
    resp = client.post("/ner", json={"text": "Donald Tusk"})
    assert resp.status_code == 200
    assert resp.get_json() == {
        "entities": [
            {"text": "Donald Tusk", "label": "persName", "lemma": "Donald Tusk", "start": 0, "end": 11}
        ]
    }


def test_ner_requires_text(client):
    resp = client.post("/ner", json={})
    assert resp.status_code == 400


def test_ner_requires_nonempty_text(client):
    resp = client.post("/ner", json={"text": ""})
    assert resp.status_code == 400
