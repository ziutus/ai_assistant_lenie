"""Conservative group snapshots and exact, request-scoped contact resolution."""

import datetime as dt
import logging
import re
from collections import Counter
from types import SimpleNamespace

from sqlalchemy import or_, select, text, update

from library.chat_contact_service import (
    _default_category_id, enrich_whatsapp_contact, sender_nickname,
)
from library.contact_change_log import record_contact_change
from library.contact_phones import phone_search_digits
from library.db.models import (
    ChatMessage, Contact, WhatsappGroup, WhatsappGroupMember, WhatsappGroupMemberEvent, WhatsappSyncChat,
)
from library.whatsapp_sync_service import BridgeClient, BridgeError

logger = logging.getLogger(__name__)
LOCK_KEY = 918273647


def _utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _identities(row):
    return {value for value in (row.jid, row.lid) if value}


def _participants(raw):
    participants = raw.get("participants")
    count = raw.get("participant_count")
    if not isinstance(participants, list) or type(count) is not int or count < 0 or len(participants) != count:
        return None, "incomplete_snapshot"
    keys, identities, result = set(), set(), []
    for item in participants:
        if not isinstance(item, dict) or not isinstance(item.get("jid"), str) or not item["jid"]:
            return None, "invalid_participant"
        phone = item.get("phone") or None
        if phone is not None and (not isinstance(phone, str) or not re.fullmatch(r"[0-9]{1,30}", phone)):
            return None, "invalid_phone"
        lid = item.get("lid") or None
        if lid is not None and not isinstance(lid, str):
            return None, "invalid_participant"
        key = phone or item["jid"]
        aliases = {value for value in (item["jid"], lid) if value}
        if key in keys or identities & aliases:
            return None, "duplicate_participant"
        keys.add(key)
        identities.update(aliases)
        result.append({**item, "phone": phone, "lid": lid, "member_key": key})
    return result, None


def sync_groups(session, bridge, now=None):
    """Apply complete snapshots atomically; the caller owns the transaction."""
    now = now or _utcnow()
    if now.tzinfo:
        now = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
    if session.get_bind().dialect.name == "postgresql":
        if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_KEY}):
            return {"status": "busy"}
    snapshots = bridge.groups()
    if not isinstance(snapshots, list):
        raise BridgeError("invalid groups snapshot")
    jids = [g.get("jid") if isinstance(g, dict) else None for g in snapshots]
    if any(not isinstance(j, str) or not j for j in jids) or len(set(jids)) != len(jids):
        raise BridgeError("invalid groups snapshot")
    groups = {g.jid: g for g in session.scalars(select(WhatsappGroup))}
    if not snapshots and any(g.is_active for g in groups.values()):
        raise BridgeError("empty groups snapshot")
    conversations = dict(session.execute(select(WhatsappSyncChat.jid, WhatsappSyncChat.conversation_id)).all())
    counts = {"groups": len(snapshots), "new": 0, "joins": 0, "leaves": 0, "skipped": []}
    for raw in snapshots:
        participants, reason = _participants(raw)
        group = groups.get(raw["jid"])
        members = list(session.scalars(select(WhatsappGroupMember).where(
            WhatsappGroupMember.group_id == group.id))) if group else []
        by_key = {m.member_key: m for m in members}
        by_alias = {alias: m for m in members for alias in _identities(m)}
        matched = []
        if not reason:
            for item in participants:
                aliases = {a for a in (item["jid"], item["lid"]) if a}
                candidates = {by_alias[a] for a in aliases if a in by_alias}
                if item["member_key"] in by_key:
                    candidates.add(by_key[item["member_key"]])
                if len(candidates) > 1:
                    reason = "ambiguous_identity"
                    break
                member = next(iter(candidates), None)
                if member is not None and member in matched:
                    reason = "duplicate_identity"
                    break
                matched.append(member)
            active = [m for m in members if m.left_at is None]
            absent = [m for m in active if m not in matched]
            if len(active) > 10 and len(absent) > len(active) / 2:
                reason = "mass_departure"
        if reason:
            logger.warning("Skipping WhatsApp group snapshot: %s", reason)
            counts["skipped"].append({"group_id": group.id if group else None, "reason": reason})
            continue
        if group is None:
            group = WhatsappGroup(jid=raw["jid"], first_seen_at=now)
            session.add(group)
            session.flush()
            groups[group.jid] = group
            counts["new"] += 1
        previous = group.last_synced_at
        baseline = group.baseline_at is None
        for key in ("name", "is_community", "is_announce", "is_default_sub", "participant_count"):
            setattr(group, key, raw.get(key, "" if key == "name" else False))
        group.parent_jid = raw.get("parent_jid") or None
        group.conversation_id = conversations.get(group.jid)
        group.is_active = True
        for item, member in zip(participants, matched):
            joined = member is None or member.left_at is not None
            if member is None:
                member = WhatsappGroupMember(group_id=group.id, first_seen_at=now)
                session.add(member)
            # A later hidden phone must not undo a previously resolved identity.
            if item["phone"] or not member.phone:
                member.member_key = item["member_key"]
                member.phone = item["phone"]
            member.jid = item["jid"]
            member.lid = item["lid"] or member.lid
            member.display_name = item.get("display_name") or ""
            member.is_admin = bool(item.get("is_admin"))
            member.is_super_admin = bool(item.get("is_super_admin"))
            member.last_seen_at = now
            member.left_at = None
            if joined and not baseline:
                _event(session, member, "join", now, previous)
                counts["joins"] += 1
        for member in absent:
            member.left_at = now
            if not baseline:
                _event(session, member, "leave", now, previous)
                counts["leaves"] += 1
        group.baseline_at = group.baseline_at or now
        group.last_synced_at = now
    # An incomplete response is not evidence that other groups disappeared.
    if not counts["skipped"]:
        for jid, group in groups.items():
            if jid not in jids:
                group.is_active = False
    session.flush()
    return counts


