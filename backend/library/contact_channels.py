"""Ordered contact channels; the first entry is the primary (legacy) value.

Replace lists when editing them; in-place JSON mutations are not tracked by ORM.
"""

CHANNEL_FIELDS = {"phone_numbers": ("phone_number", 30), "email_addresses": ("email", 255)}


def channel_key(value: str, field: str) -> str:
    if field == "email_addresses":
        return value.casefold()
    return "".join(c for c in value if c not in " ()-.")


def normalize_channels(value, field: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > 50:
        raise ValueError(f"{field} may contain at most 50 entries")
    result, seen = [], set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) - {"value", "label"}:
            raise ValueError(f"each {field} entry must contain value and optional label")
        text, label = entry.get("value"), entry.get("label")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > CHANNEL_FIELDS[field][1]:
            raise ValueError(f"{field} value must be non-empty text of at most {CHANNEL_FIELDS[field][1]} characters")
        if label is not None and (not isinstance(label, str) or len(label.strip()) > 100):
            raise ValueError(f"{field} label must be text of at most 100 characters")
        text = text.strip()
        key = channel_key(text, field)
        if not key:
            raise ValueError(f"{field} value must contain more than formatting characters")
        if key in seen:
            raise ValueError(f"{field} contains duplicate values")
        seen.add(key)
        result.append({"value": text, "label": (label or "").strip() or None})
    return result


def with_legacy_primary(entries: list[dict], value: str | None, field: str) -> list[dict]:
    """Legacy edits replace/remove only the primary; additional entries survive."""
    tail = entries[1:] if entries else []
    if not value:
        return tail
    key = channel_key(value, field)
    label = next((e.get("label") for e in entries if channel_key(e["value"], field) == key), None)
    return [{"value": value, "label": label}] + [e for e in tail if channel_key(e["value"], field) != key]


def contact_channels(row, field: str) -> list[dict]:
    entries = getattr(row, field, None) or []
    legacy = getattr(row, CHANNEL_FIELDS[field][0], None)
    return entries or ([{"value": legacy, "label": None}] if legacy else [])


def channel_patch(data: dict, row=None) -> dict:
    """Validate the entire channel patch before mutating the contact."""
    patch = {}
    for field, (legacy, limit) in CHANNEL_FIELDS.items():
        if field not in data and legacy not in data:
            continue
        scalar = data.get(legacy)
        if legacy in data:
            if scalar is not None and (not isinstance(scalar, str) or len(scalar.strip()) > limit):
                raise ValueError(f"{legacy} must be text of at most {limit} characters")
            scalar = (scalar or "").strip() or None
        if field in data:
            entries = normalize_channels(data[field], field)
            primary = entries[0]["value"] if entries else None
            if legacy in data and scalar != primary:
                raise ValueError(f"{legacy} must match the first {field} value")
        else:
            entries = with_legacy_primary((getattr(row, field, None) or []) if row else [], scalar, field)
        patch[field] = entries
        patch[legacy] = entries[0]["value"] if entries else None
    return patch


def sync_contact_channels(_mapper, _connection, target):
    """Keep older ORM importers compatible with the new lists on flush."""
    from sqlalchemy import inspect

    state = inspect(target)
    data = {}
    for field, (legacy, _limit) in CHANNEL_FIELDS.items():
        if state.attrs[field].history.has_changes():
            data[field] = getattr(target, field)
        elif state.attrs[legacy].history.has_changes():
            data[legacy] = getattr(target, legacy)
    for key, value in channel_patch(data, target).items():
        setattr(target, key, value)
