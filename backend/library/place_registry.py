"""Cross-document view of places: browse, Wikipedia link and alias profile.

Places are stored per document (``document_entities``); this module groups them by case-folded name and
joins the curated ``place_profiles`` row (matched by canonical name or alias). Nothing here writes to
``document_entities``.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy import func, or_, select

from library.db.models import Document, DocumentEntity, PlaceProfile

PLACE_TYPES = ("geogName", "placeName")
MAX_ALIASES = 20


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().casefold()


def normalize_wikipedia_url(url: str | None) -> str | None:
    """Return an https ``*.wikipedia.org/wiki/...`` URL, None for an empty value, ValueError otherwise."""
    value = (url or "").strip()
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not (host == "wikipedia.org" or host.endswith(".wikipedia.org")):
        raise ValueError("Adres musi wskazywać artykuł Wikipedii (np. https://pl.wikipedia.org/wiki/Janbu).")
    if not parsed.path.startswith("/wiki/") or len(parsed.path) <= len("/wiki/"):
        raise ValueError("Adres musi wskazywać artykuł Wikipedii (ścieżka /wiki/…).")
    return parsed._replace(scheme="https", fragment="").geturl()


def profile_index(session) -> dict[str, PlaceProfile]:
    """Every profile reachable by its canonical key or any alias key."""
    index: dict[str, PlaceProfile] = {}
    for profile in session.scalars(select(PlaceProfile)).all():
        index[profile.name_key] = profile
    for profile in session.scalars(select(PlaceProfile)).all():
        for alias in profile.aliases or []:
            index.setdefault(name_key(alias), profile)
    return index


def profile_to_dict(profile: PlaceProfile | None) -> dict | None:
    if profile is None:
        return None
    return {"id": profile.id, "canonical_name": profile.canonical_name, "wikipedia_url": profile.wikipedia_url,
            "aliases": list(profile.aliases or []), "note": profile.note}


def upsert_profile(session, name: str, *, wikipedia_url: str | None = None, aliases: list[str] | None = None,
                   note: str | None = None, set_fields: set[str]) -> PlaceProfile:
    """Create or update the profile named ``name``; only ``set_fields`` are written (others are kept)."""
    clean = re.sub(r"\s+", " ", name or "").strip()
    if not clean or len(clean) > 500:
        raise ValueError("Nazwa miejsca musi mieć od 1 do 500 znaków.")
    key = name_key(clean)
    profile = session.scalar(select(PlaceProfile).where(PlaceProfile.name_key == key))
    if profile is None:
        # Writing under an alias of an existing profile edits that profile instead of forking a second one.
        profile = profile_index(session).get(key)
    if profile is None:
        profile = PlaceProfile(canonical_name=clean, name_key=key, aliases=[])
        session.add(profile)
    if "wikipedia_url" in set_fields:
        profile.wikipedia_url = normalize_wikipedia_url(wikipedia_url)
    if "aliases" in set_fields:
        cleaned: list[str] = []
        for alias in aliases or []:
            alias = re.sub(r"\s+", " ", alias or "").strip()
            if alias and name_key(alias) != profile.name_key and alias.casefold() not in {a.casefold() for a in cleaned}:
                cleaned.append(alias)
        if len(cleaned) > MAX_ALIASES:
            raise ValueError(f"Najwyżej {MAX_ALIASES} aliasów.")
        profile.aliases = cleaned
    if "note" in set_fields:
        profile.note = (note or "").strip() or None
    session.flush()
    return profile


def list_places(session, *, query: str = "", only_with_wikipedia: bool = False, limit: int = 50, offset: int = 0):
    """Places grouped by case-folded name across all documents, most documents first."""
    key = func.lower(DocumentEntity.entity_text)
    statement = (
        select(
            key.label("key"),
            func.min(DocumentEntity.entity_text).label("name"),
            func.count(func.distinct(DocumentEntity.document_id)).label("documents"),
            func.sum(DocumentEntity.mention_count).label("mentions"),
            func.bool_or(DocumentEntity.geocode_id.is_not(None)).label("located"),
        )
        .where(DocumentEntity.entity_type.in_(PLACE_TYPES),
               or_(DocumentEntity.place_verification_status.is_(None),
                   DocumentEntity.place_verification_status != "rejected"))
        .group_by(key)
    )
    needle = (query or "").strip().replace("%", "").replace("_", "")
    if needle:
        statement = statement.where(func.unaccent(DocumentEntity.entity_text).ilike(func.unaccent(f"%{needle}%")))
    index = profile_index(session)
    if only_with_wikipedia:
        keys = [k for k, p in index.items() if p.wikipedia_url]
        statement = statement.where(key.in_(keys or [""]))
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.execute(statement.order_by(func.count(func.distinct(DocumentEntity.document_id)).desc(), key)
                           .limit(limit).offset(offset)).all()
    from library.country_gazetteer import canonical_country_name

    items = []
    for row in rows:
        items.append({
            "key": row.key, "name": row.name, "documents": row.documents, "mentions": int(row.mentions or 0),
            "located": bool(row.located), "is_country": canonical_country_name(row.name) is not None,
            "profile": profile_to_dict(index.get(row.key)),
        })
    return items, total


def place_detail(session, name: str, *, document_limit: int = 200) -> dict:
    """Profile (if any) and documents mentioning the place under its name or any alias."""
    key = name_key(name)
    profile = profile_index(session).get(key)
    keys = {key}
    if profile is not None:
        keys |= {profile.name_key, *(name_key(a) for a in profile.aliases or [])}
    rows = session.execute(
        select(
            Document.id, Document.title, Document.document_type,
            func.sum(DocumentEntity.mention_count).label("mentions"),
            func.array_agg(func.distinct(DocumentEntity.entity_text)).label("forms"),
        )
        .join(DocumentEntity, DocumentEntity.document_id == Document.id)
        .where(DocumentEntity.entity_type.in_(PLACE_TYPES), func.lower(DocumentEntity.entity_text).in_(keys),
               or_(DocumentEntity.place_verification_status.is_(None),
                   DocumentEntity.place_verification_status != "rejected"))
        .group_by(Document.id)
        .order_by(func.sum(DocumentEntity.mention_count).desc(), Document.id.desc())
        .limit(document_limit)
    ).all()
    return {
        "name": profile.canonical_name if profile is not None else name,
        "profile": profile_to_dict(profile),
        "documents": [{"id": r.id, "title": r.title, "document_type": r.document_type,
                       "mentions": int(r.mentions or 0), "forms": sorted(r.forms or [])} for r in rows],
    }
