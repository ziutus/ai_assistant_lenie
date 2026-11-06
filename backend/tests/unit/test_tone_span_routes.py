"""REST for the on-demand tone passages (library/tone_span_routes.py)."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chapter_analysis_model as cam  # noqa: E402
from library import llm_model_registry, tone_span_routes, tone_spans  # noqa: E402
from library.db.models import Document, DocumentToneSpan  # noqa: E402

CHAPTERED = "## Pierwszy\n\ntekst pierwszego rozdziału\n\n## Drugi\n\ntekst drugiego rozdziału"


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(tone_span_routes.bp)
    return app.test_client()


@pytest.fixture
def session(monkeypatch):
    sess = MagicMock()
    sess.get.side_effect = lambda model, pk: Document(id=5, text_md=CHAPTERED) if model is Document else None
    monkeypatch.setattr(tone_span_routes, "get_scoped_session", lambda: sess)
    return sess


def _row(**kw) -> DocumentToneSpan:
    defaults = dict(id=1, document_id=5, chapter_position=2, role="outlier", label="złośliwy",
                    quote="Cytat złośliwego komentarza w tekście.", note="powód", importance=None,
                    status="proposed", model="m")
    defaults.update(kw)
    return DocumentToneSpan(**defaults)


def _allow(monkeypatch, *allowed):
    monkeypatch.setattr(llm_model_registry, "is_selectable", lambda model, task="x": model in allowed)


def test_list_returns_every_stored_passage_with_its_status(client, session):
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = [_row(), _row(id=2, status="rejected")]
    session.query.return_value = query

    body = client.get("/document/5/tone_spans").get_json()

    assert [s["status"] for s in body["spans"]] == ["proposed", "rejected"]
    assert body["spans"][0]["quote"].startswith("Cytat")


def test_list_of_an_unknown_document_is_a_404(client, monkeypatch):
    sess = MagicMock()
    sess.get.return_value = None
    monkeypatch.setattr(tone_span_routes, "get_scoped_session", lambda: sess)

    assert client.get("/document/5/tone_spans").status_code == 404


def test_detect_runs_one_chapter_on_request_with_the_chosen_model(client, session, monkeypatch):
    _allow(monkeypatch, "picked")
    seen = {}

    def fake_refresh(sess, doc, model, *, chapter_position=None):
        seen.update(model=model, chapter_position=chapter_position)
        return {"all": [_row()], "rows": [], "chapters": [{"chapter_position": 2, "fragments": 2, "chapter_title": "x",
                                                            "usage_log_ids": [1], "rejected_no_quote": 1}]}

    monkeypatch.setattr(tone_spans, "refresh_document_tone_spans", fake_refresh)

    r = client.post("/document/5/chapter/2/detect_tone_spans", json={"model": "picked"})

    body = r.get_json()
    assert r.status_code == 200
    assert seen == {"model": "picked", "chapter_position": 2}
    assert body["spans"][0]["label"] == "złośliwy"
    assert body["report"] == {"chapter_position": 2, "fragments": 2, "rejected_no_quote": 1}
    session.commit.assert_called_once()


def test_detect_without_a_model_uses_the_household_default(client, session, monkeypatch):
    seen = {}
    monkeypatch.setattr(cam, "default_model", lambda s: "household")
    monkeypatch.setattr(
        tone_spans, "refresh_document_tone_spans",
        lambda sess, doc, model, **kw: seen.update(model=model) or {"all": [], "chapters": []},
    )

    assert client.post("/document/5/chapter/1/detect_tone_spans", json={}).status_code == 200
    assert seen["model"] == "household"


def test_an_article_without_headings_is_one_whole_document_unit(client, monkeypatch):
    sess = MagicMock()
    sess.get.side_effect = lambda model, pk: Document(id=5, text_md="Artykuł bez nagłówków.")
    monkeypatch.setattr(tone_span_routes, "get_scoped_session", lambda: sess)
    monkeypatch.setattr(cam, "default_model", lambda s: "m")
    seen = {}
    monkeypatch.setattr(
        tone_spans, "refresh_document_tone_spans",
        lambda session, doc, model, **kw: seen.update(**kw) or {"all": [], "chapters": []},
    )

    assert client.post("/document/5/chapter/1/detect_tone_spans", json={}).status_code == 200
    assert seen["chapter_position"] is None


def test_whole_document_reads_every_chapter_of_a_short_article(client, session, monkeypatch):
    """The reader shows a short article with several ## headings as one chapter, so it must be analysed as one."""
    monkeypatch.setattr(cam, "default_model", lambda s: "m")
    seen = {}
    monkeypatch.setattr(
        tone_spans, "refresh_document_tone_spans",
        lambda sess, doc, model, **kw: seen.update(**kw) or {"all": [], "chapters": []},
    )

    assert client.post("/document/5/chapter/1/detect_tone_spans", json={"whole_document": True}).status_code == 200
    assert seen["chapter_position"] is None


