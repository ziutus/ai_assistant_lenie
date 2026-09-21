"""Shared parsing/sender-resolution helpers for WhatsApp "Export chat" files.

Used by two independent import paths that both start from the same raw
export format but persist different things:
- ``imports/whatsapp_neighbor_profiles.py`` — LLM-extracted per-person
  profile facts, written to ``Contact.whatsapp_profile``.
- ``imports/whatsapp_chat_import.py`` — full message log + attachments,
  written to ``chat_messages``/``chat_conversations``.

Kept here rather than duplicated so a parser fix (e.g. a new WhatsApp export
line format) only has to happen once.
"""

import csv
import re
from datetime import datetime

DATE_PREFIX_RE = re.compile(r"^‎?(\d{1,2}\.\d{1,2}\.\d{2,4}), (\d{1,2}:\d{2}) - (.*)$")
SENDER_CONTENT_RE = re.compile(r"^([^:]+): (.*)$")
NOISE_CONTENT = {
    "ta wiadomość została usunięta",
    "usunięto tę wiadomość",
    "<pominięto multimedia>",
    "usunąłeś to zdjęcie",
    "usunęła to zdjęcie",
}
MIN_CONTENT_LEN = 6

# WhatsApp's own export line for an attachment: "<filename> (załączony plik)",
# with a leading U+200E left-to-right mark stripped by parse_export() already.
ATTACHMENT_RE = re.compile(r"^(.+?) \(załączony plik\)$", re.IGNORECASE)

# Some attachments (observed for documents, not photos) instead show as a bare
# "<Pominięto multimedia>" line followed immediately by the filename on its own
# line with no timestamp — parse_export() folds that continuation line into
# the same message's content, separated by "\n".
SKIPPED_MEDIA_WITH_NAME_RE = re.compile(r"^<Pomini[eę]to multimedia>\n(.+)$", re.IGNORECASE)

MEDIA_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "video": {".mp4", ".mov", ".avi"},
    "audio": {".opus", ".mp3", ".m4a", ".ogg", ".wav"},
    "contact_card": {".vcf"},
}


