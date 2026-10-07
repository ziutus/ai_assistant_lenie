"""Unit tests for the single-speaker (monologue) marking.

Covers the byline helpers in chunk_llm_analysis, the prompt context wording and
POST /analysis_run/<id>/set_monologue_speaker. DB access is mocked.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as crr  # noqa: E402
from library.chunk_llm_analysis import (  # noqa: E402
    is_monologue, monologue_speaker_from_byline, speakers_context,
)
from library.db.models import Document, DocumentAnalysisRun  # noqa: E402


class TestMonologueSpeakerFromByline:
    def test_takes_first_byline_entry(self):
        assert monologue_speaker_from_byline("Jan Kowalski, Anna Nowak") == [
            {"name": "Jan Kowalski", "role": "autor", "description": "monolog"},
        ]

    @pytest.mark.parametrize("byline", [None, "", "   ", " , "])
    def test_empty_byline_gives_no_speaker(self, byline):
        assert monologue_speaker_from_byline(byline) == []

    def test_explicit_name_overrides_byline(self):
        assert monologue_speaker_from_byline("Kanał", name=" Jan ")[0]["name"] == "Jan"

    def test_explicit_name_without_byline(self):
        assert monologue_speaker_from_byline(None, name="Jan")[0]["name"] == "Jan"


class TestSpeakersContext:
    def test_no_speakers(self):
        assert speakers_context([]) == ""
        assert speakers_context(None) == ""

    def test_monologue_wording(self):
        ctx = speakers_context([{"name": "Jan", "role": "autor"}])
        assert "monolog" in ctx and "Jan (autor)" in ctx
        assert "Uczestnicy" not in ctx

    def test_conversation_wording(self):
        ctx = speakers_context([{"name": "A", "role": "prowadzący"}, {"name": "B"}])
        assert ctx == "Uczestnicy rozmowy: A (prowadzący), B.\n"

    def test_is_monologue(self):
        assert is_monologue([{"name": "A"}])
        assert not is_monologue([{"name": "A"}, {"name": "B"}])
        assert not is_monologue([])


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


def _session(run, doc):
    session = MagicMock()

    def _get(model, pk):
        if model is DocumentAnalysisRun:
            return run
        if model is Document:
            return doc
        return None

    session.get.side_effect = _get
    return session


class TestSetMonologueEndpoint:
    def test_sets_author_from_byline(self, client, monkeypatch):
        run = SimpleNamespace(id=5, document_id=9, speakers=[])
        session = _session(run, SimpleNamespace(byline="Jan Kowalski, X"))
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        r = client.post("/analysis_run/5/set_monologue_speaker")

        assert r.status_code == 200
        assert r.get_json()["speakers"][0]["name"] == "Jan Kowalski"
        assert run.speakers[0]["role"] == "autor"
        session.commit.assert_called_once()

    def test_body_name_overrides_byline(self, client, monkeypatch):
        run = SimpleNamespace(id=5, document_id=9, speakers=[])
        session = _session(run, SimpleNamespace(byline=None))
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        r = client.post("/analysis_run/5/set_monologue_speaker", json={"name": "Anna"})

        assert r.status_code == 200
        assert run.speakers[0]["name"] == "Anna"

    def test_400_without_byline_or_name(self, client, monkeypatch):
        run = SimpleNamespace(id=5, document_id=9, speakers=[])
        session = _session(run, SimpleNamespace(byline=""))
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        r = client.post("/analysis_run/5/set_monologue_speaker")

        assert r.status_code == 400
        assert run.speakers == []
        session.commit.assert_not_called()

    def test_404_for_unknown_run(self, client, monkeypatch):
        session = _session(None, None)
        monkeypatch.setattr(crr, "get_scoped_session", lambda: session)

        assert client.post("/analysis_run/5/set_monologue_speaker").status_code == 404
