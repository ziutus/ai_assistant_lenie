"""Session-based Topics CRUD and polymorphic membership resolution."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from library.db.models import ChatConversation, ChatMessage, Contact, Document, Topic, TopicItem

ENTITY_MODELS = {
    "document": Document,
    "contact": Contact,
    "chat_conversation": ChatConversation,
    "chat_message": ChatMessage,
}


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
        raise ValueError("name must be a non-empty string of at most 120 characters")
    return value.strip()


def _text(value, field):
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value


def _save_topic(session, topic):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_topics_active_lower_name" in str(exc.orig):
            raise ValueError("An active topic with this name already exists") from exc
        raise
    return topic


def create_topic(session, name, description=None) -> Topic:
    topic = Topic(name=_name(name), description=_text(description, "description"))
    session.add(topic)
    return _save_topic(session, topic)


def list_topics(session, include_archived=False) -> list[Topic]:
    stmt = select(Topic)
    if not include_archived:
        stmt = stmt.where(Topic.archived_at.is_(None))
    return list(session.scalars(stmt.order_by(func.lower(Topic.name), Topic.id)).all())


def get_topic(session, topic_id) -> Topic | None:
    return session.get(Topic, topic_id)


def update_topic(session, topic_id, changes) -> Topic | None:
    topic = get_topic(session, topic_id)
    if topic is None:
        return None
    # Validate the entire request before changing any ORM state.
    name = _name(changes["name"]) if "name" in changes else topic.name
    description = _text(changes.get("description", topic.description), "description")
    if "archived" in changes and not isinstance(changes["archived"], bool):
        raise ValueError("archived must be a boolean")
    topic.name, topic.description = name, description
    if "archived" in changes:
        topic.archived_at = (topic.archived_at or datetime.now(timezone.utc)) if changes["archived"] else None
    topic.updated_at = datetime.now(timezone.utc)
    return _save_topic(session, topic)


def archive_topic(session, topic_id) -> bool:
    return update_topic(session, topic_id, {"archived": True}) is not None


def add_item(session, topic_id, entity_type, entity_id, note=None) -> TopicItem:
    if not isinstance(entity_type, str) or entity_type not in ENTITY_MODELS:
        raise ValueError("entity_type must be one of: " + ", ".join(ENTITY_MODELS))
    if type(entity_id) is not int or not 0 < entity_id <= 2147483647:
        raise ValueError("entity_id must be a positive 32-bit integer")
    note = _text(note, "note")
    # Serialize membership writes for a topic so concurrent duplicate adds are safe.
    topic = session.scalar(select(Topic).where(Topic.id == topic_id).with_for_update())
    if topic is None:
        raise ValueError(f"Topic {topic_id} not found")
    if session.get(ENTITY_MODELS[entity_type], entity_id) is None:
        raise ValueError(f"{entity_type} {entity_id} not found")
    item = session.scalar(select(TopicItem).where(
        TopicItem.topic_id == topic_id, TopicItem.entity_type == entity_type, TopicItem.entity_id == entity_id,
    ))
    if item is None:
        item = TopicItem(topic_id=topic_id, entity_type=entity_type, entity_id=entity_id, note=note)
        session.add(item)
    elif note is not None:
        item.note = note
    session.commit()
    return item


def remove_item(session, item_id) -> bool:
    item = session.get(TopicItem, item_id)
    if item is None:
        return False
    session.delete(item)
    session.commit()
    return True


def topic_to_dict(topic) -> dict:
    return {
        "id": topic.id, "name": topic.name, "description": topic.description,
        **{field: getattr(topic, field).isoformat() if getattr(topic, field) else None
           for field in ("archived_at", "created_at", "updated_at")},
    }


def item_to_dict(item) -> dict:
    return {"id": item.id, "topic_id": item.topic_id, "entity_type": item.entity_type,
            "entity_id": item.entity_id, "note": item.note,
            "created_at": item.created_at.isoformat() if item.created_at else None}


def _display(entity_type, entity):
    if entity_type == "document":
        return {"id": entity.id, "title": entity.title or entity.url, "url": entity.url}
    if entity_type == "contact":
        name = " ".join(filter(None, [entity.first_name, entity.last_name]))
        return {"id": entity.id, "display_name": name or entity.display_label or entity.company or "Kontakt bez nazwy"}
    if entity_type == "chat_conversation":
        return {"id": entity.id, "display_name": entity.display_name}
    return {"id": entity.id, "content": (entity.content or "")[:200],
            "sent_at": entity.sent_at.isoformat() if entity.sent_at else None,
            "conversation_id": entity.conversation_id}


def get_topic_detail(session, topic_id) -> dict | None:
    topic = get_topic(session, topic_id)
    if topic is None:
        return None
    grouped = {kind: [] for kind in ENTITY_MODELS}
    items = list(session.scalars(select(TopicItem).where(TopicItem.topic_id == topic_id)
                                 .order_by(TopicItem.created_at, TopicItem.id)).all())
    for kind, model in ENTITY_MODELS.items():
        members = [item for item in items if item.entity_type == kind]
        if not members:
            continue
        entities = {entity.id: entity for entity in session.scalars(
            select(model).where(model.id.in_([item.entity_id for item in members]))
        ).all()}
        for item in members:
            entity = entities.get(item.entity_id)
            # Deleted polymorphic targets remain visible/removable as missing links.
            grouped[kind].append({**item_to_dict(item), "entity": _display(kind, entity) if entity else None})
    return {**topic_to_dict(topic), "items": grouped}
