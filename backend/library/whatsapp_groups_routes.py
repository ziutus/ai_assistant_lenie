"""Private group membership, membership intervals, and explicit contact creation."""

import logging
from collections import defaultdict

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from werkzeug.exceptions import HTTPException

from library.chat_routes import _authorized, _bridge
from library.chat_senders_service import _search_text
from library.db.engine import get_scoped_session
from library.db.models import Contact, ContactCategory, WhatsappGroup, WhatsappGroupMember, WhatsappGroupMemberEvent
from library.whatsapp_groups_service import (
    ContactIndex, contact_dict, create_contact_from_member, group_dict, iso, member_dict, member_summary,
)

logger = logging.getLogger(__name__)
bp = Blueprint("whatsapp_groups", __name__)
bp.before_request(_authorized)


def _error(message, code=400):
    return jsonify(status="error", message=message), code


@bp.errorhandler(Exception)
def _failure(exc):
    if isinstance(exc, HTTPException):
        return _error(exc.name, exc.code)
    get_scoped_session().rollback()
    logger.error("WhatsApp groups request failed (%s)", type(exc).__name__)
    return _error("Could not process groups request", 500)


def _pagination():
    try:
        offset = max(0, int(request.args.get("offset", 0)))
        limit = min(500, max(1, int(request.args.get("limit", 200))))
    except ValueError:
        return None
    return offset, limit


def _load(session, group_id=None):
    groups = list(session.scalars(select(WhatsappGroup).order_by(WhatsappGroup.name, WhatsappGroup.id)))
    mq, eq = select(WhatsappGroupMember), select(WhatsappGroupMemberEvent)
    if group_id is not None:
        mq = mq.where(WhatsappGroupMember.group_id == group_id)
        eq = eq.where(WhatsappGroupMemberEvent.group_id == group_id)
    members = list(session.scalars(mq.order_by(WhatsappGroupMember.id)))
    events = list(session.scalars(eq.order_by(WhatsappGroupMemberEvent.detected_at.desc(),
                                             WhatsappGroupMemberEvent.id.desc())))
    return groups, members, events, ContactIndex(session, members)


@bp.get("/whatsapp_groups")
def list_groups():
    groups, members, events, index = _load(get_scoped_session())
    by_group, events_by_group = defaultdict(list), defaultdict(list)
    for member in members:
        by_group[member.group_id].append(member)
    for event in events:
        events_by_group[event.group_id].append(event)
    result = [group_dict(g, groups, by_group[g.id], index, events_by_group[g.id]) for g in groups if g.is_active]
    communities = sum(g["is_community"] for g in result)
    return jsonify(status="success", groups=result, summary={"groups": len(result) - communities,
                                                             "communities": communities})


@bp.get("/whatsapp_groups/<int:group_id>/members")
def list_members(group_id):
    session = get_scoped_session()
    group = session.get(WhatsappGroup, group_id)
    if group is None:
        return _error("Group not found", 404)
    pagination = _pagination()
    state, status = request.args.get("state", "active"), request.args.get("status")
    if pagination is None or state not in {"active", "left", "all"} or status not in {
        None, "", "in_contacts", "missing", "unverified",
    }:
        return _error("Invalid filters or pagination")
    offset, limit = pagination
    groups, members, events, index = _load(session, group_id)
    query = _search_text(request.args.get("q", ""))
    result = []
    for member in members:
        row = member_dict(member, index)
        if state != "all" and (member.left_at is None) != (state == "active"):
            continue
        if status and row["status"] != status:
            continue
        if query and not any(query in _search_text(value) for value in (
            row["phone"], row["display_name"], (row["contact"] or {}).get("display_name"),
        )):
            continue
        result.append(row)
    return jsonify(status="success", group=group_dict(group, groups, members, index, events),
                   members=result[offset:offset + limit], total=len(result),
                   summary=member_summary(members, index), offset=offset, limit=limit)


@bp.get("/whatsapp_groups/<int:group_id>/events")
def list_events(group_id):
    session = get_scoped_session()
    if session.get(WhatsappGroup, group_id) is None:
        return _error("Group not found", 404)
    pagination, kind = _pagination(), request.args.get("type")
    if pagination is None or kind not in {None, "", "join", "leave"}:
        return _error("Invalid filters or pagination")
    offset, limit = pagination
    _, members, events, index = _load(session, group_id)
    by_key = {m.member_key: m for m in members}
    # Old LID event keys remain valid after the member obtains a phone number.
    for member in members:
        for alias in (member.jid, member.lid):
            if alias:
                by_key.setdefault(alias, member)
    filtered = [e for e in events if not kind or e.event_type == kind]
    result = []
    for event in filtered[offset:offset + limit]:
        member = by_key.get(event.member_key)
        contact = index.resolve(member) if member else index.phones.get(event.phone)
        result.append({"id": event.id, "event_type": event.event_type, "phone": event.phone,
                       "display_name": event.display_name, "contact": contact_dict(contact),
                       "detected_at": iso(event.detected_at), "previous_synced_at": iso(event.previous_synced_at)})
    return jsonify(status="success", events=result, total=len(filtered), offset=offset, limit=limit)


@bp.post("/whatsapp_groups/<int:group_id>/members/add_contacts")
def add_contacts(group_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error("Expected an object")
    ids = body.get("member_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(type(i) is not int for i in ids):
        return _error("Expected 1 to 50 integer member_ids")
    if ("category_id" in body and type(body["category_id"]) is not int or
            "fetch_photo" in body and type(body["fetch_photo"]) is not bool):
        return _error("Invalid category_id or fetch_photo")
    session = get_scoped_session()
    if session.get(WhatsappGroup, group_id) is None:
        return _error("Group not found", 404)
    if "category_id" in body and session.get(ContactCategory, body["category_id"]) is None:
        return _error("Unknown category_id")
    members = {m.id: m for m in session.scalars(select(WhatsappGroupMember).where(
        WhatsappGroupMember.group_id == group_id, WhatsappGroupMember.id.in_(ids)))}
    index = ContactIndex(session, members.values())
    counts = dict.fromkeys(("created", "linked_existing", "skipped", "error"), 0)
    results = []
    bridge = _bridge() if body.get("fetch_photo", False) else None
    for member_id in ids:
        member = members.get(member_id)
        try:
            with session.begin_nested():
                if member is None:
                    result = {"outcome": "skipped", "reason": "not_in_group"}
                elif member.contact_id is not None:
                    result = {"outcome": "skipped", "reason": "already_in_contacts"}
                else:
                    result = create_contact_from_member(
                        session, member, category_id=body.get("category_id"),
                        fetch_photo=body.get("fetch_photo", False), bridge=bridge, index=index,
                    )
            if result["outcome"] in {"created", "linked_existing"}:
                contact = session.get(Contact, result["contact_id"])
                index.contacts[contact.id] = contact
                if member.phone:
                    index.phones[member.phone] = contact
        except Exception:
            logger.error("Creating a WhatsApp group contact failed")
            result = {"outcome": "error", "reason": "could_not_create_contact"}
        counts[result["outcome"]] += 1
        results.append({"member_id": member_id, **result})
    session.commit()
    return jsonify(status="success", results=results, counts=counts)


@bp.post("/whatsapp_groups/sync")
def enqueue_sync():
    from library.job_queue import enqueue

    job = enqueue(get_scoped_session(), "whatsapp_groups_sync")
    return jsonify(status="success", job_id=str(job.id)), 202
