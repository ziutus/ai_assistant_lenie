"""Model choice and one-chapter tone / period endpoints (chunk_review_routes.py, library/chapter_analysis_model.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import app_settings  # noqa: E402
from library import chapter_analysis_model as cam  # noqa: E402
from library import chunk_review_routes as crr  # noqa: E402
from library import llm_model_registry, time_periods, tones  # noqa: E402
from library.db.models import Document  # noqa: E402


@pytest.fixture
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(crr.bp)
    return app.test_client()


@pytest.fixture
def session(monkeypatch):
    sess = MagicMock()
    sess.get.side_effect = lambda model, pk: Document(id=5) if model is Document else None
    monkeypatch.setattr(crr, "get_scoped_session", lambda: sess)
    return sess


def _allow(monkeypatch, *allowed):
    monkeypatch.setattr(llm_model_registry, "is_selectable", lambda model, task="x": model in allowed)
    monkeypatch.setattr(
        llm_model_registry, "selectable_models",
        lambda task="x": [{"id": m, "available": True} for m in allowed],
    )


# --- the household default ---------------------------------------------------------------------------------------


def test_default_is_the_saved_choice_while_allowed(monkeypatch):
    _allow(monkeypatch, "saved-model", cam.DEFAULT_MODEL)
    monkeypatch.setattr(app_settings, "get_setting", lambda session, key: "saved-model")

    assert cam.default_model(MagicMock()) == "saved-model"


def test_default_falls_back_to_bielik_when_the_saved_model_is_gone(monkeypatch):
    _allow(monkeypatch, cam.DEFAULT_MODEL)
    monkeypatch.setattr(app_settings, "get_setting", lambda session, key: "retired-model")

    assert cam.default_model(MagicMock()) == cam.DEFAULT_MODEL


def test_default_falls_back_to_the_first_available_model(monkeypatch):
    _allow(monkeypatch, "other")
    monkeypatch.setattr(app_settings, "get_setting", lambda session, key: None)

    assert cam.default_model(MagicMock()) == "other"


def test_the_task_is_in_the_model_allowlist():
    assert cam.TASK in llm_model_registry._TASKS


def test_get_model_lists_models_and_the_default(client, session, monkeypatch):
    _allow(monkeypatch, "a", cam.DEFAULT_MODEL)
    monkeypatch.setattr(app_settings, "get_setting", lambda s, key: None)

    body = client.get("/chapter_analysis/model").get_json()

    assert body["default_model"] == cam.DEFAULT_MODEL
    assert body["saved"] is False
    assert {m["id"] for m in body["models"]} == {"a", cam.DEFAULT_MODEL}


def test_put_model_stores_it_and_rejects_an_unknown_one(client, session, monkeypatch):
    _allow(monkeypatch, "a", cam.DEFAULT_MODEL)
    stored = {}
    monkeypatch.setattr(app_settings, "set_setting", lambda s, key, value: stored.update({key: value}))
    monkeypatch.setattr(app_settings, "get_setting", lambda s, key: stored.get(key))

    ok = client.put("/chapter_analysis/model", json={"model": "a"})
    bad = client.put("/chapter_analysis/model", json={"model": "nope"})
    missing = client.put("/chapter_analysis/model", json={})
    cleared = client.put("/chapter_analysis/model", json={"model": None})

    assert ok.status_code == 200 and ok.get_json()["default_model"] == "a" and ok.get_json()["saved"] is True
    assert stored[cam.SETTING_KEY] is None  # the last call cleared it
    assert bad.status_code == 400
    assert missing.status_code == 400
    assert cleared.get_json()["saved"] is False


# --- one chapter -------------------------------------------------------------------------------------------------


def test_detect_tone_runs_one_chapter_with_the_chosen_model(client, session, monkeypatch):
    _allow(monkeypatch, "picked", cam.DEFAULT_MODEL)
    seen = {}

    def fake_refresh(sess, doc, model=None, *, chapter_position=None, keep_previous_on_failure=False):
        seen.update(model=model, chapter_position=chapter_position, keep=keep_previous_on_failure)
        return {
            "model": model, "rows": [object()],
            "tones": [{"chapter_position": 3, "emotion": "smutny", "sentiment": "negatywne", "intensity": "wysoka",
                       "secondary_emotions": None, "registers": None, "evidence": "e"}],
            "chapters": [{"chapter_position": 3, "chapter_title": "T", "tones": 1, "fragments": 2,
                          "fragments_skipped": 0, "usage_log_ids": [1], "llm_cost_amount": "0.1"}],
        }

    monkeypatch.setattr(tones, "refresh_document_tones", fake_refresh)

    r = client.post("/document/5/chapter/3/detect_tone", json={"model": "picked"})

    body = r.get_json()
    assert r.status_code == 200
    assert seen == {"model": "picked", "chapter_position": 3, "keep": True}
    assert body["tones"][0]["emotion"] == "smutny"
    assert body["kept_previous"] is False
    assert body["report"]["fragments"] == 2
    assert "usage_log_ids" not in body["report"] and "chapter_title" not in body["report"]
    session.commit.assert_called_once()


def test_detect_tone_without_a_model_uses_the_household_default(client, session, monkeypatch):
    seen = {}
    monkeypatch.setattr(cam, "default_model", lambda s: "household")
    monkeypatch.setattr(
        tones, "refresh_document_tones",
        lambda sess, doc, model=None, **kw: seen.update(model=model) or {"model": model, "tones": [], "chapters": []},
    )

    assert client.post("/document/5/chapter/1/detect_tone", json={}).status_code == 200
    assert seen["model"] == "household"


def test_detect_time_period_returns_periods_under_time_periods(client, session, monkeypatch):
    _allow(monkeypatch, "picked")
    monkeypatch.setattr(
        time_periods, "refresh_document_periods",
        lambda *a, **k: {
            "model": "picked", "rows": [], "kept_previous": True,
            "periods": [{"chapter_position": 2, "position": 0, "subject_period_label": "A"}],
            "chapters": [{"invalid_json": 1}],
        },
    )

    body = client.post("/document/5/chapter/2/detect_time_period", json={"model": "picked"}).get_json()

    assert body["time_periods"][0]["subject_period_label"] == "A"
    assert body["kept_previous"] is True


@pytest.mark.parametrize("path", ["detect_tone", "detect_time_period"])
def test_a_model_outside_the_allowlist_is_refused(client, session, monkeypatch, path):
    _allow(monkeypatch, "ok")

    r = client.post(f"/document/5/chapter/1/{path}", json={"model": "arbitrary/provider-model"})

    assert r.status_code == 400
    session.commit.assert_not_called()


@pytest.mark.parametrize("path", ["detect_tone", "detect_time_period"])
def test_model_must_be_a_string(client, session, path):
    assert client.post(f"/document/5/chapter/1/{path}", json={"model": 7}).status_code == 400


@pytest.mark.parametrize(("path", "module", "func"), [
    ("detect_tone", tones, "refresh_document_tones"),
    ("detect_time_period", time_periods, "refresh_document_periods"),
])
def test_unknown_chapter_is_a_400_and_rolls_back(client, session, monkeypatch, path, module, func):
    monkeypatch.setattr(cam, "default_model", lambda s: None)

    def boom(*args, **kwargs):
        raise ValueError("chapter 9 not found")

    monkeypatch.setattr(module, func, boom)

    r = client.post(f"/document/5/chapter/9/{path}", json={})

    assert r.status_code == 400
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_unknown_document_is_a_404(client, monkeypatch):
    sess = MagicMock()
    sess.get.return_value = None
    monkeypatch.setattr(crr, "get_scoped_session", lambda: sess)

    assert client.post("/document/5/chapter/1/detect_tone", json={}).status_code == 404


def test_refresh_keeps_the_stored_tone_when_the_model_failed(monkeypatch):
    sess = MagicMock()
    monkeypatch.setattr(tones, "extract_document_tones", lambda *a, **k: {"model": "m", "tones": [], "chapters": []})

    result = tones.refresh_document_tones(sess, SimpleNamespace(id=1), chapter_position=4, keep_previous_on_failure=True)

    assert result["kept_previous"] is True
    sess.execute.assert_not_called()
