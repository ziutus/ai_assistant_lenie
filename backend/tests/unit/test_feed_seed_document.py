import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from sqlalchemy.dialects import postgresql

from library import feed_routes, feed_seed_document as service
from library.db.models import ContentGroup, Document, FeedItem, FeedItemGroupMembership, FeedSource
from library.document_service import ExistingDocumentError


def make_item():
    return FeedItem(id=7, feed_source_id=1, title="Inicjatywa", url="https://example.com",
                    status="new", review_note="  Zbadaj inicjatywę.  ", summary="Opis",
                    published_at=dt.datetime(2026, 10, 25), llm_discussion_status="open")


def test_markdown():
    item = make_item()
    assert service.build_seed_markdown(item, "Blog", ["CSS", "Web"]) == """# Zalążek: Inicjatywa

> Zalążek dokumentu z wpisu feedu #7 (Blog, 2026-10-25). Punkt wyjścia do dalszej pracy z LLM (ChatGPT / Claude Code).

## Co mnie zainteresowało i co dalej
Zbadaj inicjatywę.

## Źródło
- URL: https://example.com
- Opublikowano: 2026-10-25
- Tematy: CSS, Web

## Streszczenie ze źródła
Opis

## Do ustalenia
- [ ] Czy to wymaga osobnego dokumentu lub notatki?
- [ ] Co jeszcze sprawdzić w źródle?
"""


@pytest.mark.parametrize("comment", [None, "", "   "])
def test_markdown_fallbacks(comment):
    item = make_item()
    item.review_note, item.summary, item.published_at = comment, None, None
    text = service.build_seed_markdown(item, None, [])
    assert "(nieznane źródło, brak daty)" in text
    assert "(uzupełnij: co Cię zainteresowało i co zrobić dalej)" in text
    assert "- Tematy: brak" in text
    assert "- Opublikowano: brak daty" in text
    assert "(brak streszczenia)" in text


def test_create_once_preserves_item_and_existing_document(monkeypatch):
    item = make_item()
    for name, kind, archived in [("Web", "topic", None), ("CSS", "topic", None),
                                  ("Old", "topic", dt.datetime.now()), ("High", "priority", None)]:
        item.group_memberships.append(FeedItemGroupMembership(
            group=ContentGroup(name=name, kind=kind, archived_at=archived)))
    original = dict(item.__dict__)
    session = MagicMock()
    session.get.side_effect = lambda model, _: item if model is FeedItem else FeedSource(name="Blog")
    document = Document(id=42, tags="existing tags")
    create = MagicMock(side_effect=[document, ExistingDocumentError(document)])
    monkeypatch.setattr(service.DocumentService, "create_document", create)
    copy = MagicMock()
    monkeypatch.setattr(service, "copy_feed_groups_to_document", copy)
    assert service.create_seed_document(session, 7) == (document, True)
    create.assert_called_with(url="lenie://seed/feed-item/7", url_type="text", title="Zalążek: Inicjatywa",
                              note="Zalążek z wpisu feedu #7: https://example.com", source="own", language="pl")
    assert document.text == document.text_md
    assert "- Tematy: CSS, Web" in document.text
    assert document.tags == "existing tags"
    copy.assert_called_once_with(session, [item], document, "feed_import")
    document.text = document.text_md = "User edits"
    assert service.create_seed_document(session, 7) == (document, False)
    assert document.text == document.text_md == "User edits"
    assert item.__dict__ == original
    assert item.document_id is None
    session.commit.assert_called_once()
    assert copy.call_count == 1


def test_missing_item():
    session = MagicMock()
    session.get.return_value = None
    with pytest.raises(ValueError, match="feed item not found"):
        service.create_seed_document(session, 99)
    session.commit.assert_not_called()


def test_batch_lookup_one_query():
    session = MagicMock()
    session.execute.return_value.all.return_value = [(42, service.seed_url(7)), (43, service.seed_url(8))]
    assert service.seed_document_ids(session, [7, 8, 9]) == {7: 42, 8: 43}
    session.execute.assert_called_once()
    sql = str(session.execute.call_args.args[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "documents.document_type = 'text'" in sql
    assert "documents.url IN" in sql
    assert all(service.seed_url(i) in sql for i in [7, 8, 9])


def test_item_dict_lookup_and_supplied_map(monkeypatch):
    lookup = MagicMock(return_value={7: 42})
    monkeypatch.setattr(feed_routes, "seed_document_ids", lookup)
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: "session")
    assert feed_routes._item_dict(make_item())["seed_document_id"] == 42
    lookup.assert_called_once_with("session", [7])
    assert feed_routes._item_dict(make_item(), seed_ids={})["seed_document_id"] is None
    assert lookup.call_count == 1


def test_list_looks_up_seeds_once_for_the_page(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    session = MagicMock()
    second = make_item()
    second.id = 8
    session.scalars.return_value.all.return_value = [make_item(), second]
    session.scalar.return_value = 2
    lookup = MagicMock(return_value={7: 42})
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(feed_routes.feed_retention, "default_months", lambda _: 6)
    monkeypatch.setattr(feed_routes, "seed_document_ids", lookup)
    response = app.test_client().get("/feed_items")
    assert response.status_code == 200
    assert [item["seed_document_id"] for item in response.json["feed_items"]] == [42, None]
    lookup.assert_called_once_with(session, [7, 8])


@pytest.mark.parametrize("created,code", [(True, 201), (False, 200), (None, 404)])
def test_route(monkeypatch, created, code):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    session = MagicMock()
    session.get.return_value = make_item()
    session.execute.return_value.all.return_value = [(42, service.seed_url(7))]
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    create = MagicMock(return_value=(Document(id=42), created))
    if created is None:
        create.side_effect = ValueError("feed item not found")
    monkeypatch.setattr(feed_routes, "create_seed_document", create)
    response = app.test_client().post("/feed_items/7/seed_document")
    assert response.status_code == code
    create.assert_called_once_with(session, 7)
    if created is not None:
        assert response.json["created"] is created
        assert response.json["document_id"] == response.json["feed_item"]["seed_document_id"] == 42
