"""HTTP contract of region-scoped corrections (country tag, optional channel) with mocked persistence."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask

from library import transcript_corrections_routes as routes
from library.db.models import Document, TranscriptCorrection
from library.transcript_corrections import TranscriptCorrectionRow

YEMEN = "kraj-jemen"


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind="service", key_name="test-key")

    session = MagicMock()
    session.get.return_value = None

    def commit():
        if session.add.called:
            session.add.call_args.args[0].id = 42

    session.commit.side_effect = commit
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(routes, "bust_cache", MagicMock())
    bump = MagicMock()
    monkeypatch.setattr(routes, "_bump_hit_counts", bump)
    return app.test_client(), session, bump


def region_payload(**overrides):
    return dict(pattern="Hutni", replacement="Huti", scope="region", country_slug=YEMEN) | overrides


def test_create_region_rule_with_single_word(api):
    client, session, _ = api
    response = client.post("/transcript_corrections", json=region_payload(country_slug=" KRAJ-JEMEN "))
    assert response.status_code == 201
    rule = response.get_json()["rule"]
    assert rule["scope"] == "region" and rule["country_slug"] == YEMEN and rule["author"] is None
    session.commit.assert_called_once()


def test_create_region_rule_narrowed_to_channel(api):
    rule = api[0].post("/transcript_corrections", json=region_payload(author="  Kanal  Wschód ")).get_json()["rule"]
    assert rule["author"] == "kanal wschód"


@pytest.mark.parametrize("overrides", [
    {"country_slug": None}, {"country_slug": "jemen"}, {"country_slug": "kraj-atlantyda"},
    {"scope": "global"}, {"pattern": "ab"},
])
def test_create_rejects_invalid_region_rules(api, overrides):
    client, session, _ = api
    assert client.post("/transcript_corrections", json=region_payload(**overrides)).status_code == 400
    session.commit.assert_not_called()


def test_global_single_word_is_still_rejected(api):
    assert api[0].post("/transcript_corrections", json={"pattern": "Hutni", "replacement": "Huti"}).status_code == 400


def test_list_filters_by_country(api):
    client, session, _ = api
    session.scalars.return_value.all.return_value = [TranscriptCorrection(id=1, **region_payload(), hit_count=0)]
    response = client.get("/transcript_corrections?scope=region&country_slug=KRAJ-JEMEN")
    assert response.status_code == 200
    assert response.get_json()["rules"][0]["country_slug"] == YEMEN
    assert session.scalars.call_args.args[0].compile().params == {"scope_1": "region", "country_slug_1": YEMEN}


def test_patch_moves_rule_between_scopes(api):
    client, session, _ = api
    rule = TranscriptCorrection(id=42, pattern="Hutni", replacement="Huti", scope="region",
                                country_slug=YEMEN, active=True)
    session.get.return_value = rule
    # Leaving the region scope without clearing the country is refused; clearing it first makes it a phrase rule.
    assert client.patch("/transcript_corrections/42", json={"scope": "global"}).status_code == 400
    assert client.patch("/transcript_corrections/42",
                        json={"scope": "global", "country_slug": None, "pattern": "Hutni zaatakowali"}).status_code == 200
    assert rule.scope == "global" and rule.country_slug is None


@pytest.mark.parametrize("tags,expected_hits,expected_text", [
    ([YEMEN, "polityka"], [{"rule_id": 7, "count": 1}], "Huti atakują"),
    (["kraj-iran"], [], "Hutni atakują"),
    (None, [], "Hutni atakują"),
])
def test_apply_uses_document_country_tags(api, tags, expected_hits, expected_text):
    client, session, _ = api
    doc = Document(id=11263, document_type="youtube", byline="channel", text="Hutni atakują", text_md=None, tags=tags)
    session.get.return_value = doc
    session.scalars.return_value = [TranscriptCorrectionRow(7, "region", None, "Hutni", "Huti", YEMEN)]
    result = client.post("/transcript_corrections/apply", json={"document_id": 11263, "dry_run": False}).get_json()
    assert result["hits"] == expected_hits
    assert doc.text == expected_text
    assert result["countries"] == sorted(c for c in (tags or []) if c.startswith("kraj-"))
