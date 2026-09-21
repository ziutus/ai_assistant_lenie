"""Topics unit tests: real local membership tables, mocked polymorphic targets."""

import importlib.util
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from flask import Flask
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from library import topic_routes, topic_service as svc
from library.db.models import ChatConversation, ChatMessage, Contact, Document, Topic, TopicItem


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Topic.__table__.create(engine)
    TopicItem.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def target_exists(monkeypatch, session, model=Document, entity_id=7):
    original = session.get
    monkeypatch.setattr(session, "get", lambda cls, key: object() if cls is model and key == entity_id
                        else None if cls in svc.ENTITY_MODELS.values() else original(cls, key))


def test_create_list_archive_and_name_reuse(session):
    topic = svc.create_topic(session, "  Gardens  ", "Investment")
    topic_id = topic.id
    assert topic.name == "Gardens"
    assert topic.created_at and topic.updated_at
    with pytest.raises(ValueError, match="already exists"):
        svc.create_topic(session, "gardens")
    assert svc.archive_topic(session, topic_id)
    assert svc.list_topics(session) == []
    assert svc.list_topics(session, include_archived=True) == [topic]
    replacement = svc.create_topic(session, "GARDENS")
    with pytest.raises(ValueError, match="already exists"):
        svc.update_topic(session, topic_id, {"archived": False})
    assert svc.get_topic(session, topic_id).archived_at
    assert svc.list_topics(session) == [replacement]
    assert not svc.archive_topic(session, 999)


@pytest.mark.parametrize("name", [None, "", "  ", "x" * 121, 123, []])
def test_invalid_names(session, name):
    with pytest.raises(ValueError, match="name"):
        svc.create_topic(session, name)


def test_update_validation_and_sorting(session):
    topic = svc.create_topic(session, "Zulu")
    alpha = svc.create_topic(session, "alpha")
    assert svc.list_topics(session) == [alpha, topic]
    before = topic.updated_at
    svc.update_topic(session, topic.id, {"name": "Beta", "description": "New"})
    assert topic.name == "Beta" and topic.description == "New" and topic.updated_at >= before
    with pytest.raises(ValueError, match="description"):
        svc.update_topic(session, topic.id, {"name": "Wrong", "description": []})
    assert topic.name == "Beta"
    with pytest.raises(ValueError, match="boolean"):
        svc.update_topic(session, topic.id, {"archived": "true"})
    svc.update_topic(session, topic.id, {"description": None})
    assert topic.description is None


@pytest.mark.parametrize("kind,model", svc.ENTITY_MODELS.items())
def test_add_duplicate_update_remove(session, monkeypatch, kind, model):
    target_exists(monkeypatch, session, model)
    topic = svc.create_topic(session, "Test")
    item = svc.add_item(session, topic.id, kind, 7, "First")
    assert svc.add_item(session, topic.id, kind, 7).id == item.id
    assert item.note == "First"
    assert svc.add_item(session, topic.id, kind, 7, "Updated").id == item.id
    assert item.note == "Updated"
    assert len(session.scalars(select(TopicItem)).all()) == 1
    assert svc.remove_item(session, item.id)
    assert not svc.remove_item(session, item.id)


@pytest.mark.parametrize("kind,entity_id,note,match", [
    ("unknown", 7, None, "entity_type"), ([], 7, None, "entity_type"),
    ("document", True, None, "entity_id"), ("document", "7", None, "entity_id"),
    ("document", 0, None, "entity_id"), ("document", 2147483648, None, "entity_id"),
    ("document", 7, [], "note"), ("contact", 8, None, "contact 8 not found"),
])
def test_invalid_items(session, monkeypatch, kind, entity_id, note, match):
    target_exists(monkeypatch, session)
    topic = svc.create_topic(session, "Test")
    with pytest.raises(ValueError, match=match):
        svc.add_item(session, topic.id, kind, entity_id, note)
    assert session.scalars(select(TopicItem)).all() == []


def test_missing_topic(session):
    assert svc.get_topic(session, 999) is None
    assert svc.get_topic_detail(session, 999) is None
    with pytest.raises(ValueError, match="Topic 999 not found"):
        svc.add_item(session, 999, "document", 7)


