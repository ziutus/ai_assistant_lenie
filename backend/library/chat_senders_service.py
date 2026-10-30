"""Aggregate chat authors without loading their message histories."""

import unicodedata

from sqlalchemy import case, func, select

from library.chat_contact_service import sender_nickname, sender_phone
from library.db.models import ChatMessage, Contact


def _search_text(value):
    return "".join(c for c in unicodedata.normalize("NFKD", (value or "").casefold().replace("ł", "l"))
                   if not unicodedata.combining(c))


def list_senders(session, conversation_id, *, status=None, q="", offset=0, limit=200):
    """Use window rankings and one grouped aggregate, then join one message per author.

    Search is folded in Python so PostgreSQL and SQLite share accent-insensitive semantics.
    No message history or lazy contact relationships are loaded.
    """
    m = ChatMessage
    name = func.nullif(func.trim(m.sender_name_raw), "")
    key = func.coalesce(func.nullif(m.wa_sender_jid, ""), case((name.is_not(None), m.sender_name_raw)))
    order = [m.sent_at.desc(), m.id.desc()]
    base = select(
        m.id, key.label("key"), m.sender_name_raw, m.contact_id, m.sent_at,
        func.row_number().over(partition_by=key, order_by=order).label("latest"),
        func.row_number().over(partition_by=key, order_by=[case((name.is_not(None), 0), else_=1), *order])
        .label("named"),
        func.count().over(partition_by=[key, m.contact_id]).label("contact_count"),
        case(((m.message_type != "deleted") | (name.is_not(None)), 1), else_=0).label("eligible"),
    ).where(m.conversation_id == conversation_id, m.is_from_me.is_not(True), key.is_not(None)).cte("authors")
    ranked = select(
        base,
        func.row_number().over(partition_by=base.c.key, order_by=[
            case((base.c.contact_id.is_not(None), 0), else_=1),
            base.c.contact_count.desc(), base.c.contact_id.asc(), base.c.id.desc(),
        ]).label("contact_rank"),
    ).cte("ranked_authors")
    r = ranked.c
    grouped = select(
        r.key, func.count().label("message_count"), func.min(r.sent_at).label("first_at"),
        func.max(r.sent_at).label("last_at"),
        func.max(case((r.latest == 1, r.id))).label("sample_message_id"),
        func.max(case((r.named == 1, r.sender_name_raw))).label("name"),
        func.max(case((r.contact_rank == 1, r.contact_id))).label("contact_id"),
        func.max(r.eligible).label("eligible"),
    ).group_by(r.key).cte("senders")
    rows = session.execute(select(grouped, m, Contact).join(m, m.id == grouped.c.sample_message_id)
                           .outerjoin(Contact, Contact.id == grouped.c.contact_id)).all()
    senders = []
    for row in rows:
        data = row._mapping
        message, contact = data[m], data[Contact]
        linked = data["contact_id"] is not None
        senders.append({
            "key": data["key"], "name": data["name"], "nickname": sender_nickname(message),
            "phone": sender_phone(message), "message_count": data["message_count"],
            "first_at": data["first_at"].isoformat(), "last_at": data["last_at"].isoformat(),
            "sample_message_id": data["sample_message_id"], "can_add": not linked and bool(data["eligible"]),
            "status": "in_contacts" if linked else "missing",
            "contact": {"id": contact.id, "display_name": contact.display_label or
                        f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None} if contact else None,
        })
    count = sum(s["status"] == "in_contacts" for s in senders)
    summary = {"senders": len(senders), "in_contacts": count, "missing": len(senders) - count}
    query = _search_text(q)
    filtered = [s for s in senders if (not status or s["status"] == status) and
                (not query or any(query in _search_text(s[k]) for k in ("name", "nickname", "phone")))]
    filtered.sort(key=lambda s: (-s["message_count"], _search_text(s["name"]), s["key"]))
    return {"senders": filtered[offset:offset + limit], "total": len(filtered), "summary": summary,
            "offset": offset, "limit": limit}
