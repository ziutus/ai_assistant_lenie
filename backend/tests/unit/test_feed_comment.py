from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask, g

from library import content_group_suggestion_service as svc, feed_routes
from library.db.models import FeedItem


def test_comment_is_added_to_the_material_and_survives_truncation():
    item = FeedItem(id=1, title="CSS w 2027", summary="x" * 9000, review_note="  Chcę zalążek dokumentu o inicjatywie.  ", raw_payload={})
    text = svc.target_text(item)
    assert len(text) <= svc.MAX_INPUT_CHARS
    assert text.endswith("KOMENTARZ UŻYTKOWNIKA (co go zainteresowało i co dalej): Chcę zalążek dokumentu o inicjatywie.")
    assert text.startswith("TYTUŁ: CSS w 2027")


def test_material_without_a_comment_is_unchanged():
    item = FeedItem(id=1, title="t", summary="s", review_note=None, raw_payload={})
    assert "KOMENTARZ" not in svc.target_text(item)
    assert svc.target_text(FeedItem(id=1, title="t", summary="s", review_note="   ", raw_payload={})) == svc.target_text(item)


def test_a_very_long_comment_is_cut_to_the_limit():
    item = FeedItem(id=1, title="t", summary="s", review_note="k" * 5000, raw_payload={})
    text = svc.target_text(item)
    assert text.count("k") == svc.MAX_COMMENT_CHARS and len(text) <= svc.MAX_INPUT_CHARS


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    monkeypatch.setattr(feed_routes, "get_scoped_session", MagicMock())
    monkeypatch.setattr(feed_routes, "_item_dict", lambda item: {"id": item.id, "review_note": item.review_note})
    return app.test_client()


def test_note_route_validates_type_and_length(client, monkeypatch):
    save = MagicMock(return_value=SimpleNamespace(id=7, review_note="ok"))
    monkeypatch.setattr(feed_routes, "save_review_note", save)
    assert client.patch("/feed_items/7/note", json={"note": "ok"}).json == {"id": 7, "review_note": "ok"}
    assert client.patch("/feed_items/7/note", json={"note": "x" * 4000}).status_code == 200
    assert client.patch("/feed_items/7/note", json={"note": "x" * 4001}).status_code == 400
    assert client.patch("/feed_items/7/note", json={"note": 5}).status_code == 400
    assert save.call_count == 2


def test_note_route_unknown_item_is_404(client, monkeypatch):
    monkeypatch.setattr(feed_routes, "save_review_note", MagicMock(side_effect=ValueError("feed item not found")))
    assert client.patch("/feed_items/999/note", json={"note": "x"}).status_code == 404