def test_detail_grouping_and_deleted_target():
    session = MagicMock()
    topic = Topic(id=1, name="Test")
    session.get.return_value = topic
    now = datetime.now(timezone.utc)
    entities = [Document(id=7, title="Article", url="https://example.com"),
                Contact(id=7, first_name="Jan", last_name="Nowak"),
                ChatConversation(id=7, display_name="Group"),
                ChatMessage(id=7, content="x" * 250, sent_at=now, conversation_id=3)]
    items = [TopicItem(id=i, topic_id=1, entity_type=kind, entity_id=7)
             for i, kind in enumerate(svc.ENTITY_MODELS, 1)]
    items.append(TopicItem(id=5, topic_id=1, entity_type="document", entity_id=99))
    session.scalars.side_effect = [MagicMock(all=lambda: items)] + [
        MagicMock(all=lambda entity=entity: [entity]) for entity in entities
    ]
    detail = svc.get_topic_detail(session, 1)
    assert detail["name"] == "Test"
    groups = detail["items"]
    assert groups["document"][0]["entity"]["title"] == "Article"
    assert groups["document"][1]["entity"] is None
    assert groups["contact"][0]["entity"]["display_name"] == "Jan Nowak"
    assert groups["chat_conversation"][0]["entity"]["display_name"] == "Group"
    assert groups["chat_message"][0]["entity"] == {
        "id": 7, "content": "x" * 200, "sent_at": now.isoformat(), "conversation_id": 3,
    }


def test_contact_display_fallback():
    contact = Contact(id=1, display_label="Neighbour")
    assert svc._display("contact", contact)["display_name"] == "Neighbour"


def test_database_constraints_and_cascade(session):
    topic = svc.create_topic(session, "Test")
    topic.items.append(TopicItem(entity_type="document", entity_id=7))
    session.commit()
    session.add(TopicItem(topic_id=topic.id, entity_type="document", entity_id=7))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(TopicItem(topic_id=topic.id, entity_type="invalid", entity_id=7))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    # Bulk delete exercises the database's ON DELETE, not ORM relationship cascades.
    session.execute(Topic.__table__.delete().where(Topic.id == topic.id))
    session.commit()
    assert session.scalars(select(TopicItem)).all() == []


@pytest.fixture
def client(session, monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(topic_routes.bp)
    monkeypatch.setattr(topic_routes, "get_scoped_session", lambda: session)
    return app.test_client()


def test_routes_crud(client, session, monkeypatch):
    target_exists(monkeypatch, session)
    response = client.post("/topics", json={"name": "Test"})
    assert response.status_code == 201
    topic_id = response.json["topic"]["id"]
    assert client.get("/topics?limit=1&offset=0").json["total"] == 1
    assert client.get(f"/topics/{topic_id}").json["topic"]["items"] == {key: [] for key in svc.ENTITY_MODELS}
    response = client.post(f"/topics/{topic_id}/items", json={"entity_type": "document", "entity_id": 7})
    assert response.status_code == 201
    item_id = response.json["item"]["id"]
    assert client.delete(f"/topic_items/{item_id}").status_code == 200
    assert client.delete(f"/topic_items/{item_id}").status_code == 404
    assert client.patch(f"/topics/{topic_id}", json={"name": "Renamed", "archived": True}).status_code == 200
    assert client.get("/topics").json["total"] == 0
    assert client.get("/topics?include_archived=1").json["total"] == 1


@pytest.mark.parametrize("body", [[], "text", None, {}, {"name": ""}, {"name": "Test", "description": 1}])
def test_routes_invalid_body(client, body):
    assert client.post("/topics", json=body).status_code == 400


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
def test_routes_bad_pagination(client, query):
    assert client.get(f"/topics?{query}").status_code == 400


def test_routes_missing_and_conflicts(client):
    assert client.get("/topics/999").status_code == 404
    assert client.patch("/topics/999", json={"name": "Test"}).status_code == 404
    assert client.post("/topics/999/items", json={}).status_code == 404
    assert client.post("/topics", json={"name": "Test"}).status_code == 201
    assert client.post("/topics", json={"name": "test"}).status_code == 400


def test_migration_head_upgrade_downgrade_and_postgresql_sql():
    directory = Path(__file__).resolve().parents[2] / "alembic"
    script = ScriptDirectory(str(directory))
    assert script.get_current_head() == "c4e8b1a93d72"
    revision = script.get_revision("c4e8b1a93d72")
    assert revision.down_revision == "a9c7e2d48f10"
    spec = importlib.util.spec_from_file_location("topics_migration", revision.path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert set(inspect(connection).get_table_names()) == {"topics", "topic_items"}
            migration.downgrade()
            assert inspect(connection).get_table_names() == []
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration.upgrade()
    sql = output.getvalue()
    assert "WHERE archived_at IS NULL" in sql
    assert "ON DELETE CASCADE" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
