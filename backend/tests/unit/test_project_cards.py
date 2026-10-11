"""Tests for project cards: import normalization, validation, age filter and REST contract."""

from unittest.mock import MagicMock, patch

import flask
import pytest

pytest.importorskip("sqlalchemy")

import library.project_card_routes as routes
from library.db.models import ProjectCard
from library.project_cards import (
    ProjectCardError,
    age_fit,
    card_to_dict,
    group_label,
    normalize_import_card,
    upsert_cards,
    validate_fields,
)


def _raw(**overrides):
    raw = {
        "number": "001",
        "file": "001 - Magiczna Waga z Kartonu.pdf",
        "flags": [],
        "group_raw": "DŹWIGNIEIKOŁYSKI",
        "title": "Magiczna Waga z Kartonu",
        "age_min": 5,
        "age_max": 9,
        "time_min": 30,
        "time_max": 30,
        "difficulty": 1,
        "needs_adult": True,
        "materials": [{"qty": "1", "name": "Taśma klejąca"}],
        "tools": ["nożyczki"],
        "steps": ["Zrób dwa otwory."],
        "troubleshooting": [{"problem": "Nie działa", "solution": "Sprawdź."}],
        "variants": ["Udekoruj wagę."],
        "safety": "Potrzebny dorosły.",
    }
    raw.update(overrides)
    return raw


def _card(**overrides):
    values = {"id": 1, "series": "S", "number": 1, "title": "T", "age_min": 6, "age_max": 10,
              "review_status": "imported"}
    values.update(overrides)
    return ProjectCard(**values)


@pytest.fixture()
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(routes.bp)
    app.config["TESTING"] = True
    return app.test_client()


def test_normalize_import_card_maps_group_and_number():
    card = normalize_import_card(_raw())
    assert card["number"] == 1
    assert card["series"] == "Niesamowite Maszyny"
    assert card["group_name"] == "Dźwignie i kołyski"
    assert card["review_status"] == "imported"
    assert card["source_file"].startswith("001 - ")


def test_normalize_import_card_flags_mark_needs_review():
    card = normalize_import_card(_raw(flags=["step_uses_unlisted:silnik"]))
    assert card["review_status"] == "needs_review"
    assert card["import_flags"] == ["step_uses_unlisted:silnik"]


def test_normalize_import_card_keeps_reviewed_status_and_extra_fields():
    card = normalize_import_card(_raw(review_status="reviewed", what_child_does=["Wkłada przedmioty"]))
    assert card["review_status"] == "reviewed"
    assert card["what_child_does"] == ["Wkłada przedmioty"]


@pytest.mark.parametrize("bad", [{"number": "x"}, {"title": ""}, {"age_min": 12, "age_max": 5}, {"difficulty": 4}])
def test_normalize_import_card_rejects_invalid(bad):
    with pytest.raises(ProjectCardError):
        normalize_import_card(_raw(**bad))


def test_validate_fields_rejects_unknown_and_wrong_types():
    with pytest.raises(ProjectCardError):
        validate_fields({"id": 5})
    with pytest.raises(ProjectCardError):
        validate_fields({"needs_adult": "yes"})
    with pytest.raises(ProjectCardError):
        validate_fields({"tools": "nożyczki"})
    with pytest.raises(ProjectCardError):
        validate_fields({"review_status": "done"})
    with pytest.raises(ProjectCardError):
        validate_fields({"materials": [{"qty": "1"}]})


def test_age_fit_ok_stretch_and_none():
    card = _card(age_min=6, age_max=10)
    assert age_fit(card, 7) == "ok"
    assert age_fit(card, 5) is None
    assert age_fit(card, 5, stretch=1) == "stretch"
    assert age_fit(card, 4, stretch=1) is None
    assert age_fit(_card(age_min=None, age_max=None), 5) is None


def test_group_label_known_and_unknown():
    assert group_label("BLOCZKIIDŹWIGI") == "Bloczki i dźwigi"
    assert group_label("COŚ NOWEGO") == "COŚ NOWEGO"
    assert group_label(None) is None


