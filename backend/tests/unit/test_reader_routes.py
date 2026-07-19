"""Unit tests for Etap 7 (reader): users, reading progress and fragment notes.

Covers library/reader_routes.py with a mocked scoped session (no DB): user
CRUD + reader-identity resolution from the API key (Etap 8: flask.g.auth set
by the server middleware; service keys get 403), reading-progress upsert
semantics and note anchoring/ownership rules.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import reader_routes as rr  # noqa: E402
from library.auth import AuthContext  # noqa: E402
from library.db.models import User, UserDocumentNote, UserReadingProgress, Document  # noqa: E402


READER_USER = User(username="krzysztof", display_name="Krzysztof")
READER_USER.id = 1

OTHER_USER = User(username="gosc")
OTHER_USER.id = 2

DOC_ID = 9204

USER_AUTH = AuthContext(kind="user", key_id=10, key_name="frontend-krzysztof", user_id=READER_USER.id)
SERVICE_AUTH = AuthContext(kind="service", key_id=11, key_name="chrome-extension", user_id=None)


def _make_note(**overrides) -> UserDocumentNote:
    note = UserDocumentNote(
        user_id=READER_USER.id,
        document_id=DOC_ID,
        chapter_position=4,
        anchor_quote="cytowany fragment",
        anchor_prefix="poprzedzający tekst",
        anchor_suffix="następujący tekst",
        note_text="moja reakcja",
        tags=[],
        stance="agree",
    )
    note.id = 501
    for key, value in overrides.items():
        setattr(note, key, value)
    return note


@pytest.fixture
def fake_session(monkeypatch):
    session = MagicMock()
    doc = MagicMock(spec=Document)
    doc.id = DOC_ID

    store = {"users": {1: READER_USER, 2: OTHER_USER}, "notes": {}, "doc": doc}

    def fake_get(model, pk):
        if model is User:
            return store["users"].get(pk)
        if model is Document:
            return store["doc"] if pk == DOC_ID else None
        if model is UserDocumentNote:
            return store["notes"].get(pk)
        return None

    session.get.side_effect = fake_get
    # new objects get an id on add (stand-in for commit-time sequence values)
    session.add.side_effect = lambda obj: setattr(obj, "id", getattr(obj, "id", None) or 900)
    session.store = store
    monkeypatch.setattr(rr, "get_scoped_session", lambda: session)
    return session


@pytest.fixture
def auth_holder():
    """Mutable stand-in for the AuthContext the server middleware puts in g.auth."""
    return {"ctx": USER_AUTH}


@pytest.fixture
def client(fake_session, auth_holder):
    app = flask.Flask(__name__)

    @app.before_request
    def _set_auth():
        if auth_holder["ctx"] is not None:
            flask.g.auth = auth_holder["ctx"]

    app.register_blueprint(rr.bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class TestUsers:
    def test_list_users(self, client, fake_session):
        fake_session.execute.return_value.scalars.return_value.all.return_value = [
            READER_USER, OTHER_USER,
        ]
        resp = client.get("/users")
        data = resp.get_json()

        assert resp.status_code == 200
        assert [u["username"] for u in data["users"]] == ["krzysztof", "gosc"]

    def test_create_user(self, client, fake_session):
        fake_session.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.post("/users", json={"username": "nowy", "display_name": " Nowy "})
        data = resp.get_json()

        assert resp.status_code == 201
        assert data["user"]["username"] == "nowy"
        assert data["user"]["display_name"] == "Nowy"
        fake_session.commit.assert_called_once()

    def test_create_user_duplicate_409(self, client, fake_session):
        fake_session.execute.return_value.scalar_one_or_none.return_value = READER_USER
        resp = client.post("/users", json={"username": "krzysztof"})
        assert resp.status_code == 409

    def test_create_user_empty_username_400(self, client):
        resp = client.post("/users", json={"username": "  "})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Reader identity from the API key (g.auth)
# ---------------------------------------------------------------------------


class TestRequireUser:
    def test_no_auth_context_401(self, client, auth_holder):
        auth_holder["ctx"] = None
        resp = client.get(f"/document/{DOC_ID}/reading_progress")
        assert resp.status_code == 401

    def test_service_key_403(self, client, auth_holder):
        auth_holder["ctx"] = SERVICE_AUTH
        resp = client.get(f"/document/{DOC_ID}/reading_progress")
        assert resp.status_code == 403

    def test_no_header_needed_with_user_key(self, client, fake_session):
        fake_session.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.get(f"/document/{DOC_ID}/reading_progress")
        assert resp.status_code == 200

    def test_key_user_gone_403(self, client, auth_holder):
        auth_holder["ctx"] = AuthContext(kind="user", key_id=12, key_name="stale", user_id=99)
        resp = client.get(f"/document/{DOC_ID}/reading_progress")
        assert resp.status_code == 403

    def test_unknown_document_404(self, client, fake_session):
        resp = client.get("/document/12345/reading_progress")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reading progress
# ---------------------------------------------------------------------------


class TestReadingProgress:
    def test_get_without_row_returns_nulls(self, client, fake_session):
        fake_session.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.get(f"/document/{DOC_ID}/reading_progress")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["current_chapter"] is None
        assert data["read_chapters"] == []

    def test_get_existing_row(self, client, fake_session):
        progress = UserReadingProgress(
            user_id=1, document_id=DOC_ID, current_chapter=7,
            current_chapter_title="Bank centralny", read_chapters=[3, 1, 2],
        )
        fake_session.execute.return_value.scalar_one_or_none.return_value = progress
        resp = client.get(f"/document/{DOC_ID}/reading_progress")
        data = resp.get_json()

        assert data["current_chapter"] == 7
        assert data["current_chapter_title"] == "Bank centralny"
        assert data["read_chapters"] == [1, 2, 3]

    def test_put_creates_row(self, client, fake_session):
        fake_session.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.put(
            f"/document/{DOC_ID}/reading_progress",
            json={"current_chapter": 5, "current_chapter_title": "Rozdział 5", "mark_read": [4]},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["current_chapter"] == 5
        assert data["read_chapters"] == [4]
        fake_session.add.assert_called_once()
        fake_session.commit.assert_called_once()

    def test_put_updates_existing_row_and_read_set(self, client, fake_session):
        progress = UserReadingProgress(
            user_id=1, document_id=DOC_ID, current_chapter=3, read_chapters=[1, 2, 3],
        )
        fake_session.execute.return_value.scalar_one_or_none.return_value = progress
        resp = client.put(
            f"/document/{DOC_ID}/reading_progress",
            json={"current_chapter": 6, "mark_read": [5, 5], "unmark_read": [2]},
        )
        data = resp.get_json()

        assert data["current_chapter"] == 6
        assert data["read_chapters"] == [1, 3, 5]
        fake_session.add.assert_not_called()

    def test_put_invalid_current_chapter_400(self, client):
        for bad in (None, 0, -1, "3"):
            resp = client.put(
                f"/document/{DOC_ID}/reading_progress",
                json={"current_chapter": bad},
            )
            assert resp.status_code == 400

    def test_put_invalid_mark_read_400(self, client):
        resp = client.put(
            f"/document/{DOC_ID}/reading_progress",
            json={"current_chapter": 1, "mark_read": [0]},
        )
        assert resp.status_code == 400

    def test_put_truncates_title_to_500(self, client, fake_session):
        fake_session.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.put(
            f"/document/{DOC_ID}/reading_progress",
            json={"current_chapter": 1, "current_chapter_title": "x" * 600},
        )
        assert len(resp.get_json()["current_chapter_title"]) == 500


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class TestNotes:
    def test_create_note(self, client, fake_session):
        resp = client.post(
            f"/document/{DOC_ID}/notes",
            json={
                "anchor_quote": "fragment książki",
                "note_text": "zgadzam się z autorem",
                "anchor_prefix": "p" * 150,
                "anchor_suffix": "s" * 150,
                "chapter_position": 4,
                "stance": "agree",
            },
        )
        data = resp.get_json()

        assert resp.status_code == 201
        note = data["note"]
        assert note["anchor_quote"] == "fragment książki"
        assert len(note["anchor_prefix"]) == 100
        assert len(note["anchor_suffix"]) == 100
        assert note["chapter_position"] == 4
        assert note["stance"] == "agree"
        fake_session.commit.assert_called_once()

    def test_create_note_requires_quote_and_text(self, client):
        resp = client.post(
            f"/document/{DOC_ID}/notes",
            json={"anchor_quote": "", "note_text": "coś"},
        )
        assert resp.status_code == 400
        resp = client.post(
            f"/document/{DOC_ID}/notes",
            json={"anchor_quote": "coś", "note_text": " "},
        )
        assert resp.status_code == 400

    def test_create_note_invalid_stance_400(self, client):
        resp = client.post(
            f"/document/{DOC_ID}/notes",
            json={"anchor_quote": "q", "note_text": "n", "stance": "meh"},
        )
        assert resp.status_code == 400

    def test_list_notes(self, client, fake_session):
        fake_session.execute.return_value.scalars.return_value.all.return_value = [_make_note()]
        resp = client.get(f"/document/{DOC_ID}/notes")
        data = resp.get_json()

        assert resp.status_code == 200
        assert len(data["notes"]) == 1
        assert data["notes"][0]["note_text"] == "moja reakcja"

    def test_patch_note_updates_text_and_stance(self, client, fake_session):
        note = _make_note()
        fake_session.store["notes"][note.id] = note
        resp = client.patch(
            f"/note/{note.id}",
            json={"note_text": "zmienione", "stance": "disagree"},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["note"]["note_text"] == "zmienione"
        assert data["note"]["stance"] == "disagree"

    def test_patch_note_empty_text_400(self, client, fake_session):
        note = _make_note()
        fake_session.store["notes"][note.id] = note
        resp = client.patch(f"/note/{note.id}", json={"note_text": ""})
        assert resp.status_code == 400

    def test_patch_foreign_note_403(self, client, fake_session):
        note = _make_note(user_id=OTHER_USER.id)
        fake_session.store["notes"][note.id] = note
        resp = client.patch(f"/note/{note.id}", json={"note_text": "x"})
        assert resp.status_code == 403

    def test_delete_note(self, client, fake_session):
        note = _make_note()
        fake_session.store["notes"][note.id] = note
        resp = client.delete(f"/note/{note.id}")

        assert resp.status_code == 200
        fake_session.delete.assert_called_once_with(note)

    def test_delete_foreign_note_403(self, client, fake_session):
        note = _make_note(user_id=OTHER_USER.id)
        fake_session.store["notes"][note.id] = note
        resp = client.delete(f"/note/{note.id}")
        assert resp.status_code == 403

    def test_delete_missing_note_404(self, client):
        resp = client.delete("/note/777")
        assert resp.status_code == 404
