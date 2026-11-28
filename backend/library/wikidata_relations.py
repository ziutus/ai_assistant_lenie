"""Wikidata proposals. Fetch all remote data before writing any proposal."""

import calendar
import datetime
import re
import time

import requests
from sqlalchemy import select

from library import wikidata_client
from library.country_gazetteer import detect_countries
from library.db.models import Person, PersonAlias
from library.entity_relations_detect import exact_organization
from library.entity_relations_service import RelationError, upsert_relation
from library.relation_extraction import normalized

USER_AGENT = "lenie-ai/0.3 (https://www.lenie-ai.eu) entity-relations"
PROPERTIES = {"P108": ("pracownik", "organization"), "P463": ("czlonek", "organization"),
              "P102": ("czlonek", "organization"), "P27": ("obywatel", "country"),
              "P26": ("malzonek", "person"), "P22": ("rodzic", "person"), "P25": ("rodzic", "person"),
              "P40": ("rodzic", "person"), "P3373": ("rodzenstwo", "person")}


class WikidataError(RuntimeError):
    pass


def get_entities(qids, *, delay=0):
    from library.external_service_events import observed_request
    result = {}
    qids = sorted(set(qids))
    if any(not re.fullmatch(r"Q\d{1,12}", q) for q in qids):
        raise WikidataError("Invalid Wikidata identifier")
    for index in range(0, len(qids), 50):
        if delay:
            time.sleep(delay)
        try:
            response = observed_request(
                service="wikidata", operation="wbgetentities",
                request_fn=lambda: requests.get(
                    wikidata_client.API_URL, params={"action": "wbgetentities", "format": "json",
                        "ids": "|".join(qids[index:index + 50]), "props": "claims|labels", "languages": "pl|en"},
                    headers={"User-Agent": USER_AGENT}, timeout=wikidata_client.REQUEST_TIMEOUT_S))
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("entities"), dict) or data.get("error"):
                raise ValueError("Invalid response")
            result.update(data["entities"])
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise WikidataError("Wikidata request failed") from exc
    return result


def target(claim):
    value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
    return value.get("id") if isinstance(value, dict) else None


def claims(entity, prop):
    return [r for r in entity.get("claims", {}).get(prop, []) if r.get("rank") != "deprecated" and target(r)]


def labels(entity):
    return [entity["labels"][lang]["value"] for lang in ("pl", "en")
            if entity.get("labels", {}).get(lang, {}).get("value")]


def qualifier_date(claim, prop):
    values = claim.get("qualifiers", {}).get(prop, [])
    for item in values:
        value = item.get("datavalue", {}).get("value", {})
        if not isinstance(value, dict) or value.get("precision", 0) < 9:
            continue
        match = re.match(r"\+(\d{4})-(\d{2})-(\d{2})T", value.get("time", ""))
        if not match:
            continue
        year, month, day = map(int, match.groups())
        precision = value["precision"]
        if precision == 9:
            month, day = (12, 31) if prop == "P582" else (1, 1)
        elif precision == 10:
            if not 1 <= month <= 12:
                continue
            day = calendar.monthrange(year, month)[1] if prop == "P582" else 1
        try:
            return datetime.date(year, month, day)
        except ValueError:
            continue
    return None


def resolve_target(session, kind, qid, entities):
    names = labels(entities.get(qid, {}))
    if kind == "person":
        direct = session.scalars(select(Person).where(Person.wikidata_qid == qid)).all()
        if len(direct) == 1:
            return {"type": kind, "id": direct[0].id}
        wanted = {normalized(n) for n in names}
        ids = {p.id for p in session.scalars(select(Person)) if normalized(p.canonical_name) in wanted}
        ids.update(a.person_id for a in session.scalars(select(PersonAlias)) if normalized(a.alias) in wanted)
        if len(ids) == 1:
            person = session.get(Person, ids.pop())
            if person.wikidata_qid in (None, qid):
                return {"type": kind, "id": person.id}
    elif kind == "organization":
        hits = {org.id for name in names if (org := exact_organization(session, name))}
        if len(hits) == 1:
            return {"type": kind, "id": hits.pop()}
    else:
        hits = {c.slug for name in names for c in detect_countries(name)}
        if len(hits) == 1:
            return {"type": kind, "slug": hits.pop()}
    return None


def propose_for_person(session, person_id, *, fetch=None, apply=True, delay=0):
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Person not found")
    if not person.wikidata_qid:
        raise RelationError("Person has no Wikidata identifier")
    fetch = fetch or (lambda ids: get_entities(ids, delay=delay))
    qid = person.wikidata_qid
    entities = fetch([qid])
    entity = entities.get(qid, {})
    first = {target(c) for prop in [*PROPERTIES, "P39"] for c in claims(entity, prop)}
    if first:
        entities.update(fetch(first))
    second = {target(c) for p in claims(entity, "P39") for prop in ("P2389", "P1001", "P17")
              for c in claims(entities.get(target(p), {}), prop)} - entities.keys()
    if second:
        entities.update(fetch(second))
    # No more HTTP calls after this point.
    proposals, unresolved = [], []
    subject = {"type": "person", "id": person_id}

    def resolve(kind, target_qid, prop):
        result = resolve_target(session, kind, target_qid, entities)
        if result is None:
            unresolved.append({"property": prop, "type": kind, "qid": target_qid,
                               "labels": labels(entities.get(target_qid, {}))})
        return result

    def append(left, role, right, claim, title=None):
        proposals.append(dict(subject=left, relation=role, object=right, title=title,
                              valid_from=qualifier_date(claim, "P580"), valid_to=qualifier_date(claim, "P582")))

    for prop, (role, kind) in PROPERTIES.items():
        for claim in claims(entity, prop):
            obj = resolve(kind, target(claim), prop)
            if obj:
                left, right = (obj, subject) if prop in ("P22", "P25") else (subject, obj)
                append(left, role, right, claim)
    for claim in claims(entity, "P39"):
        position_qid = target(claim)
        position = entities.get(position_qid, {})
        title = next(iter(labels(position)), None)
        orgs = [obj for c in claims(position, "P2389") if (obj := resolve("organization", target(c), "P2389"))]
        countries = [obj for prop in ("P1001", "P17") for c in claims(position, prop)
                     if (obj := resolve("country", target(c), prop))]
        for org in orgs:
            append(subject, "funkcja_publiczna", org, claim, title)
            for country in countries:
                append(org, "siedziba", country, claim)
        if not orgs:
            for country in countries:
                append(subject, "funkcja_publiczna", country, claim, title)
        if not orgs and not countries:
            unresolved.append({"property": "P39", "type": "position", "qid": position_qid, "labels": labels(position)})
    result = dict(person_id=person_id, created=0, evidence_added=0, skipped_rejected=0, unresolved=unresolved,
                  rejected={}, relation_ids=[], proposals=[])
    for proposal in proposals:
        result["proposals"].append({k: v.isoformat() if isinstance(v, datetime.date) else v for k, v in proposal.items()})
        if not apply:
            continue
        try:
            row, created, added = upsert_relation(session, **proposal, detection_method="wikidata",
                                                  evidence={"source_url": f"https://www.wikidata.org/wiki/{qid}"})
        except RelationError:
            result["rejected"]["invalid_relation"] = result["rejected"].get("invalid_relation", 0) + 1
            continue
        result["created"] += int(created)
        result["evidence_added"] += int(added)
        result["skipped_rejected"] += int(row.status == "rejected")
        if row.id not in result["relation_ids"]:
            result["relation_ids"].append(row.id)
    return result