def _event(session, member, kind, now, previous):
    session.add(WhatsappGroupMemberEvent(
        group_id=member.group_id, member_key=member.member_key, event_type=kind,
        phone=member.phone, display_name=member.display_name, detected_at=now, previous_synced_at=previous,
    ))


class ContactIndex:
    """Three bounded queries per request, never suffix or display-name matching."""

    def __init__(self, session, members):
        self.contacts = {c.id: c for c in session.scalars(select(Contact))}
        self.phones = {}
        for contact in self.contacts.values():
            values = [contact.phone_number] + [
                v.get("value") if isinstance(v, dict) else v for v in (contact.phone_numbers or [])]
            for value in values:
                digits = phone_search_digits(value) if isinstance(value, str) else None
                if digits:
                    self.phones.setdefault(digits, contact)
        aliases = {a for member in members for a in _identities(member)}
        self.jids = {}
        if aliases:
            rows = session.execute(select(ChatMessage.wa_sender_jid, ChatMessage.wa_sender_alt_jid,
                                          ChatMessage.contact_id).where(
                ChatMessage.contact_id.is_not(None), ChatMessage.is_from_me.is_not(True),
                or_(ChatMessage.wa_sender_jid.in_(aliases), ChatMessage.wa_sender_alt_jid.in_(aliases)),
            ).distinct().order_by(ChatMessage.contact_id))
            for jid, lid, contact_id in rows:
                if contact_id in self.contacts:
                    for alias in (jid, lid):
                        if alias:
                            self.jids.setdefault(alias, self.contacts[contact_id])

    def resolve(self, member):
        return (self.contacts.get(member.contact_id) or self.phones.get(member.phone) or
                self.jids.get(member.jid) or self.jids.get(member.lid))


def contact_dict(contact):
    if contact is None:
        return None
    return {"id": contact.id, "display_name": contact.display_label or
            f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None}


def iso(value):
    return value.isoformat() if value else None


