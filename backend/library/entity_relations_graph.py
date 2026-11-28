"""Bounded person -> organization -> country expansion of the existing reader graph."""

import datetime

from library.db.models import Organization, Person
from library.entity_relations_service import document_endpoints, key, relations_for


def extend_relationship_graph(session, doc, nodes, edges):
    document_ends = document_endpoints(session, doc.id)
    document_keys = {key(e) for e in document_ends}
    by_id = {n["id"]: n for n in nodes}
    seen = set()
    organizations = {e["id"] for e in document_ends if e["type"] == "organization"}
    organizations.update(int(n["id"].split(":")[1]) for n in nodes if n["type"] == "organization")
    published = doc.published_on
    if isinstance(published, datetime.datetime):
        published = published.date()

    def add_node(end):
        kind, identifier = key(end)
        node_id = f"{kind}:{identifier}"
        row = session.get(Person if kind == "person" else Organization, identifier) if kind != "country" else None
        node = {"id": node_id, "type": kind, "label": end["name"],
                "href": f"/{'persons' if kind == 'person' else 'organizations'}/{identifier}" if row else None,
                "description": getattr(row, "description", None)}
        if node_id not in by_id:
            nodes.append(node)
            by_id[node_id] = node
        else:
            existing = by_id[node_id]
            # A cited source keeps its link to the information source; a context node gains its registry page.
            if existing.get("linked_to_source"):
                node.pop("href")
            existing.update(node)
            existing.pop("context_only", None)
        if kind == "organization":
            organizations.add(identifier)
        return node_id

    def outside_period(row):
        start, end = row["valid_from"], row["valid_to"]
        return bool(published and ((start and published < datetime.date.fromisoformat(start)) or
                                   (end and published > datetime.date.fromisoformat(end))))

    def add(row):
        identity = row["source"], row["id"]
        if identity in seen:
            return
        seen.add(identity)
        subject, obj = row["subject"], row["object"]
        start, end = row["valid_from"], row["valid_to"]
        label = row["title"] or row["label"]
        # Perspective may be incoming; the graph always points subject -> object.
        if row["source"] == "entity_relations" and not row["title"]:
            from library.entity_relation_vocabulary import VOCABULARY
            label = VOCABULARY[row["relation"]][0]
        if start or end:
            label += f" ({start[:4] if start else '…'}–{end[:4] if end else '…'})"
        edge = {"id": f"{row['source']}:{row['id']}", "source": add_node(subject), "target": add_node(obj),
                "type": label, "status": row["status"], "outside_period": outside_period(row)}
        if row["source"] == "entity_relations":
            edge["relation_id"] = row["id"]
        excerpt = next((e["quote"] for e in row["evidence"] if e["quote"]), None)
        if excerpt:
            edge["evidence_excerpt"] = excerpt
        edges.append(edge)

    for endpoint in document_ends:
        for row in relations_for(session, endpoint["type"], endpoint["id"]):
            subject, obj = row["subject"], row["object"]
            if subject["type"] == "person":
                # An organization of the document must not drag in everyone ever tied to it: someone the
                # document does not mention appears only through a confirmed tie valid when it was published.
                if (key(subject) in document_keys or (obj["type"] == "person" and key(obj) in document_keys)
                        or (obj["type"] != "person" and row["status"] == "confirmed" and not outside_period(row))):
                    add(row)
            elif subject["type"] == "organization" and obj["type"] == "organization":
                add(row)
    for identifier in sorted(organizations):
        for row in relations_for(session, "organization", identifier):
            if row["subject"]["type"] == "organization" and row["object"]["type"] == "country":
                add(row)
