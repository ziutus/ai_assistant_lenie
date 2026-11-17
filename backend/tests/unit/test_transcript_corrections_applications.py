"""What a dictionary really changed: chapter-aware change list, audit rows and the document endpoint."""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask

from library import transcript_corrections as rules
from library import transcript_corrections_routes as routes
from library.db.models import Document, TranscriptCorrectionApplication
from library.transcript_corrections import TranscriptCorrectionRow

YEMEN = "kraj-jemen"
TEXT = (
    "Wstęp bez zmian.\n\n"
    "## Wstęp\n\nHutik i Huti.\n\n"
    "## Jemen\n\nTais, potem Tais oraz huti.\n\n"
    "## Reklama\n\nBez zmian."
)


def region(rule_id, pattern, replacement, author=None):
    return TranscriptCorrectionRow(rule_id, "region", author, pattern, replacement, YEMEN)


RULES = [region(1, "Hutik", "Huti"), region(2, "Tais", "Taiz"), region(3, "huti", "Huti")]


def test_chapter_position_counts_headings_before_the_offset():
    assert rules.chapter_position(TEXT, 0) == 0
    assert rules.chapter_position(TEXT, TEXT.index("Hutik")) == 1
    assert rules.chapter_position(TEXT, TEXT.index("Tais")) == 2
    assert rules.chapter_position(TEXT, TEXT.index("Bez zmian.", 40)) == 3
    # a match inside the heading line belongs to that chapter
    assert rules.chapter_position("## Tais\n\nx", 3) == 1


def test_detailed_changes_skip_no_ops_and_know_the_chapter():
    corrected, hits, changes = rules.correct_text_detailed(TEXT, None, RULES, {YEMEN})
    assert corrected.count("Taiz") == 2 and "Hutik" not in corrected
    assert sorted(changes) == [(1, "Hutik", "Huti", 1), (2, "Tais", "Taiz", 2), (2, "Tais", "Taiz", 2),
                               (3, "huti", "Huti", 2)]
    # rule huti -> Huti matches "Huti" twice (the original one and the repaired "Hutik") plus one real "huti":
    # three hits, one change
    assert dict(hits)[3] == 3
    assert rules.correct_text(TEXT, None, RULES, {YEMEN}) == (corrected, hits)


def test_no_changes_without_the_country_tag():
    assert rules.correct_text_detailed(TEXT, None, RULES, set())[2] == []


@pytest.fixture
def api(monkeypatch):
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        flask.g.auth = SimpleNamespace(kind="service", key_name="test-key")

    session = MagicMock()
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(routes, "bust_cache", MagicMock())
    monkeypatch.setattr(routes, "_bump_hit_counts", MagicMock())
    monkeypatch.setattr(routes, "load_active_rules", lambda **kwargs: RULES)
    return app.test_client(), session


def test_apply_records_applications_only_when_persisting(api):
    client, session = api
    doc = Document(id=11263, document_type="youtube", byline="Kanał", text=TEXT, text_md=None, tags=[YEMEN])
    session.get.return_value = doc
    assert client.post("/transcript_corrections/apply", json={"document_id": 11263}).status_code == 200
    session.add.assert_not_called()

    response = client.post("/transcript_corrections/apply", json={"document_id": 11263, "dry_run": False})
    assert response.status_code == 200
    added = [call.args[0] for call in session.add.call_args_list]
    assert all(isinstance(row, TranscriptCorrectionApplication) for row in added)
    summary = {(r.rule_id, r.original_text, r.replacement_text, r.chapter_position): r.occurrences for r in added}
    assert summary == {(1, "Hutik", "Huti", 1): 1, (2, "Tais", "Taiz", 2): 2, (3, "huti", "Huti", 2): 1}
    assert all(row.document_id == 11263 for row in added)
    session.commit.assert_called_once()


def test_one_off_apply_records_nothing(api):
    client, session = api
    session.get.return_value = Document(id=1, document_type="youtube", text="Hutni", text_md=None, tags=[YEMEN])
    body = {"document_id": 1, "pattern": "Hutni", "replacement": "Huti", "dry_run": False}
    assert client.post("/transcript_corrections/apply", json=body).status_code == 200
    session.add.assert_not_called()


def test_document_endpoint_lists_applications_dictionaries_and_pending(api):
    client, session = api
    doc = Document(id=11263, document_type="youtube", byline="Kanał", text=TEXT, text_md=None, tags=[YEMEN, "iran"])
    session.get.return_value = doc
    when = datetime.datetime(2026, 11, 17, 8, 0)
    session.execute.return_value.all.return_value = [
        (TranscriptCorrectionApplication(rule_id=2, original_text="Tais", replacement_text="Taiz",
                                         chapter_position=2, occurrences=3, applied_at=when), "region", YEMEN),
        (TranscriptCorrectionApplication(rule_id=2, original_text="Tais", replacement_text="Taiz",
                                         chapter_position=2, occurrences=1, applied_at=when), "region", YEMEN),
    ]
    data = client.get("/document/11263/transcript_corrections").get_json()
    assert data["applications"] == [{
        "rule_id": 2, "scope": "region", "country_slug": YEMEN, "original_text": "Tais",
        "replacement_text": "Taiz", "chapter_position": 2, "occurrences": 4, "applied_at": when.isoformat(),
    }]
    assert data["dictionaries"] == [{"country_slug": YEMEN, "country_name": "Jemen", "rules": 3}]
    assert data["pending_changes"] == 4 and data["author"] == "Kanał"


def test_document_endpoint_404_and_other_country(api):
    client, session = api
    session.get.return_value = None
    assert client.get("/document/9/transcript_corrections").status_code == 404
    session.get.return_value = Document(id=2, document_type="youtube", text=TEXT, tags=["kraj-iran"])
    session.execute.return_value.all.return_value = []
    data = client.get("/document/2/transcript_corrections").get_json()
    assert data["dictionaries"] == [] and data["pending_changes"] == 0 and data["applications"] == []


def test_list_paginates_and_filters_scopes(api):
    client, session = api
    session.scalar.return_value = 120
    session.scalars.return_value.all.return_value = []
    data = client.get("/transcript_corrections?scope=global,author&limit=50&offset=50").get_json()
    assert data["total"] == 120 and data["limit"] == 50 and data["offset"] == 50
    query = session.scalars.call_args.args[0]
    assert "transcript_corrections.scope IN" in str(query)
    assert client.get("/transcript_corrections?limit=0").status_code == 400
    assert client.get("/transcript_corrections?limit=x").status_code == 400
    assert client.get("/transcript_corrections?limit=10&offset=-1").status_code == 400


def test_list_without_limit_returns_everything_with_total(api):
    client, session = api
    session.scalars.return_value.all.return_value = []
    data = client.get("/transcript_corrections").get_json()
    assert data["total"] == 0 and data["rules"] == []