def test_a_model_outside_the_allowlist_is_refused(client, session, monkeypatch):
    _allow(monkeypatch, "ok")

    r = client.post("/document/5/chapter/1/detect_tone_spans", json={"model": "arbitrary/model"})

    assert r.status_code == 400
    session.commit.assert_not_called()


def test_model_must_be_a_string(client, session):
    assert client.post("/document/5/chapter/1/detect_tone_spans", json={"model": 3}).status_code == 400


def test_unknown_chapter_is_a_400_and_rolls_back(client, session, monkeypatch):
    monkeypatch.setattr(cam, "default_model", lambda s: "m")

    def boom(*args, **kwargs):
        raise ValueError("chapter 9 not found")

    monkeypatch.setattr(tone_spans, "refresh_document_tone_spans", boom)

    r = client.post("/document/5/chapter/9/detect_tone_spans", json={})

    assert r.status_code == 400
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


@pytest.mark.parametrize("status", ["confirmed", "rejected", "proposed"])
def test_review_stores_the_decision(client, session, status):
    row = _row()
    session.get.side_effect = lambda model, pk: row

    r = client.patch("/tone_spans/1", json={"status": status})

    assert r.status_code == 200
    assert row.status == status
    session.commit.assert_called_once()


def test_review_rejects_an_unknown_status_and_an_unknown_span(client, session):
    assert client.patch("/tone_spans/1", json={"status": "maybe"}).status_code == 400
    session.get.side_effect = lambda model, pk: None
    assert client.patch("/tone_spans/1", json={"status": "confirmed"}).status_code == 404


def test_core_tone_never_echoes_the_text_of_an_unexpected_error(client, session, monkeypatch):
    monkeypatch.setattr(cam, "default_model", lambda s: "m")

    def boom(*args, **kwargs):
        raise ValueError("internal detail: /srv/secret/path")

    monkeypatch.setattr(tone_spans, "recompute_core_tone", boom)

    r = client.post("/document/5/chapter/2/core_tone", json={})

    assert r.status_code == 400
    assert "secret" not in r.get_data(as_text=True)
    session.rollback.assert_called_once()


def test_core_tone_is_stored_and_returned(client, session, monkeypatch):
    monkeypatch.setattr(cam, "default_model", lambda s: "m")
    monkeypatch.setattr(
        tone_spans, "recompute_core_tone",
        lambda sess, doc, model, **kw: {"core_tone": {"emotion": "neutralny"}, "report": {"fragments": 1}},
    )

    r = client.post("/document/5/chapter/2/core_tone", json={})

    assert r.status_code == 200
    assert r.get_json()["core_tone"] == {"emotion": "neutralny"}
    session.commit.assert_called_once()


@pytest.mark.parametrize(("code", "status"), [
    ("no_outliers", 409), ("no_tone", 409), ("text_too_short", 409), ("failed", 502),
])
def test_core_tone_explains_why_it_cannot_be_computed(client, session, monkeypatch, code, status):
    monkeypatch.setattr(cam, "default_model", lambda s: "m")

    def boom(*args, **kwargs):
        raise ValueError(code)

    monkeypatch.setattr(tone_spans, "recompute_core_tone", boom)

    r = client.post("/document/5/chapter/2/core_tone", json={})

    assert r.status_code == status
    assert r.get_json()["code"] == code
    session.rollback.assert_called_once()
