"""Rule-based extraction of named physical facilities from NER place entities.

spaCy correctly finds ``Gravelines`` but its NER labels do not express that
"elektrownia jądrowa Gravelines" is a separate real-world object.  This
module adds that semantic layer conservatively: a facility is emitted only
when a known object-type phrase is immediately followed by an already-detected
place mention.  It never infers an owner or operator from a co-occurring
organization.
"""

from __future__ import annotations

import re

from sqlalchemy import delete, func, select

from library.db.models import DocumentEntity, DocumentFacility, Facility

FACILITY_PATTERNS = (
    ("nuclear_power_plant", "Elektrownia jądrowa", re.compile(r"\belektrowni(?:a|ę|i)?\s+jądrow(?:ej|a)\s+", re.IGNORECASE)),
    ("power_plant", "Elektrownia", re.compile(r"\belektrowni(?:a|ę|i)?\s+", re.IGNORECASE)),
    ("refinery", "Rafineria", re.compile(r"\brafineri[aię]\s+", re.IGNORECASE)),
    ("airport", "Lotnisko", re.compile(r"\blotnisk[ou]\s+", re.IGNORECASE)),
    ("seaport", "Port", re.compile(r"\bpor[tc]ie\s+", re.IGNORECASE)),
)


def extract_facility_candidates(text: str, place_entities: list[DocumentEntity]) -> list[dict]:
    """Return grounded facility candidates based on an existing place mention."""
    result: dict[tuple[str, str], dict] = {}
    for place in place_entities:
        names = [place.entity_text, *(place.variants or [])]
        for name in dict.fromkeys(value for value in names if value):
            escaped = re.escape(name)
            for facility_type, display_type, prefix in FACILITY_PATTERNS:
                match = re.search(prefix.pattern + rf"({escaped})(?![\w-])", text, prefix.flags)
                if match is None:
                    continue
                raw_mention = match.group(0).strip()
                canonical_name = f"{display_type} {place.entity_text}"
                key = (facility_type, place.entity_text.casefold())
                # A later bare "elektrownia Gravelines" is a shorter mention
                # of the already recognised nuclear plant, not a second site.
                # Prefer the more specific facility type and merge its count.
                specific_key = ("nuclear_power_plant", place.entity_text.casefold())
                if facility_type == "power_plant" and specific_key in result:
                    result[specific_key]["mention_count"] += len(re.findall(
                        prefix.pattern + rf"{escaped}(?![\w-])", text, prefix.flags,
                    ))
                    continue
                previous = result.get(key)
                if previous is None:
                    result[key] = {
                        "canonical_name": canonical_name,
                        "facility_type": facility_type,
                        "place_entity": place,
                        "raw_mention": raw_mention,
                        "mention_count": len(re.findall(prefix.pattern + rf"{escaped}(?![\w-])", text, prefix.flags)),
                    }
                else:
                    previous["mention_count"] += len(re.findall(prefix.pattern + rf"{escaped}(?![\w-])", text, prefix.flags))
    return list(result.values())


def refresh_document_facilities(session, document_id: int, text: str) -> list[DocumentFacility]:
    """Replace automatic facility links after NER has supplied place entities."""
    session.execute(delete(DocumentFacility).where(DocumentFacility.document_id == document_id))
    places = session.scalars(select(DocumentEntity).where(
        DocumentEntity.document_id == document_id,
        DocumentEntity.entity_type.in_(("geogName", "placeName")),
    )).all()
    links: list[DocumentFacility] = []
    for candidate in extract_facility_candidates(text, list(places)):
        place = candidate["place_entity"]
        geocode = place.geocode if place.geocode_id else None
        facility = session.scalar(select(Facility).where(
            Facility.canonical_name == candidate["canonical_name"],
            Facility.facility_type == candidate["facility_type"],
            Facility.place_name == place.entity_text,
        ))
        if facility is None:
            facility = Facility(
                canonical_name=candidate["canonical_name"], facility_type=candidate["facility_type"],
                place_name=place.entity_text, geocode_id=place.geocode_id,
                latitude=geocode.lat if geocode and geocode.resolved else None,
                longitude=geocode.lon if geocode and geocode.resolved else None,
            )
            session.add(facility)
            session.flush()
        # A facility can be detected before the asynchronous place verification
        # has filled geocode_id.  Reuse the same canonical facility later, but
        # upgrade it with the verified point instead of leaving it coordinate-less.
        if geocode is not None and geocode.resolved:
            facility.geocode_id = place.geocode_id
            facility.latitude = geocode.lat
            facility.longitude = geocode.lon
        if facility.latitude is not None and facility.longitude is not None:
            facility.location = func.ST_SetSRID(
                func.ST_MakePoint(facility.longitude, facility.latitude), 4326,
            ).cast(Facility.__table__.c.location.type)
        links.append(DocumentFacility(
            document_id=document_id, facility_id=facility.id, place_entity_id=place.id,
            raw_mention=candidate["raw_mention"], mention_count=max(1, candidate["mention_count"]),
        ))
    session.add_all(links)
    return links