def test_card_to_dict_summary_vs_detail():
    card = _card(steps=["a"], materials=[])
    assert "steps" not in card_to_dict(card)
    assert card_to_dict(card, detail=True)["steps"] == ["a"]
    assert card_to_dict(card, age=7)["age_fit"] == "ok"


def _session_returning(existing):
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = existing
    return session


def test_upsert_creates_new_card():
    session = _session_returning(None)
    result = upsert_cards(session, [_raw()])
    assert result.as_dict() == {"created": 1, "updated": 0, "kept_reviewed": 0}
    added = session.add.call_args[0][0]
    assert added.title == "Magiczna Waga z Kartonu"
    session.commit.assert_called_once()


def test_upsert_does_not_overwrite_reviewed_card_with_unreviewed_import():
    existing = _card(title="Poprawiony tytuł", review_status="reviewed")
    result = upsert_cards(_session_returning(existing), [_raw()])
    assert result.kept_reviewed == 1
    assert existing.title == "Poprawiony tytuł"


def test_upsert_reviewed_import_replaces_reviewed_card():
    existing = _card(title="Stary", review_status="reviewed")
    result = upsert_cards(_session_returning(existing), [_raw(review_status="reviewed")])
    assert result.updated == 1
    assert existing.title == "Magiczna Waga z Kartonu"


def test_get_list_passes_filters_and_returns_age_fit(client):
    session = MagicMock()
    with patch.object(routes, "get_scoped_session", return_value=session), \
            patch.object(routes, "list_cards", return_value=([_card()], 61)) as list_cards, \
            patch.object(routes, "group_counts", return_value=[{"name": "G", "count": 1}]):
        response = client.get("/project_cards?age=7&stretch=1&max_difficulty=2&needs_adult=true&q=waga&limit=25&offset=50")
    body = response.get_json()
    assert response.status_code == 200
    assert body["cards"][0]["age_fit"] == "ok"
    assert body["groups"] == [{"name": "G", "count": 1}]
    assert body["total"] == 61 and body["limit"] == 25 and body["offset"] == 50
    kwargs = list_cards.call_args.kwargs
    assert kwargs["age"] == 7 and kwargs["stretch"] == 1 and kwargs["max_difficulty"] == 2
    assert kwargs["needs_adult"] is True and kwargs["query"] == "waga"
    assert kwargs["limit"] == 25 and kwargs["offset"] == 50


@pytest.mark.parametrize("query", ["age=abc", "age=40", "max_difficulty=9", "review_status=nope", "needs_adult=maybe", "limit=0", "limit=500"])
def test_get_list_rejects_bad_params(client, query):
    with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
        response = client.get(f"/project_cards?{query}")
    assert response.status_code == 400


def test_get_card_404_and_detail(client):
    session = MagicMock()
    session.get.return_value = None
    with patch.object(routes, "get_scoped_session", return_value=session):
        assert client.get("/project_cards/9").status_code == 404
    session.get.return_value = _card(steps=["x"])
    with patch.object(routes, "get_scoped_session", return_value=session):
        response = client.get("/project_cards/1")
    assert response.get_json()["card"]["steps"] == ["x"]


def test_patch_updates_and_validates(client):
    session = MagicMock()
    card = _card()
    session.get.return_value = card
    with patch.object(routes, "get_scoped_session", return_value=session):
        ok = client.patch("/project_cards/1", json={"review_status": "reviewed", "age_min": 5})
        bad = client.patch("/project_cards/1", json={"age_min": 99})
        empty = client.patch("/project_cards/1", json={})
    assert ok.status_code == 200
    assert card.review_status == "reviewed" and card.age_min == 5
    assert bad.status_code == 400
    assert empty.status_code == 400


def test_import_endpoint(client):
    session = MagicMock()
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "upsert_cards") as upsert:
            upsert.return_value.as_dict.return_value = {"created": 2, "updated": 0, "kept_reviewed": 0}
            response = client.post("/project_cards/import", json={"cards": [_raw(), _raw(number="002")]})
        missing = client.post("/project_cards/import", json={"cards": []})
        broken = client.post("/project_cards/import", json={"cards": "x"})
    assert response.get_json()["created"] == 2
    assert missing.status_code == 400 and broken.status_code == 400