def parse_export(txt_path: str) -> list[dict]:
    """Parse a WhatsApp 'Export chat' .txt file into a list of message dicts.

    System/group events (added/removed/renamed/encryption notice — lines with
    no 'Sender: content' shape) are discarded rather than merged into the
    previous message, so they can't pollute a person's corpus.
    """
    messages = []
    current = None
    with open(txt_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n").lstrip("﻿")
            date_match = DATE_PREFIX_RE.match(line)
            if date_match:
                date_s, time_s, rest = date_match.groups()
                rest = rest.lstrip("‎")
                msg_match = None if rest.startswith("~") else SENDER_CONTENT_RE.match(rest)
                if msg_match and msg_match.group(2).lstrip("‎").startswith("~"):
                    # "Dodano: ~ Imię" / similar member-added system events —
                    # colon makes it look like a real sender:content message
                    msg_match = None
                if msg_match:
                    if current:
                        messages.append(current)
                    sender, content = msg_match.groups()
                    current = {
                        "date": _parse_date(date_s),
                        "date_str": date_s,
                        "time": time_s,
                        "sender": sender.strip(),
                        "content": content.lstrip("‎"),
                    }
                else:
                    # system/group event or the encryption notice — not a message
                    if current:
                        messages.append(current)
                    current = None
                continue
            if current is not None and line:
                current["content"] += "\n" + line
        if current:
            messages.append(current)
    return messages


def _parse_date(date_s: str):
    try:
        day, month, year = date_s.split(".")
        year = ("20" + year) if len(year) == 2 else year
        return datetime(int(year), int(month), int(day))
    except ValueError:
        return None


def message_datetime(m: dict):
    d = _parse_date(m["date_str"])
    if d is None:
        return None
    try:
        h, mi = m["time"].split(":")
        return d.replace(hour=int(h), minute=int(mi))
    except (ValueError, AttributeError):
        return d


def parse_meta_timestamp(s: str | None):
    """Parse a stored 'DD.MM.YYYY, HH:MM' watermark back into a datetime."""
    if not s or "," not in s:
        return None
    date_part, _, time_part = s.partition(",")
    d = _parse_date(date_part.strip())
    if d is None:
        return None
    try:
        h, mi = time_part.strip().split(":")
        return d.replace(hour=int(h), minute=int(mi))
    except (ValueError, AttributeError):
        return d


def is_noise(content: str) -> bool:
    c = content.strip()
    if len(c) < MIN_CONTENT_LEN:
        return True
    return c.lower() in NOISE_CONTENT


def is_deleted(content: str) -> bool:
    c = content.strip().lower()
    return c in ("ta wiadomość została usunięta", "usunięto tę wiadomość") or c.startswith("usun") and "zdjęcie" in c


def parse_attachment(content: str) -> tuple[str, bool] | None:
    """Detect an attachment reference in a message's content.

    Returns ``(filename, embedded)`` or ``None`` if the content isn't an
    attachment line. ``embedded=True`` means the file should be present in
    the export archive at that name (WhatsApp's "<filename> (załączony
    plik)" line); ``embedded=False`` means WhatsApp only recorded the
    filename but excluded the actual bytes from the export (observed for
    some documents as "<Pominięto multimedia>" followed by the filename on
    its own line, no timestamp — usually because the export's per-file/total
    size limit was hit), so no media upload is possible for that message.
    """
    stripped = content.strip()
    m = ATTACHMENT_RE.match(stripped)
    if m:
        return m.group(1).strip(), True
    m = SKIPPED_MEDIA_WITH_NAME_RE.match(stripped)
    if m:
        return m.group(1).strip(), False
    return None


def guess_media_type(filename: str) -> str:
    """Map a filename extension to a chat_messages.message_type bucket.
    Falls back to 'document' for anything not explicitly known (pdf, docx,
    xlsx, pptx, odt, ods, ...)."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for media_type, extensions in MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    return "document"


def is_phone_number(sender: str) -> bool:
    return bool(re.match(r"^\+?[\d\s]{7,}$", sender.strip()))


def normalize_name(value: str) -> set[str]:
    from unidecode import unidecode

    value = unidecode(value).lower()
    return {tok for tok in re.split(r"[^a-z]+", value) if tok}


_UNKNOWN_CONTACT_NAME_RE = re.compile(r"^(nieznan\w*|unkonwn|unknown)$", re.IGNORECASE)


def strip_sender_suffix(display_name: str, suffix: str | None) -> str:
    """Strip a trailing ' - <suffix>' community tag (the household's own WhatsApp
    display-name convention, e.g. " - Tuwima Gardens") from a whole display name.

    Contacts in the private contact book never carry this suffix (google_contacts_import.py
    strips it at import time into a contact_groups membership instead), so matching a raw
    WhatsApp sender name against the contact book without stripping it first never finds a
    match — normalize_name() would fold the suffix's own words into the comparison key.
    """
    if not suffix:
        return display_name
    suffix_re = re.compile(r"\s*-\s*" + re.escape(suffix) + r"\s*$", re.IGNORECASE)
    return suffix_re.sub("", display_name).strip()


def load_contacts(csv_path: str, suffix: str | None = None) -> dict[str, str]:
    """Load a Google Contacts CSV export into a normalized-phone-digits -> display-name map.

    Only First/Last Name + the two phone columns are used. A trailing " - <suffix>"
    community tag on the last name (this export's convention for marking neighbor
    contacts, e.g. " - Tuwima Gardens") is stripped from the display name, and
    placeholder "unknown" entries are skipped so they can never overwrite a
    phone-only sender's title with a non-name.

    Each number is keyed both by its full digit string and by its last 9 digits (a
    bare Polish local number, no "+48") so a WhatsApp export number with a country
    code still matches a contact stored without one, and vice versa — unless that
    9-digit suffix collides across two different contacts, in which case the
    ambiguous fallback key is dropped rather than guessed.
    """
    suffix_re = re.compile(r"\s*-\s*" + re.escape(suffix) + r"\s*$", re.IGNORECASE) if suffix else None
    full: dict[str, str] = {}
    last9: dict[str, str | None] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # The community suffix can land on either column (e.g. First Name=" - Tuwima
            # Gardens" with no surname), and a name part can itself be a placeholder (e.g.
            # Last Name="unkonwn - Tuwima Gardens") while the other part is a real name —
            # so each part is stripped/filtered independently, not the joined name as a whole.
            parts = []
            for col in ("First Name", "Last Name"):
                token = (row.get(col) or "").strip()
                if suffix_re:
                    token = suffix_re.sub("", token).strip()
                if token and not _UNKNOWN_CONTACT_NAME_RE.match(token):
                    parts.append(token)
            name = " ".join(parts)
            if not name:
                continue
            for col in ("Phone 1 - Value", "Phone 2 - Value"):
                digits = re.sub(r"\D", "", row.get(col) or "")
                if len(digits) < 7:
                    continue
                full[digits] = name
                key9 = digits[-9:]
                if key9 in last9 and last9[key9] != name:
                    last9[key9] = None  # ambiguous — two different contacts share this local number
                else:
                    last9.setdefault(key9, name)
    for key9, name in last9.items():
        if name is not None:
            full.setdefault(key9, name)
    return full


def resolve_phone_sender(sender: str, contacts: dict[str, str]) -> str | None:
    digits = re.sub(r"\D", "", sender)
    if not digits:
        return None
    return contacts.get(digits) or contacts.get(digits[-9:])


def load_contact_phone_index(session) -> dict[str, int]:
    """Existing Contact.phone_number values -> contact id, digits-only with the
    same full/last-9-digits fallback as load_contacts()."""
    from sqlalchemy import select

    from library.db.models import Contact

    full: dict[str, int] = {}
    last9: dict[str, int | None] = {}
    for c in session.scalars(select(Contact).where(Contact.phone_number.is_not(None))):
        digits = re.sub(r"\D", "", c.phone_number or "")
        if len(digits) < 7:
            continue
        full[digits] = c.id
        key9 = digits[-9:]
        if key9 in last9 and last9[key9] != c.id:
            last9[key9] = None
        else:
            last9.setdefault(key9, c.id)
    for key9, cid in last9.items():
        if cid is not None:
            full.setdefault(key9, cid)
    return full


def load_contact_name_index(session) -> dict[str, int]:
    """Existing contacts' normalized full-name key -> contact id.

    A key shared by more than one contact (e.g. several bare-first-name-only
    "Agnieszka"/"Grzegorz" entries with no surname to disambiguate) is
    dropped rather than pointing at an arbitrary one of them — see
    feedback_no_merge_unverifiable_contacts.md. Picking "whichever contact
    happened to be seen first" would silently attach a WhatsApp profile to
    the wrong real person.
    """
    from sqlalchemy import select

    from library.db.models import Contact

    index: dict[str, int | None] = {}
    for c in session.scalars(select(Contact)):
        key = " ".join(sorted(normalize_name(f"{c.first_name or ''} {c.last_name}")))
        if not key:
            continue
        if key in index and index[key] != c.id:
            index[key] = None  # ambiguous
        else:
            index.setdefault(key, c.id)
    return {k: v for k, v in index.items() if v is not None}


def split_display_name(display_name: str) -> tuple[str | None, str]:
    """First token -> first_name, rest -> last_name. An unresolved phone-number
    sender (e.g. "+48 668 527 645") is kept whole as last_name instead — splitting
    it on whitespace would put "+48" in first_name and the rest of the digits in
    last_name."""
    display_name = display_name.strip()
    if is_phone_number(display_name):
        return None, display_name
    parts = display_name.split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, display_name


def find_or_create_contact(session, display_name: str, phone: str | None, default_category_id: int,
                            phone_index: dict[str, int], name_index: dict[str, int]):
    """Match an existing Contact by phone (reliable) then by normalized name, else
    create a new one. phone_index/name_index are built ONCE from the DB before the
    run and never updated with contacts created during this run — two distinct
    senders that happen to share a name (no phone for either) must never be
    silently merged into one Contact just because they were processed back to
    back (see feedback_no_merge_unverifiable_contacts.md)."""
    from library.db.models import Contact

    contact = None
    if phone:
        digits = re.sub(r"\D", "", phone)
        cid = phone_index.get(digits) or phone_index.get(digits[-9:])
        if cid:
            contact = session.get(Contact, cid)
    if contact is None:
        key = " ".join(sorted(normalize_name(display_name)))
        cid = name_index.get(key) if key else None
        if cid:
            contact = session.get(Contact, cid)
    is_new = contact is None
    if contact is None:
        first_name, last_name = split_display_name(display_name)
        contact = Contact(category_id=default_category_id, first_name=first_name, last_name=last_name)
        session.add(contact)
        session.flush()
    if phone and not contact.phone_number:
        contact.phone_number = phone
    return contact, is_new


def find_contact(display_name: str, phone: str | None, phone_index: dict[str, int],
                  name_index: dict[str, int]) -> int | None:
    """Resolve-only counterpart to find_or_create_contact() — looks up an existing
    contact by phone then normalized name, never creates one. Used by
    whatsapp_chat_import.py, which logs a full multi-participant message history
    and must not silently spawn a Contact for every group member it happens to
    see (that is whatsapp_neighbor_profiles.py's job, an explicit opt-in)."""
    if phone:
        digits = re.sub(r"\D", "", phone)
        cid = phone_index.get(digits) or phone_index.get(digits[-9:])
        if cid:
            return cid
    key = " ".join(sorted(normalize_name(display_name)))
    return name_index.get(key) if key else None