def member_dict(member, index):
    contact = index.resolve(member)
    status = "in_contacts" if contact else "missing" if member.phone else "unverified"
    return {"id": member.id, "phone": member.phone, "display_name": member.display_name,
            "is_admin": member.is_admin or member.is_super_admin, "status": status,
            "contact": contact_dict(contact), "first_seen_at": iso(member.first_seen_at),
            "left_at": iso(member.left_at), "can_add": status == "missing" and member.left_at is None}


def member_summary(members, index):
    statuses = Counter(member_dict(m, index)["status"] for m in members if m.left_at is None)
    return {"active": sum(statuses.values()), **{k: statuses[k] for k in ("in_contacts", "missing", "unverified")}}


def group_dict(group, groups, members, index, events):
    summary = member_summary(members, index)
    cutoff = _utcnow() - dt.timedelta(days=7)
    recent = Counter(e.event_type for e in events if e.detected_at >= cutoff)
    parent = next((g.id for g in groups if g.jid == group.parent_jid), None)
    return {"id": group.id, "jid": group.jid, "name": group.name, "is_community": group.is_community,
            "parent_id": parent, "is_announce": group.is_announce, "is_default_sub": group.is_default_sub,
            "participant_count": group.participant_count, "active_members": summary.pop("active"), **summary,
            "joins_7d": recent["join"], "leaves_7d": recent["leave"],
            "last_synced_at": iso(group.last_synced_at), "conversation_id": group.conversation_id}


def create_contact_from_member(session, member, *, category_id=None, fetch_photo=False, bridge=None, index=None):
    """Link exact known identities, otherwise create an active, numbered member."""
    if member.left_at is not None:
        return {"outcome": "skipped", "reason": "inactive_member"}
    index = index or ContactIndex(session, [member])
    contact = index.resolve(member)
    if contact:
        member.contact_id = contact.id
        return {"outcome": "linked_existing", "contact_id": contact.id}
    if not member.phone:
        return {"outcome": "skipped", "reason": "unknown_phone"}
    aliases = _identities(member)
    messages = list(session.scalars(select(ChatMessage).where(
        ChatMessage.is_from_me.is_not(True),
        or_(ChatMessage.wa_sender_jid.in_(aliases), ChatMessage.wa_sender_alt_jid.in_(aliases)),
    ).order_by(ChatMessage.sent_at.desc(), ChatMessage.id.desc())))
    nickname = next((sender_nickname(m) for m in messages if sender_nickname(m)), None)
    contact = Contact(category_id=category_id or _default_category_id(session),
                      display_label=nickname[:200] if nickname else None,
                      last_name=None if nickname else f"+{member.phone}", phone_number=f"+{member.phone}")
    session.add(contact)
    session.flush()
    group = session.get(WhatsappGroup, member.group_id)
    conversation = SimpleNamespace(display_name=group.name)
    message = SimpleNamespace(wa_sender_jid=member.jid)
    enrich_whatsapp_contact(session, contact, conversation, message, member.phone, nickname,
                            bridge=bridge, fetch_photo=fetch_photo)
    session.execute(update(ChatMessage).where(
        ChatMessage.contact_id.is_(None), ChatMessage.is_from_me.is_not(True),
        or_(ChatMessage.wa_sender_jid.in_(aliases), ChatMessage.wa_sender_alt_jid.in_(aliases)),
    ).values(contact_id=contact.id))
    member.contact_id = contact.id
    record_contact_change(session, contact, "other", changed_fields=["created_from_whatsapp"],
                          note=f"Kanał WhatsApp: {group.name}")
    return {"outcome": "created", "contact_id": contact.id}


def execute_whatsapp_groups_sync(session, job):
    from library.config_loader import load_config

    config = load_config()
    url, token = config.get("WHATSAPP_BRIDGE_URL"), config.get("WHATSAPP_BRIDGE_TOKEN")
    if not url or not token:
        return {"status": "not_configured"}
    return sync_groups(session, BridgeClient(url, token))
